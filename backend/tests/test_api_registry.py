"""
Integration tests for the Registry API (GET/PATCH /api/rules/...).

Uses the async HTTPX TestClient with the in-memory SQLite database via
the test_client fixture.  All requests pass tenant_id as a query parameter.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rule import Rule
from app.models.tenant import Tenant


TENANT_ID = "11111111-1111-1111-1111-111111111111"


# ---------------------------------------------------------------------------
# GET /api/rules — list
# ---------------------------------------------------------------------------

class TestListRules:
    async def test_list_rules_returns_paginated_response(
        self,
        test_client: AsyncClient,
        sample_rule: Rule,
    ) -> None:
        """GET /api/rules returns total, offset, limit, and items."""
        resp = await test_client.get(
            "/api/rules",
            params={"tenant_id": TENANT_ID},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "items" in data
        assert "offset" in data
        assert "limit" in data
        assert data["total"] >= 1

    async def test_list_rules_items_have_rule_fields(
        self,
        test_client: AsyncClient,
        sample_rule: Rule,
    ) -> None:
        """Each item in the response includes core rule fields."""
        resp = await test_client.get(
            "/api/rules",
            params={"tenant_id": TENANT_ID},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1
        for item in items:
            assert "id" in item
            assert "rule_id" in item
            assert "title" in item
            assert "status" in item

    async def test_list_rules_department_filter(
        self,
        test_client: AsyncClient,
        sample_rule: Rule,
    ) -> None:
        """department query parameter filters results."""
        resp = await test_client.get(
            "/api/rules",
            params={"tenant_id": TENANT_ID, "department": "shipping"},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert all(item["department"] == "shipping" for item in items)

    async def test_list_rules_department_filter_no_match(
        self,
        test_client: AsyncClient,
        sample_rule: Rule,
    ) -> None:
        """Filtering by a non-existent department returns empty results."""
        resp = await test_client.get(
            "/api/rules",
            params={"tenant_id": TENANT_ID, "department": "nonexistent"},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    async def test_list_rules_search_filter(
        self,
        test_client: AsyncClient,
        sample_rule: Rule,
    ) -> None:
        """search query parameter filters by title/description."""
        resp = await test_client.get(
            "/api/rules",
            params={"tenant_id": TENANT_ID, "search": "high-value"},
        )
        assert resp.status_code == 200
        # The sample rule title contains "High-value"
        assert resp.json()["total"] >= 1

    async def test_list_rules_status_filter(
        self,
        test_client: AsyncClient,
        sample_rule: Rule,
    ) -> None:
        """status query parameter filters results."""
        resp = await test_client.get(
            "/api/rules",
            params={"tenant_id": TENANT_ID, "status": "active"},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert all(item["status"] == "active" for item in items)

    async def test_list_rules_risk_level_filter(
        self,
        test_client: AsyncClient,
        sample_rule: Rule,
    ) -> None:
        """risk_level query parameter filters results."""
        resp = await test_client.get(
            "/api/rules",
            params={"tenant_id": TENANT_ID, "risk_level": "medium"},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert all(item["risk_level"] == "medium" for item in items)


# ---------------------------------------------------------------------------
# GET /api/rules/{rule_id} — single rule detail
# ---------------------------------------------------------------------------

class TestGetRule:
    async def test_get_rule_returns_rule_detail(
        self,
        test_client: AsyncClient,
        sample_rule: Rule,
    ) -> None:
        """GET /api/rules/{id} returns the full rule dict for a valid UUID."""
        resp = await test_client.get(
            f"/api/rules/{sample_rule.id}",
            params={"tenant_id": TENANT_ID},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["rule_id"] == "SCN.RECIPIENTS.HIGH_VALUE_CC"
        assert data["title"] == "High-value contract CC recipients"

    async def test_get_rule_includes_all_serialized_fields(
        self,
        test_client: AsyncClient,
        sample_rule: Rule,
    ) -> None:
        """Response includes every field from Rule.to_dict()."""
        resp = await test_client.get(
            f"/api/rules/{sample_rule.id}",
            params={"tenant_id": TENANT_ID},
        )
        data = resp.json()
        for key in ("id", "rule_id", "title", "status", "risk_level",
                    "editable_fields", "editable_field_values",
                    "created_at", "updated_at"):
            assert key in data, f"Missing key: {key!r}"

    async def test_get_rule_returns_404_for_nonexistent(
        self,
        test_client: AsyncClient,
        sample_tenant: Tenant,
    ) -> None:
        """GET /api/rules/{unknown_id} returns 404."""
        resp = await test_client.get(
            f"/api/rules/{uuid.uuid4()}",
            params={"tenant_id": TENANT_ID},
        )
        assert resp.status_code == 404

    async def test_get_rule_returns_404_for_wrong_tenant(
        self,
        test_client: AsyncClient,
        sample_rule: Rule,
    ) -> None:
        """A rule from another tenant's perspective returns 404."""
        resp = await test_client.get(
            f"/api/rules/{sample_rule.id}",
            params={"tenant_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/rules/{rule_id}/editable
# ---------------------------------------------------------------------------

class TestUpdateEditable:
    async def test_patch_editable_valid_update_returns_updated_rule(
        self,
        test_client: AsyncClient,
        sample_rule: Rule,
    ) -> None:
        """A valid PATCH returns 200 with the updated rule."""
        resp = await test_client.patch(
            f"/api/rules/{sample_rule.id}/editable",
            params={"tenant_id": TENANT_ID},
            json={
                "changes": {"HIGH_VALUE_THRESHOLD": 750000},
                "changed_by": "alice@acme.com",
                "reason": "Q4 adjustment",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["editable_field_values"]["HIGH_VALUE_THRESHOLD"] == 750000

    async def test_patch_editable_unknown_field_returns_422(
        self,
        test_client: AsyncClient,
        sample_rule: Rule,
    ) -> None:
        """Trying to update an undeclared editable field returns 422."""
        resp = await test_client.patch(
            f"/api/rules/{sample_rule.id}/editable",
            params={"tenant_id": TENANT_ID},
            json={
                "changes": {"SECRET_FIELD": "hack"},
                "changed_by": "alice@acme.com",
            },
        )
        assert resp.status_code == 422

    async def test_patch_editable_wrong_type_returns_422(
        self,
        test_client: AsyncClient,
        sample_rule: Rule,
    ) -> None:
        """Passing a non-numeric value for an int field returns 422."""
        resp = await test_client.patch(
            f"/api/rules/{sample_rule.id}/editable",
            params={"tenant_id": TENANT_ID},
            json={
                "changes": {"HIGH_VALUE_THRESHOLD": "not-a-number"},
                "changed_by": "alice@acme.com",
            },
        )
        assert resp.status_code == 422

    async def test_patch_editable_value_below_min_returns_422(
        self,
        test_client: AsyncClient,
        sample_rule: Rule,
    ) -> None:
        """A value below min_value returns 422."""
        resp = await test_client.patch(
            f"/api/rules/{sample_rule.id}/editable",
            params={"tenant_id": TENANT_ID},
            json={
                "changes": {"HIGH_VALUE_THRESHOLD": -100},
                "changed_by": "alice@acme.com",
            },
        )
        assert resp.status_code == 422

    async def test_patch_editable_nonexistent_rule_returns_404(
        self,
        test_client: AsyncClient,
        sample_tenant: Tenant,
    ) -> None:
        resp = await test_client.patch(
            f"/api/rules/{uuid.uuid4()}/editable",
            params={"tenant_id": TENANT_ID},
            json={
                "changes": {},
                "changed_by": "alice@acme.com",
            },
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/rules/{rule_id}/verify
# ---------------------------------------------------------------------------

class TestVerifyRule:
    async def test_verify_rule_marks_as_verified(
        self,
        test_client: AsyncClient,
        sample_rule: Rule,
    ) -> None:
        """PATCH /verify sets verified=True and records verified_by."""
        resp = await test_client.patch(
            f"/api/rules/{sample_rule.id}/verify",
            params={"tenant_id": TENANT_ID},
            json={
                "verified_by": "alice@acme.com",
                "notes": "Reviewed against source code — accurate.",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["verified"] is True
        assert data["verified_by"] == "alice@acme.com"

    async def test_verify_rule_returns_404_for_nonexistent(
        self,
        test_client: AsyncClient,
        sample_tenant: Tenant,
    ) -> None:
        resp = await test_client.patch(
            f"/api/rules/{uuid.uuid4()}/verify",
            params={"tenant_id": TENANT_ID},
            json={"verified_by": "alice@acme.com"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/rules/{rule_id}/audit
# ---------------------------------------------------------------------------

class TestGetRuleAudit:
    async def test_audit_history_empty_before_changes(
        self,
        test_client: AsyncClient,
        sample_rule: Rule,
    ) -> None:
        """No audit entries exist for a freshly created rule."""
        resp = await test_client.get(
            f"/api/rules/{sample_rule.id}/audit",
            params={"tenant_id": TENANT_ID},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    async def test_audit_history_records_editable_update(
        self,
        test_client: AsyncClient,
        sample_rule: Rule,
    ) -> None:
        """After a PATCH, the audit log contains one entry."""
        await test_client.patch(
            f"/api/rules/{sample_rule.id}/editable",
            params={"tenant_id": TENANT_ID},
            json={
                "changes": {"HIGH_VALUE_THRESHOLD": 600000},
                "changed_by": "alice@acme.com",
            },
        )

        resp = await test_client.get(
            f"/api/rules/{sample_rule.id}/audit",
            params={"tenant_id": TENANT_ID},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        entry = data["items"][0]
        assert entry["action"] == "editable_update"
        assert entry["changed_by"] == "alice@acme.com"

    async def test_audit_history_response_structure(
        self,
        test_client: AsyncClient,
        sample_rule: Rule,
    ) -> None:
        """Audit response includes total, offset, limit, and items."""
        resp = await test_client.get(
            f"/api/rules/{sample_rule.id}/audit",
            params={"tenant_id": TENANT_ID},
        )
        assert resp.status_code == 200
        data = resp.json()
        for key in ("total", "offset", "limit", "items"):
            assert key in data


# ---------------------------------------------------------------------------
# GET /api/rules/graph
# ---------------------------------------------------------------------------

class TestDependencyGraph:
    async def test_graph_returns_nodes_and_edges(
        self,
        test_client: AsyncClient,
        sample_rules_with_graph: list,
        sample_tenant: Tenant,
    ) -> None:
        """GET /api/rules/graph returns a dict with nodes and edges keys."""
        resp = await test_client.get(
            "/api/rules/graph",
            params={"tenant_id": TENANT_ID},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data

    async def test_graph_nodes_include_rule_data(
        self,
        test_client: AsyncClient,
        sample_rules_with_graph: list,
        sample_tenant: Tenant,
    ) -> None:
        """Each graph node has an id and a data dict."""
        resp = await test_client.get(
            "/api/rules/graph",
            params={"tenant_id": TENANT_ID},
        )
        data = resp.json()
        assert len(data["nodes"]) == 5
        for node in data["nodes"]:
            assert "id" in node
            assert "data" in node

    async def test_graph_edges_connect_correct_nodes(
        self,
        test_client: AsyncClient,
        sample_rules_with_graph: list,
        sample_tenant: Tenant,
    ) -> None:
        """Expected edges from the graph fixture are present."""
        resp = await test_client.get(
            "/api/rules/graph",
            params={"tenant_id": TENANT_ID},
        )
        data = resp.json()
        edge_pairs = {(e["source"], e["target"]) for e in data["edges"]}
        assert ("SCN.THRESHOLD.ALERT", "SCN.NOTIFY.EMAIL") in edge_pairs
        assert ("SCN.THRESHOLD.ALERT", "SCN.AUDIT.LOG") in edge_pairs
        assert ("SCN.NOTIFY.EMAIL", "SCN.ESCALATE.PAGER") in edge_pairs

    async def test_graph_empty_tenant_returns_empty_lists(
        self,
        test_client: AsyncClient,
        sample_tenant: Tenant,
    ) -> None:
        """A tenant with no rules returns empty nodes and edges."""
        resp = await test_client.get(
            "/api/rules/graph",
            params={"tenant_id": TENANT_ID},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)
