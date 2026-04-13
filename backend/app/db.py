"""
Async database session factory.

Supports both PostgreSQL (asyncpg) and SQLite (aiosqlite) for local dev.
All FastAPI route handlers receive an AsyncSession via the get_db() dependency.
Scripts and Alembic migrations can use get_sync_db() for a synchronous session.
"""
from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Generator

from sqlalchemy import String, Text, TypeDecorator, create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings


# ---------------------------------------------------------------------------
# SQLite JSON workaround — SQLAlchemy's JSON type uses TEXT on SQLite but
# doesn't auto-serialize/deserialize.  This event listener handles it.
# ---------------------------------------------------------------------------

def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


# ---------------------------------------------------------------------------
# Async engine — used by FastAPI route handlers
# ---------------------------------------------------------------------------

def _async_url() -> str:
    url = settings.DATABASE_URL
    if _is_sqlite(url):
        # sqlite:///path → sqlite+aiosqlite:///path
        if "+aiosqlite" not in url:
            return url.replace("sqlite:", "sqlite+aiosqlite:", 1)
        return url
    # PostgreSQL variants
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


_async_url_str = _async_url()

_engine_kwargs = {
    "echo": settings.ENV == "dev",
}

if _is_sqlite(_async_url_str):
    # aiosqlite needs StaticPool for in-memory, and no pool_size args
    pass
else:
    _engine_kwargs.update(
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )

async_engine = create_async_engine(_async_url_str, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=True,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Sync engine — used by Alembic migrations, seed scripts, etc.
# ---------------------------------------------------------------------------

def _sync_url() -> str:
    url = settings.DATABASE_URL
    if _is_sqlite(url):
        # Strip any async driver
        return url.replace("+aiosqlite", "")
    if url.startswith("postgresql+psycopg2://"):
        return url
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


sync_engine = create_engine(
    _sync_url(),
    echo=settings.ENV == "dev",
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    class_=Session,
    autoflush=True,
    autocommit=False,
)


def get_sync_db() -> Generator[Session, None, None]:
    session = SyncSessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Auto-create tables (for SQLite local dev — Postgres uses Alembic)
# ---------------------------------------------------------------------------

async def create_tables() -> None:
    """Create all tables if they don't exist. Used for SQLite local dev."""
    from .models.base import Base  # noqa: F811

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def create_tables_sync() -> None:
    """Synchronous version for scripts."""
    from .models.base import Base  # noqa: F811

    Base.metadata.create_all(bind=sync_engine)
