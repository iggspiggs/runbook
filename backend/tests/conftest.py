"""
Shared pytest fixtures for the Runbook backend test suite.

All database tests use an async SQLite in-memory database (via aiosqlite)
so that no real PostgreSQL instance is required. The FastAPI TestClient is
wired to override the get_db dependency with this in-memory session.

PostgreSQL-specific dialect types (UUID, JSONB, Enum with create_type=True)
are handled by pre-configuring SQLAlchemy to treat them as their generic
equivalents before any table is created.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# SQLite dialect shim — swap out PostgreSQL-specific types before models load
# ---------------------------------------------------------------------------
# We must monkeypatch BEFORE importing any model module, because SQLAlchemy
# resolves dialect types at class-definition time.

from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy import String, JSON
from sqlalchemy.dialects import registry as dialect_registry


def _patch_pg_types() -> None:
    """
    Replace PostgreSQL-specific column types with SQLite-compatible ones
    so that create_all() succeeds against an in-memory SQLite engine.
    """
    import sqlalchemy.dialects.postgresql as pg_module

    # UUID(as_uuid=True) → String(36) for SQLite
    class _SQLiteUUID(String):
        def __init__(self, as_uuid: bool = True, **kw):
            super().__init__(length=36, **kw)

        def process_bind_param(self, value, dialect):
            if value is None:
                return None
            return str(value)

        def process_result_value(self, value, dialect):
            if value is None:
                return None
            try:
                return uuid.UUID(str(value))
            except (ValueError, AttributeError):
                return value

    # Patch at module level so all imports of UUID from pg module get the shim
    pg_module.UUID = _SQLiteUUID  # type: ignore[attr-defined]


_patch_pg_types()

# Now it is safe to import models (they reference UUID from pg module)
from app.models.base import Base
from app.models.rule import Rule
from app.models.audit_log import AuditLog
from app.models.tenant import Tenant
from app.models.extraction_job import ExtractionJob, JobStatus, SourceType


# ---------------------------------------------------------------------------
# Async SQLite engine
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """
    Create a fresh async SQLite in-memory engine for each test function.
    StaticPool ensures the same in-memory DB is reused within a single
    connection (required for aiosqlite + in-memory DBs).
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    # SQLite foreign-key enforcement is off by default; enable it
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_db(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Yield a single AsyncSession bound to the in-memory SQLite engine.
    Each test function gets a fresh session (and fresh tables via test_engine).
    """
    factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=True,
        autocommit=False,
    )
    async with factory() as session:
        yield session


# ---------------------------------------------------------------------------
# FastAPI TestClient with DB override
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="function")
async def test_client(test_db: AsyncSession):
    """
    Return an async HTTPX client pointed at the FastAPI app with
    the get_db dependency overridden to use our in-memory SQLite session.
    """
    from app.main import app
    from app.db import get_db

    async def _override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def sample_tenant(test_db: AsyncSession) -> Tenant:
    """A single Tenant row for the Acme Logistics demo."""
    tenant = Tenant(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        name="Acme Logistics",
        slug="acme-logistics",
        plan="pro",
        settings={"feature_flags": {"simulation": True}},
    )
    test_db.add(tenant)
    await test_db.commit()
    await test_db.refresh(tenant)
    return tenant


@pytest_asyncio.fixture
async def sample_rule(test_db: AsyncSession, sample_tenant: Tenant) -> Rule:
    """
    A fully-populated Rule row matching the Acme Logistics demo scenario.
    Rule: SCN.RECIPIENTS.HIGH_VALUE_CC — high-value contract CC recipients.
    """
    rule = Rule(
        id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        tenant_id=sample_tenant.id,
        rule_id="SCN.RECIPIENTS.HIGH_VALUE_CC",
        slug="scn-recipients-high-value-cc",
        title="High-value contract CC recipients",
        description=(
            "Automatically adds executive recipients to contracts whose total "
            "value exceeds the configured threshold."
        ),
        why=(
            "Ensures finance and executive leadership maintain visibility on "
            "contracts above the company approval threshold."
        ),
        department="shipping",
        subsystem="recipients",
        owner="contracts-team",
        tags=["email", "contracts", "high-value"],
        status="active",
        trigger="contract.total_value > HIGH_VALUE_THRESHOLD",
        conditions=["contract.total_value > 500000"],
        actions=["extend recipients with EXECUTIVE_CC"],
        actors=[{"type": "automated", "name": "contract-service", "role": "sender"}],
        editable_fields=[
            {
                "field_name": "HIGH_VALUE_THRESHOLD",
                "field_type": "int",
                "current": 500000,
                "default": 500000,
                "description": "Minimum contract value (in dollars) triggering executive CC",
                "editable_by": "admin",
                "min_value": 0,
                "max_value": 10000000,
            },
            {
                "field_name": "EXECUTIVE_CC",
                "field_type": "email_list",
                "current": ["cfo@acme.com", "vp-sales@acme.com"],
                "default": ["cfo@acme.com", "vp-sales@acme.com"],
                "description": "Email addresses copied on high-value contract notifications",
                "editable_by": "operator",
            },
        ],
        editable_field_values={},
        upstream_rule_ids=[],
        downstream_rule_ids=[],
        source_file="app/services/contracts/recipients.py",
        source_start_line=1,
        source_end_line=10,
        source_content=(
            "HIGH_VALUE_THRESHOLD = 500_000\n"
            "EXECUTIVE_CC = ['cfo@acme.com', 'vp-sales@acme.com']\n\n"
            "def get_contract_recipients(contract):\n"
            "    recipients = [contract.owner_email]\n"
            "    if contract.total_value > HIGH_VALUE_THRESHOLD:\n"
            "        recipients.extend(EXECUTIVE_CC)\n"
            "    return recipients\n"
        ),
        language="python",
        confidence=0.97,
        verified=False,
        risk_level="medium",
        customer_facing=False,
        cost_impact=None,
    )
    test_db.add(rule)
    await test_db.commit()
    await test_db.refresh(rule)
    return rule


@pytest_asyncio.fixture
async def sample_rules_with_graph(
    test_db: AsyncSession, sample_tenant: Tenant
) -> list[Rule]:
    """
    Five rules wired into a dependency graph for graph/simulation tests.

    Graph topology (A feeds B and D; B feeds C):
        A (SCN.THRESHOLD.ALERT) → B (SCN.NOTIFY.EMAIL)
        A                        → D (SCN.AUDIT.LOG)
        B                        → C (SCN.ESCALATE.PAGER)
        E is standalone

    This gives us:
      - simulate change on A → direct: [B, D], indirect: [C]
      - simulate change on C → no downstream
      - cycle A → B → A is NOT present (clean graph)
    """
    rule_defs = [
        {
            "id": uuid.UUID("a0000000-0000-0000-0000-000000000001"),
            "rule_id": "SCN.THRESHOLD.ALERT",
            "title": "Shipment alert threshold",
            "status": "active",
            "risk_level": "high",
            "customer_facing": False,
            "cost_impact": False,
            "verified": True,
            "downstream_rule_ids": ["SCN.NOTIFY.EMAIL", "SCN.AUDIT.LOG"],
            "upstream_rule_ids": [],
        },
        {
            "id": uuid.UUID("b0000000-0000-0000-0000-000000000002"),
            "rule_id": "SCN.NOTIFY.EMAIL",
            "title": "Email notification dispatch",
            "status": "active",
            "risk_level": "medium",
            "customer_facing": True,
            "cost_impact": False,
            "verified": True,
            "downstream_rule_ids": ["SCN.ESCALATE.PAGER"],
            "upstream_rule_ids": ["SCN.THRESHOLD.ALERT"],
        },
        {
            "id": uuid.UUID("c0000000-0000-0000-0000-000000000003"),
            "rule_id": "SCN.ESCALATE.PAGER",
            "title": "PagerDuty escalation",
            "status": "active",
            "risk_level": "critical",
            "customer_facing": False,
            "cost_impact": True,
            "verified": False,
            "downstream_rule_ids": [],
            "upstream_rule_ids": ["SCN.NOTIFY.EMAIL"],
        },
        {
            "id": uuid.UUID("d0000000-0000-0000-0000-000000000004"),
            "rule_id": "SCN.AUDIT.LOG",
            "title": "Audit log writer",
            "status": "paused",
            "risk_level": "low",
            "customer_facing": False,
            "cost_impact": False,
            "verified": True,
            "downstream_rule_ids": [],
            "upstream_rule_ids": ["SCN.THRESHOLD.ALERT"],
        },
        {
            "id": uuid.UUID("e0000000-0000-0000-0000-000000000005"),
            "rule_id": "SCN.STANDALONE.CLEANUP",
            "title": "Nightly cleanup job",
            "status": "active",
            "risk_level": "low",
            "customer_facing": False,
            "cost_impact": False,
            "verified": True,
            "downstream_rule_ids": [],
            "upstream_rule_ids": [],
        },
    ]

    rules = []
    for d in rule_defs:
        rule = Rule(
            id=d["id"],
            tenant_id=sample_tenant.id,
            rule_id=d["rule_id"],
            title=d["title"],
            status=d["status"],
            risk_level=d["risk_level"],
            customer_facing=d["customer_facing"],
            cost_impact=d["cost_impact"],
            verified=d["verified"],
            downstream_rule_ids=d["downstream_rule_ids"],
            upstream_rule_ids=d["upstream_rule_ids"],
            editable_fields=[],
            editable_field_values={},
            source_file=f"app/rules/{d['rule_id'].lower().replace('.', '_')}.py",
            source_content="# placeholder source",
        )
        test_db.add(rule)
        rules.append(rule)

    await test_db.commit()
    for r in rules:
        await test_db.refresh(r)
    return rules


@pytest.fixture
def mock_anthropic_client():
    """
    Return a MagicMock that mimics anthropic.Anthropic well enough for
    RuleAnalyzer tests. The messages.create call is patched to return a
    canned JSON response representing a single extracted rule.
    """
    canned_response = """{
        "is_rule": true,
        "rule_id": "SCN.RECIPIENTS.HIGH_VALUE_CC",
        "title": "High-value contract CC recipients",
        "description": "Adds executive CC on contracts above threshold.",
        "trigger": "contract.total_value > HIGH_VALUE_THRESHOLD",
        "conditions": ["contract.total_value > 500000"],
        "actions": ["extend recipients with EXECUTIVE_CC"],
        "editable_fields": [
            {
                "name": "HIGH_VALUE_THRESHOLD",
                "type": "int",
                "current_value": 500000,
                "description": "Minimum contract value triggering executive CC",
                "min_value": 0,
                "max_value": null,
                "allowed_values": []
            }
        ],
        "risk_level": "medium",
        "customer_facing": false,
        "cost_impact": false,
        "upstream_suggestions": [],
        "downstream_suggestions": [],
        "tags": ["contracts", "email"],
        "confidence": 0.95
    }"""

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=canned_response)]

    mock_messages = MagicMock()
    mock_messages.create = MagicMock(return_value=mock_message)

    mock_client = MagicMock()
    mock_client.messages = mock_messages

    return mock_client
