"""
Unit tests for RuleService — the single data-access layer for all rule operations.

Tests use the async SQLite in-memory database provided by conftest.py fixtures.
No mocking of the DB layer: we test the real SQL queries against a real (SQLite)
engine to catch logic errors early.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rule import Rule
from app.models.audit_log import AuditLog
from app.models.tenant import Tenant
from app.services.registry.rule_service import RuleService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rule(tenant_id, rule_id, title, **kwargs) -> Rule:
    """Factory for lightweight Rule objects used within individual tests."""
    return Rule(
        tenant_id=tenant_id,
        rule_id=rule_id,
        title=title,
        status=kwargs.get("status", "active"),
        risk_level=kwargs.get("risk_level", "medium"),
        department=kwargs.get("department", None),
        description=kwargs.get("description", ""),
        editable_fields=kwargs.get("editable_fields", []),
        editable_field_values=kwargs.get("editable_field_values", {}),
        upstream_rule_ids=kwargs.get("upstream_rule_ids", []),
        downstream_rule_ids=kwargs.get("downstream_rule_ids", []),
        verified=kwargs.get("verified", False),
        customer_facing=kwargs.get("customer_facing", False),
        cost_impact=kwargs.get("cost_impact", False),
    )


# ---------------------------------------------------------------------------
# get_rules — filtering
# ---------------------------------------------------------------------------

class TestGetRules:
    async def test_get_rules_no_filters_returns_all(
        self, test_db: AsyncSession, sample_tenant: Tenant
    ) -> None:
        """With no optional filters, all rules for the tenant are returned."""
        for i in range(3):
            test_db.add(
                _make_rule(sample_tenant.id, f"RULE.A.{i}", f"Rule {i}")
            )
        await test_db.commit()

        svc = RuleService(test_db)
        rules, total = await svc.get_rules({"tenant_id": str(sample_tenant.id)})
        assert total == 3
        assert len(rules) == 3

    async def test_get_rules_department_filter(
        self, test_db: AsyncSession, sample_tenant: Tenant
    ) -> None:
        """department filter returns only matching rules."""
        test_db.add(_make_rule(sample_tenant.id, "BILL.A.1", "Billing Rule",
                               department="billing"))
        test_db.add(_make_rule(sample_tenant.id, "OPS.A.1", "Ops Rule",
                               department="operations"))
        await test_db.commit()

        svc = RuleService(test_db)
        rules, total = await svc.get_rules(
            {"tenant_id": str(sample_tenant.id), "department": "billing"}
        )
        assert total == 1
        assert rules[0].department == "billing"

    async def test_get_rules_search_matches_title(
        self, test_db: AsyncSession, sample_tenant: Tenant
    ) -> None:
        """search filter matches against title (case-insensitive)."""
        test_db.add(_make_rule(sample_tenant.id, "R.1", "High Value Contract Alert"))
        test_db.add(_make_rule(sample_tenant.id, "R.2", "Low Balance Notification"))
        await test_db.commit()

        svc = RuleService(test_db)
        rules, total = await svc.get_rules(
            {"tenant_id": str(sample_tenant.id), "search": "high value"}
        )
        assert total == 1
        assert "High Value" in rules[0].title

    async def test_get_rules_search_matches_description(
        self, test_db: AsyncSession, sample_tenant: Tenant
    ) -> None:
        """search filter also matches against description."""
        test_db.add(_make_rule(
            sample_tenant.id, "R.1", "Alert Rule",
            description="fires when balance drops below threshold"
        ))
        test_db.add(_make_rule(sample_tenant.id, "R.2", "Other Rule", description="unrelated"))
        await test_db.commit()

        svc = RuleService(test_db)
        rules, total = await svc.get_rules(
            {"tenant_id": str(sample_tenant.id), "search": "balance drops"}
        )
        assert total == 1
        assert rules[0].rule_id == "R.1"

    async def test_get_rules_status_filter(
        self, test_db: AsyncSession, sample_tenant: Tenant
    ) -> None:
        """status filter returns only rules with matching status."""
        test_db.add(_make_rule(sample_tenant.id, "R.1", "Active Rule", status="active"))
        test_db.add(_make_rule(sample_tenant.id, "R.2", "Paused Rule", status="paused"))
        test_db.add(_make_rule(sample_tenant.id, "R.3", "Draft Rule", status="draft"))
        await test_db.commit()

        svc = RuleService(test_db)
        rules, total = await svc.get_rules(
            {"tenant_id": str(sample_tenant.id), "status": "paused"}
        )
        assert total == 1
        assert rules[0].status == "paused"

    async def test_get_rules_risk_level_filter(
        self, test_db: AsyncSession, sample_tenant: Tenant
    ) -> None:
        """risk_level filter returns only matching rules."""
        test_db.add(_make_rule(sample_tenant.id, "R.1", "Critical Rule", risk_level="critical"))
        test_db.add(_make_rule(sample_tenant.id, "R.2", "Low Risk Rule", risk_level="low"))
        await test_db.commit()

        svc = RuleService(test_db)
        rules, total = await svc.get_rules(
            {"tenant_id": str(sample_tenant.id), "risk_level": "critical"}
        )
        assert total == 1
        assert rules[0].risk_level == "critical"

    async def test_get_rules_tenant_isolation(
        self, test_db: AsyncSession
    ) -> None:
        """Rules from one tenant are never returned when querying another."""
        t1_id = uuid.UUID("11111111-0000-0000-0000-000000000001")
        t2_id = uuid.UUID("11111111-0000-0000-0000-000000000002")

        for tid, slug in [(t1_id, "tenant-one"), (t2_id, "tenant-two")]:
            from app.models.tenant import Tenant
            test_db.add(Tenant(id=tid, name=slug, slug=slug))
        await test_db.commit()

        test_db.add(_make_rule(t1_id, "T1.RULE", "Tenant 1 Rule"))
        test_db.add(_make_rule(t2_id, "T2.RULE", "Tenant 2 Rule"))
        await test_db.commit()

        svc = RuleService(test_db)
        rules, total = await svc.get_rules({"tenant_id": str(t1_id)})
        assert total == 1
        assert rules[0].rule_id == "T1.RULE"


# ---------------------------------------------------------------------------
# get_rule — single rule lookup
# ---------------------------------------------------------------------------

class TestGetRule:
    async def test_get_rule_returns_correct_rule(
        self, test_db: AsyncSession, sample_rule: Rule, sample_tenant: Tenant
    ) -> None:
        svc = RuleService(test_db)
        result = await svc.get_rule(str(sample_tenant.id), sample_rule.id)
        assert result is not None
        assert result.rule_id == "SCN.RECIPIENTS.HIGH_VALUE_CC"

    async def test_get_rule_nonexistent_returns_none(
        self, test_db: AsyncSession, sample_tenant: Tenant
    ) -> None:
        svc = RuleService(test_db)
        result = await svc.get_rule(str(sample_tenant.id), uuid.uuid4())
        assert result is None

    async def test_get_rule_wrong_tenant_returns_none(
        self, test_db: AsyncSession, sample_rule: Rule
    ) -> None:
        """A rule UUID from one tenant is not visible to another tenant."""
        svc = RuleService(test_db)
        result = await svc.get_rule(str(uuid.uuid4()), sample_rule.id)
        assert result is None


# ---------------------------------------------------------------------------
# update_editable — field validation and mutation
# ---------------------------------------------------------------------------

class TestUpdateEditable:
    async def test_update_editable_valid_field_persists(
        self, test_db: AsyncSession, sample_rule: Rule, sample_tenant: Tenant
    ) -> None:
        """A valid editable-field update is persisted and returned."""
        svc = RuleService(test_db)
        updated = await svc.update_editable(
            tenant_id=str(sample_tenant.id),
            rule_id=sample_rule.id,
            field_updates={"HIGH_VALUE_THRESHOLD": 750000},
            changed_by="alice@acme.com",
            reason="Q4 budget adjustment",
        )
        assert updated is not None
        assert updated.editable_field_values["HIGH_VALUE_THRESHOLD"] == 750000

    async def test_update_editable_creates_audit_log(
        self, test_db: AsyncSession, sample_rule: Rule, sample_tenant: Tenant
    ) -> None:
        """Each accepted field change produces exactly one AuditLog entry."""
        from sqlalchemy import select

        svc = RuleService(test_db)
        await svc.update_editable(
            tenant_id=str(sample_tenant.id),
            rule_id=sample_rule.id,
            field_updates={"HIGH_VALUE_THRESHOLD": 600000},
            changed_by="bob@acme.com",
        )

        result = await test_db.execute(
            select(AuditLog).where(AuditLog.action == "editable_update")
        )
        logs = list(result.scalars().all())
        assert len(logs) == 1
        assert logs[0].field_name == "HIGH_VALUE_THRESHOLD"
        assert logs[0].changed_by == "bob@acme.com"

    async def test_update_editable_multiple_fields_multiple_audit_entries(
        self, test_db: AsyncSession, sample_rule: Rule, sample_tenant: Tenant
    ) -> None:
        """Two field updates produce two separate audit log entries."""
        from sqlalchemy import select

        svc = RuleService(test_db)
        await svc.update_editable(
            tenant_id=str(sample_tenant.id),
            rule_id=sample_rule.id,
            field_updates={
                "HIGH_VALUE_THRESHOLD": 600000,
                "EXECUTIVE_CC": ["cfo@acme.com"],
            },
            changed_by="alice@acme.com",
        )

        result = await test_db.execute(
            select(AuditLog).where(AuditLog.action == "editable_update")
        )
        logs = list(result.scalars().all())
        assert len(logs) == 2

    async def test_update_editable_rejects_unknown_field(
        self, test_db: AsyncSession, sample_rule: Rule, sample_tenant: Tenant
    ) -> None:
        """Attempting to update an undeclared field raises ValueError."""
        svc = RuleService(test_db)
        with pytest.raises(ValueError, match="not declared as editable"):
            await svc.update_editable(
                tenant_id=str(sample_tenant.id),
                rule_id=sample_rule.id,
                field_updates={"NONEXISTENT_FIELD": "value"},
                changed_by="alice@acme.com",
            )

    async def test_update_editable_rejects_wrong_type(
        self, test_db: AsyncSession, sample_rule: Rule, sample_tenant: Tenant
    ) -> None:
        """
        Passing a string where an int is expected raises ValueError
        (the int() coercer raises ValueError on non-numeric strings).
        """
        svc = RuleService(test_db)
        with pytest.raises(ValueError, match="Invalid value"):
            await svc.update_editable(
                tenant_id=str(sample_tenant.id),
                rule_id=sample_rule.id,
                field_updates={"HIGH_VALUE_THRESHOLD": "not-a-number"},
                changed_by="alice@acme.com",
            )

    async def test_update_editable_rejects_value_below_min(
        self, test_db: AsyncSession, sample_rule: Rule, sample_tenant: Tenant
    ) -> None:
        """A value below min_value raises ValueError with a descriptive message."""
        svc = RuleService(test_db)
        with pytest.raises(ValueError, match="below minimum"):
            await svc.update_editable(
                tenant_id=str(sample_tenant.id),
                rule_id=sample_rule.id,
                field_updates={"HIGH_VALUE_THRESHOLD": -1},
                changed_by="alice@acme.com",
            )

    async def test_update_editable_rejects_value_above_max(
        self, test_db: AsyncSession, sample_rule: Rule, sample_tenant: Tenant
    ) -> None:
        """A value above max_value raises ValueError."""
        svc = RuleService(test_db)
        with pytest.raises(ValueError, match="exceeds maximum"):
            await svc.update_editable(
                tenant_id=str(sample_tenant.id),
                rule_id=sample_rule.id,
                field_updates={"HIGH_VALUE_THRESHOLD": 99999999},
                changed_by="alice@acme.com",
            )

    async def test_update_editable_nonexistent_rule_returns_none(
        self, test_db: AsyncSession, sample_tenant: Tenant
    ) -> None:
        svc = RuleService(test_db)
        result = await svc.update_editable(
            tenant_id=str(sample_tenant.id),
            rule_id=uuid.uuid4(),
            field_updates={},
            changed_by="system",
        )
        assert result is None


# ---------------------------------------------------------------------------
# upsert_from_extraction
# ---------------------------------------------------------------------------

class TestUpsertFromExtraction:
    async def test_upsert_creates_new_rules(
        self, test_db: AsyncSession, sample_tenant: Tenant
    ) -> None:
        """New rules are inserted with status='draft'."""
        extracted = [
            {
                "rule_id": "NEW.RULE.ONE",
                "title": "New Rule One",
                "description": "Auto-extracted",
                "trigger": "on schedule",
                "conditions": [],
                "actions": [],
                "editable_fields": [],
                "risk_level": "low",
                "customer_facing": False,
                "source_file": "app/jobs.py",
                "source_content": "def job(): pass",
                "language": "python",
                "upstream_rule_ids": [],
                "downstream_rule_ids": [],
                "tags": [],
            }
        ]
        svc = RuleService(test_db)
        committed, skipped = await svc.upsert_from_extraction(
            tenant_id=str(sample_tenant.id),
            extracted_rules=extracted,
            committed_by="extractor",
        )
        assert committed == 1
        assert skipped == 0

        rules, total = await svc.get_rules({"tenant_id": str(sample_tenant.id)})
        assert total == 1
        assert rules[0].status == "draft"
        assert rules[0].rule_id == "NEW.RULE.ONE"

    async def test_upsert_updates_existing_rule_without_admin_edits(
        self, test_db: AsyncSession, sample_rule: Rule, sample_tenant: Tenant
    ) -> None:
        """
        Re-scanning an existing rule (no operator edits) updates its title
        but preserves editable_field_values.
        """
        extracted = [
            {
                "rule_id": "SCN.RECIPIENTS.HIGH_VALUE_CC",
                "title": "Updated CC Title",
                "description": "Updated description",
                "trigger": "contract.total_value > HIGH_VALUE_THRESHOLD",
                "conditions": [],
                "actions": [],
                "editable_fields": [],
                "risk_level": "medium",
                "customer_facing": False,
                "source_file": "app/services/contracts/recipients.py",
                "source_content": "# updated",
                "language": "python",
                "upstream_rule_ids": [],
                "downstream_rule_ids": [],
                "tags": [],
            }
        ]
        svc = RuleService(test_db)
        committed, skipped = await svc.upsert_from_extraction(
            tenant_id=str(sample_tenant.id),
            extracted_rules=extracted,
            committed_by="extractor",
        )
        assert committed == 1
        assert skipped == 0

        updated = await svc.get_rule(str(sample_tenant.id), sample_rule.id)
        assert updated.title == "Updated CC Title"

    async def test_upsert_skips_rule_with_admin_edits(
        self, test_db: AsyncSession, sample_rule: Rule, sample_tenant: Tenant
    ) -> None:
        """
        If an operator has already set editable_field_values, a re-scan
        does NOT overwrite the rule (skipped count increments instead).
        """
        # Simulate an operator having edited the field
        svc = RuleService(test_db)
        await svc.update_editable(
            tenant_id=str(sample_tenant.id),
            rule_id=sample_rule.id,
            field_updates={"HIGH_VALUE_THRESHOLD": 750000},
            changed_by="alice@acme.com",
        )

        extracted = [
            {
                "rule_id": "SCN.RECIPIENTS.HIGH_VALUE_CC",
                "title": "Would Overwrite Title",
                "description": "",
                "trigger": "",
                "conditions": [],
                "actions": [],
                "editable_fields": [],
                "risk_level": "medium",
                "customer_facing": False,
                "source_file": "app/services/contracts/recipients.py",
                "source_content": "# some new code",
                "language": "python",
                "upstream_rule_ids": [],
                "downstream_rule_ids": [],
                "tags": [],
            }
        ]
        committed, skipped = await svc.upsert_from_extraction(
            tenant_id=str(sample_tenant.id),
            extracted_rules=extracted,
            committed_by="extractor",
        )
        assert committed == 0
        assert skipped == 1

        # Title should NOT have been overwritten
        rule = await svc.get_rule(str(sample_tenant.id), sample_rule.id)
        assert rule.title == "High-value contract CC recipients"


# ---------------------------------------------------------------------------
# get_dependency_graph
# ---------------------------------------------------------------------------

class TestGetDependencyGraph:
    async def test_graph_returns_nodes_and_edges(
        self,
        test_db: AsyncSession,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        """Graph endpoint returns node and edge lists."""
        svc = RuleService(test_db)
        graph = await svc.get_dependency_graph(str(sample_tenant.id))

        assert "nodes" in graph
        assert "edges" in graph
        assert len(graph["nodes"]) == 5

    async def test_graph_edges_match_upstream_relationships(
        self,
        test_db: AsyncSession,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        """
        Edges are derived from upstream_rule_ids; each upstream reference
        becomes an edge from the upstream node to the current node.
        """
        svc = RuleService(test_db)
        graph = await svc.get_dependency_graph(str(sample_tenant.id))

        edge_pairs = {(e["source"], e["target"]) for e in graph["edges"]}
        # SCN.NOTIFY.EMAIL has upstream SCN.THRESHOLD.ALERT
        assert ("SCN.THRESHOLD.ALERT", "SCN.NOTIFY.EMAIL") in edge_pairs
        # SCN.AUDIT.LOG has upstream SCN.THRESHOLD.ALERT
        assert ("SCN.THRESHOLD.ALERT", "SCN.AUDIT.LOG") in edge_pairs
        # SCN.ESCALATE.PAGER has upstream SCN.NOTIFY.EMAIL
        assert ("SCN.NOTIFY.EMAIL", "SCN.ESCALATE.PAGER") in edge_pairs

    async def test_graph_node_data_fields(
        self,
        test_db: AsyncSession,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        """Each graph node includes the fields needed for frontend rendering."""
        svc = RuleService(test_db)
        graph = await svc.get_dependency_graph(str(sample_tenant.id))

        for node in graph["nodes"]:
            assert "id" in node
            assert "data" in node
            for field in ("rule_id", "title", "status", "risk_level", "verified"):
                assert field in node["data"], f"Missing field {field!r} in node data"

    async def test_graph_standalone_node_has_no_edges(
        self,
        test_db: AsyncSession,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        """A rule with no upstream/downstream references generates no edges."""
        svc = RuleService(test_db)
        graph = await svc.get_dependency_graph(str(sample_tenant.id))

        standalone_edges = [
            e for e in graph["edges"]
            if e["source"] == "SCN.STANDALONE.CLEANUP"
            or e["target"] == "SCN.STANDALONE.CLEANUP"
        ]
        assert standalone_edges == []
