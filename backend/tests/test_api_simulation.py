"""
Integration tests for the Simulation API (POST /api/simulate).

Uses the async HTTPX TestClient backed by the in-memory SQLite database.
The sample_rules_with_graph fixture provides the 5-rule dependency graph
used for all simulation assertions.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.rule import Rule
from app.models.tenant import Tenant

TENANT_ID = "11111111-1111-1111-1111-111111111111"

# UUIDs matching the sample_rules_with_graph fixture (defined in conftest.py)
RULE_A_ID = "a0000000-0000-0000-0000-000000000001"  # SCN.THRESHOLD.ALERT
RULE_B_ID = "b0000000-0000-0000-0000-000000000002"  # SCN.NOTIFY.EMAIL
RULE_C_ID = "c0000000-0000-0000-0000-000000000003"  # SCN.ESCALATE.PAGER
RULE_D_ID = "d0000000-0000-0000-0000-000000000004"  # SCN.AUDIT.LOG  (paused)
RULE_E_ID = "e0000000-0000-0000-0000-000000000005"  # SCN.STANDALONE.CLEANUP


class TestSimulateChange:
    async def test_simulate_returns_200_for_valid_rule(
        self,
        test_client: AsyncClient,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        """POST /api/simulate with a valid rule_id returns 200."""
        resp = await test_client.post(
            "/api/simulate",
            json={
                "tenant_id": TENANT_ID,
                "rule_id": RULE_A_ID,
                "proposed_changes": {"some_threshold": 95},
            },
        )
        assert resp.status_code == 200

    async def test_simulate_response_has_required_top_level_keys(
        self,
        test_client: AsyncClient,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        """Response includes all documented top-level keys."""
        resp = await test_client.post(
            "/api/simulate",
            json={
                "tenant_id": TENANT_ID,
                "rule_id": RULE_A_ID,
                "proposed_changes": {},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        for key in (
            "target_rule_id",
            "target_rule_title",
            "proposed_changes",
            "aggregate_risk",
            "cycle_detected",
            "warnings",
            "directly_affected",
            "indirectly_affected",
            "impact_summary",
        ):
            assert key in data, f"Missing key: {key!r}"

    async def test_simulate_A_reports_direct_impact_on_B_and_D(
        self,
        test_client: AsyncClient,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        """Simulating rule A returns B and D as directly affected."""
        resp = await test_client.post(
            "/api/simulate",
            json={
                "tenant_id": TENANT_ID,
                "rule_id": RULE_A_ID,
                "proposed_changes": {"threshold": 90},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        direct_ids = {r["rule_id"] for r in data["directly_affected"]}
        assert "SCN.NOTIFY.EMAIL" in direct_ids
        assert "SCN.AUDIT.LOG" in direct_ids

    async def test_simulate_A_reports_indirect_impact_on_C(
        self,
        test_client: AsyncClient,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        """Simulating rule A returns C as indirectly affected (via B)."""
        resp = await test_client.post(
            "/api/simulate",
            json={
                "tenant_id": TENANT_ID,
                "rule_id": RULE_A_ID,
                "proposed_changes": {},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        indirect_ids = {r["rule_id"] for r in data["indirectly_affected"]}
        assert "SCN.ESCALATE.PAGER" in indirect_ids

    async def test_simulate_aggregate_risk_is_critical_for_A(
        self,
        test_client: AsyncClient,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        """
        Rule C (critical risk) is reachable from A, so aggregate_risk
        for simulating A should be 'critical'.
        """
        resp = await test_client.post(
            "/api/simulate",
            json={
                "tenant_id": TENANT_ID,
                "rule_id": RULE_A_ID,
                "proposed_changes": {},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["aggregate_risk"] == "critical"

    async def test_simulate_C_has_no_affected_rules(
        self,
        test_client: AsyncClient,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        """Rule C is a leaf node — no directly or indirectly affected rules."""
        resp = await test_client.post(
            "/api/simulate",
            json={
                "tenant_id": TENANT_ID,
                "rule_id": RULE_C_ID,
                "proposed_changes": {},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["directly_affected"] == []
        assert data["indirectly_affected"] == []

    async def test_simulate_returns_warnings_list(
        self,
        test_client: AsyncClient,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        """The warnings field is a non-empty list for rule A."""
        resp = await test_client.post(
            "/api/simulate",
            json={
                "tenant_id": TENANT_ID,
                "rule_id": RULE_A_ID,
                "proposed_changes": {"x": 1},
            },
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["warnings"], list)
        assert len(resp.json()["warnings"]) > 0

    async def test_simulate_impact_summary_totals_match(
        self,
        test_client: AsyncClient,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        """impact_summary.total_affected == direct + indirect counts."""
        resp = await test_client.post(
            "/api/simulate",
            json={
                "tenant_id": TENANT_ID,
                "rule_id": RULE_A_ID,
                "proposed_changes": {},
            },
        )
        assert resp.status_code == 200
        s = resp.json()["impact_summary"]
        assert s["total_affected"] == s["directly_affected_count"] + s["indirectly_affected_count"]

    async def test_simulate_proposed_changes_echoed_in_response(
        self,
        test_client: AsyncClient,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        """The response echoes proposed_changes so the UI can display what was asked."""
        payload = {"alert_threshold": 95, "retry_count": 5}
        resp = await test_client.post(
            "/api/simulate",
            json={
                "tenant_id": TENANT_ID,
                "rule_id": RULE_A_ID,
                "proposed_changes": payload,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["proposed_changes"] == payload


class TestSimulateNotFound:
    async def test_simulate_nonexistent_rule_returns_404(
        self,
        test_client: AsyncClient,
        sample_tenant: Tenant,
    ) -> None:
        """POST /api/simulate with an unknown rule_id returns 404."""
        resp = await test_client.post(
            "/api/simulate",
            json={
                "tenant_id": TENANT_ID,
                "rule_id": str(uuid.uuid4()),
                "proposed_changes": {},
            },
        )
        assert resp.status_code == 404

    async def test_simulate_valid_uuid_wrong_tenant_returns_404(
        self,
        test_client: AsyncClient,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        """A rule that exists but belongs to a different tenant returns 404."""
        resp = await test_client.post(
            "/api/simulate",
            json={
                "tenant_id": str(uuid.uuid4()),  # wrong tenant
                "rule_id": RULE_A_ID,
                "proposed_changes": {},
            },
        )
        assert resp.status_code == 404


class TestSimulateRequestValidation:
    async def test_simulate_missing_tenant_id_returns_422(
        self,
        test_client: AsyncClient,
        sample_tenant: Tenant,
    ) -> None:
        """Missing required tenant_id field returns 422 (Pydantic validation)."""
        resp = await test_client.post(
            "/api/simulate",
            json={
                "rule_id": RULE_A_ID,
                "proposed_changes": {},
                # tenant_id is intentionally omitted
            },
        )
        assert resp.status_code == 422

    async def test_simulate_missing_rule_id_returns_422(
        self,
        test_client: AsyncClient,
        sample_tenant: Tenant,
    ) -> None:
        """Missing required rule_id field returns 422."""
        resp = await test_client.post(
            "/api/simulate",
            json={
                "tenant_id": TENANT_ID,
                "proposed_changes": {},
                # rule_id is intentionally omitted
            },
        )
        assert resp.status_code == 422

    async def test_simulate_invalid_uuid_format_returns_422(
        self,
        test_client: AsyncClient,
        sample_tenant: Tenant,
    ) -> None:
        """A malformed UUID string for rule_id returns 422."""
        resp = await test_client.post(
            "/api/simulate",
            json={
                "tenant_id": TENANT_ID,
                "rule_id": "not-a-uuid-at-all",
                "proposed_changes": {},
            },
        )
        assert resp.status_code == 422
