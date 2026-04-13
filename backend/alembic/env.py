"""
Alembic environment configuration.

Supports both:
  - Online (connected) migrations via asyncpg + run_async_migrations()
  - Offline (SQL-script) migrations via run_migrations_offline()

The DATABASE_URL is read from the app's Settings object so that the
same .env file drives both the application and migrations — no
separate configuration to keep in sync.
"""
from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# ── Make sure the backend package is importable from anywhere alembic is run ──
# Running `alembic upgrade head` from backend/ works without this; running it
# from the repo root requires the path adjustment below.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Import application models so Alembic can see all tables ──────────────────
# This must come AFTER the sys.path manipulation above.
from app.config import settings  # noqa: E402
from app.models import Base  # noqa: E402  — registers all ORM models via __init__.py

# Alembic Config object (gives access to values in alembic.ini)
config = context.config

# Set up Python logging from the alembic.ini [loggers] section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate support (`alembic revision --autogenerate`)
target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _async_url() -> str:
    """
    Return a postgresql+asyncpg:// URL derived from settings.DATABASE_URL.
    Alembic's online mode needs the async driver.
    """
    url = settings.DATABASE_URL
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _sync_url() -> str:
    """
    Return a postgresql+psycopg2:// URL derived from settings.DATABASE_URL.
    Offline mode (SQL generation) uses the synchronous driver.
    """
    url = settings.DATABASE_URL
    if url.startswith("postgresql+psycopg2://"):
        return url
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


# ---------------------------------------------------------------------------
# Offline migrations — generates SQL to stdout, no DB connection required
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """
    Run migrations without a live database connection.

    Produces a SQL script that can be reviewed and applied manually.
    Useful for production environments where the migration runner does
    not have direct DB access.
    """
    url = _sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online migrations — connects to the database and applies changes directly
# ---------------------------------------------------------------------------

def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Create an async engine and run migrations within a synchronous
    connection context (Alembic does not natively support async, but
    SQLAlchemy provides run_sync() to bridge the gap).
    """
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _async_url()

    connectable = async_engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
