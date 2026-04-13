from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings

logger = logging.getLogger(__name__)

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.ENV == "dev" else logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Runs once at startup and once at shutdown."""
    summary = settings.log_safe_summary()
    logger.info("Runbook backend starting — config: %s", summary)

    if settings.ENV == "prod" and settings.SECRET_KEY == "change-me-before-production":
        raise RuntimeError("SECRET_KEY must be changed before running in production.")

    # Auto-create tables for SQLite local dev (Postgres uses Alembic)
    if settings.DATABASE_URL.startswith("sqlite"):
        from .db import create_tables
        logger.info("SQLite detected — auto-creating tables...")
        await create_tables()

    yield

    logger.info("Runbook backend shutting down.")


# ── App factory ───────────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title="Runbook API",
        description=(
            "Scan codebases, extract automation rules into a living registry, "
            "and let operators safely edit system behaviour."
        ),
        version="0.1.0",
        docs_url="/docs" if settings.ENV != "prod" else None,
        redoc_url="/redoc" if settings.ENV != "prod" else None,
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    # Each router module defines its own prefix (e.g. /api/rules, /api/extract).
    # Do NOT add an extra prefix= here or the paths will be doubled.
    from .routers.registry import router as registry_router
    from .routers.extraction import router as extraction_router
    from .routers.audit import router as audit_router
    from .routers.simulation import router as simulation_router

    app.include_router(registry_router)
    app.include_router(extraction_router)
    app.include_router(audit_router)
    app.include_router(simulation_router)

    # ── Built-in endpoints ────────────────────────────────────────────────────
    @app.get("/api/tenants/demo", tags=["tenants"], summary="Get demo tenant")
    async def get_demo_tenant() -> dict:
        """Returns the demo tenant ID for local dev / demo mode."""
        from sqlalchemy import select
        from .db import AsyncSessionLocal
        from .models.tenant import Tenant

        async with AsyncSessionLocal() as session:
            stmt = select(Tenant).where(Tenant.slug == "acme-logistics").limit(1)
            result = await session.execute(stmt)
            tenant = result.scalar_one_or_none()
            if tenant:
                return {"id": str(tenant.id), "name": tenant.name, "slug": tenant.slug}
            return {"id": "", "name": "", "slug": ""}

    @app.get("/health", tags=["ops"], summary="Health check")
    async def health() -> dict:
        """
        Returns 200 with service status.  Used by load balancers and uptime
        monitors.  Does NOT check DB connectivity — use /health/ready for that.
        """
        return {"status": "ok", "env": settings.ENV, "version": "0.1.0"}

    @app.get("/health/ready", tags=["ops"], summary="Readiness check")
    async def readiness() -> dict:
        """
        Checks that the database is reachable.  Returns 503 if not.
        Suitable for Kubernetes readinessProbe.
        """
        from sqlalchemy import text

        from .db import async_engine

        try:
            async with async_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return {"status": "ready", "database": "ok"}
        except Exception as exc:
            logger.error("Readiness check failed: %s", exc)
            return {"status": "not ready", "database": str(exc)}

    return app


app = create_app()
