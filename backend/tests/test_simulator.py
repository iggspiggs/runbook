"""
Tests for SimulationEngine — what-if impact analysis.

Uses the sample_rules_with_graph fixture (defined in conftest.py) which
creates this topology:

    A (SCN.THRESHOLD.ALERT)  → B (SCN.NOTIFY.EMAIL)
    A                         → D (SCN.AUDIT.LOG)
    B                         → C (SCN.ESCALATE.PAGER)
    E (SCN.STANDALONE.CLEANUP) — no connections

Fixture details:
    A: risk=high,     customer_facing=False, cost_impact=False, verified=True
    B: risk=medium,   customer_facing=True,  cost_impact=False, verified=True
    C: risk=critical, customer_facing=False, cost_impact=True,  verified=False
    D: risk=low,      status=paused,         customer_facing=False, verified=True
    E: risk=low,      standalone,            verified=True
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rule import Rule
from app.models.tenant import Tenant
from app.services.registry.rule_service import RuleService
from app.services.simulator.engine import SimulationEngine, SimulationResult, AffectedRule


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rule_id_for_name(name: str) -> uuid.UUID:
    """Maps letter name (A-E) to the UUIDs defined in the graph fixture."""
    mapping = {
        "A": uuid.UUID("a0000000-0000-0000-0000-000000000001"),
        "B": uuid.UUID("b0000000-0000-0000-0000-000000000002"),
        "C": uuid.UUID("c0000000-0000-0000-0000-000000000003"),
        "D": uuid.UUID("d0000000-0000-0000-0000-000000000004"),
        "E": uuid.UUID("e0000000-0000-0000-0000-000000000005"),
    }
    return mapping[name]


# ---------------------------------------------------------------------------
# Basic simulation — graph traversal
# ---------------------------------------------------------------------------

class TestSimulateChange:
    async def test_simulate_on_A_finds_direct_dependents_B_and_D(
        self,
        test_db: AsyncSession,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        """
        Changing rule A (which has downstream B and D) should report B and D
        as directly affected.
        """
        svc = RuleService(test_db)
        engine = SimulationEngine(rule_service=svc)

        result = await engine.simulate_change(
            tenant_id=str(sample_tenant.id),
            rule_id=_rule_id_for_name("A"),
            proposed_changes={"some_threshold": 95},
        )

        assert result is not None
        direct_ids = {r.rule_id for r in result.directly_affected}
        assert "SCN.NOTIFY.EMAIL" in direct_ids
        assert "SCN.AUDIT.LOG" in direct_ids

    async def test_simulate_on_A_finds_indirect_dependent_C(
        self,
        test_db: AsyncSession,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        """
        Changing A propagates to B (direct), and then to C via B (indirect).
        C should appear in indirectly_affected.
        """
        svc = RuleService(test_db)
        engine = SimulationEngine(rule_service=svc)

        result = await engine.simulate_change(
            tenant_id=str(sample_tenant.id),
            rule_id=_rule_id_for_name("A"),
            proposed_changes={"some_threshold": 95},
        )

        assert result is not None
        indirect_ids = {r.rule_id for r in result.indirectly_affected}
        assert "SCN.ESCALATE.PAGER" in indirect_ids

    async def test_simulate_on_A_does_not_include_E(
        self,
        test_db: AsyncSession,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        """Standalone rule E is not downstream of A and must not appear in results."""
        svc = RuleService(test_db)
        engine = SimulationEngine(rule_service=svc)

        result = await engine.simulate_change(
            tenant_id=str(sample_tenant.id),
            rule_id=_rule_id_for_name("A"),
            proposed_changes={},
        )

        assert result is not None
        all_ids = {r.rule_id for r in result.directly_affected + result.indirectly_affected}
        assert "SCN.STANDALONE.CLEANUP" not in all_ids

    async def test_simulate_on_C_has_no_downstream(
        self,
        test_db: AsyncSession,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        """Rule C is a leaf node — no direct or indirect downstream impact."""
        svc = RuleService(test_db)
        engine = SimulationEngine(rule_service=svc)

        result = await engine.simulate_change(
            tenant_id=str(sample_tenant.id),
            rule_id=_rule_id_for_name("C"),
            proposed_changes={},
        )

        assert result is not None
        assert result.directly_affected == []
        assert result.indirectly_affected == []

    async def test_simulate_nonexistent_rule_returns_none(
        self,
        test_db: AsyncSession,
        sample_tenant: Tenant,
        sample_rules_with_graph: list[Rule],
    ) -> None:
        """simulate_change returns None for an unknown rule_id."""
        svc = RuleService(test_db)
        engine = SimulationEngine(rule_service=svc)

        result = await engine.simulate_change(
            tenant_id=str(sample_tenant.id),
            rule_id=uuid.uuid4(),   # random UUID not in DB
            proposed_changes={},
        )

        assert result is None


# ---------------------------------------------------------------------------
# Depth values in AffectedRule
# ---------------------------------------------------------------------------

class TestAffectedRuleDepth:
    async def test_direct_dependents_have_depth_1(
        self,
        test_db: AsyncSession,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        svc = RuleService(test_db)
        engine = SimulationEngine(rule_service=svc)

        result = await engine.simulate_change(
            tenant_id=str(sample_tenant.id),
            rule_id=_rule_id_for_name("A"),
            proposed_changes={},
        )

        assert result is not None
        for ar in result.directly_affected:
            assert ar.depth == 1
            assert ar.relationship == "direct"

    async def test_indirect_dependents_have_depth_greater_than_1(
        self,
        test_db: AsyncSession,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        svc = RuleService(test_db)
        engine = SimulationEngine(rule_service=svc)

        result = await engine.simulate_change(
            tenant_id=str(sample_tenant.id),
            rule_id=_rule_id_for_name("A"),
            proposed_changes={},
        )

        assert result is not None
        for ar in result.indirectly_affected:
            assert ar.depth > 1
            assert ar.relationship == "indirect"


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------

class TestCycleDetection:
    async def test_cycle_does_not_cause_infinite_loop(
        self,
        test_db: AsyncSession,
        sample_tenant: Tenant,
    ) -> None:
        """
        If rules A and B reference each other (A→B, B→A), the engine must
        terminate without infinite recursion and set cycle_detected=True.
        """
        from app.models.rule import Rule

        rule_a = Rule(
            id=uuid.UUID("f0000000-0000-0000-0000-000000000001"),
            tenant_id=sample_tenant.id,
            rule_id="CYCLE.A",
            title="Cycle Rule A",
            status="active",
            risk_level="medium",
            customer_facing=False,
            cost_impact=False,
            verified=True,
            downstream_rule_ids=["CYCLE.B"],
            upstream_rule_ids=[],
            editable_fields=[],
            editable_field_values={},
        )
        rule_b = Rule(
            id=uuid.UUID("f0000000-0000-0000-0000-000000000002"),
            tenant_id=sample_tenant.id,
            rule_id="CYCLE.B",
            title="Cycle Rule B",
            status="active",
            risk_level="medium",
            customer_facing=False,
            cost_impact=False,
            verified=True,
            downstream_rule_ids=["CYCLE.A"],   # back-edge → cycle
            upstream_rule_ids=[],
            editable_fields=[],
            editable_field_values={},
        )
        test_db.add(rule_a)
        test_db.add(rule_b)
        await test_db.commit()
        await test_db.refresh(rule_a)
        await test_db.refresh(rule_b)

        svc = RuleService(test_db)
        engine = SimulationEngine(rule_service=svc)

        result = await engine.simulate_change(
            tenant_id=str(sample_tenant.id),
            rule_id=rule_a.id,
            proposed_changes={},
        )

        assert result is not None
        assert result.cycle_detected is True

    async def test_self_referencing_rule_detected_as_cycle(
        self,
        test_db: AsyncSession,
        sample_tenant: Tenant,
    ) -> None:
        """A rule that lists itself as a downstream dependency is caught as a cycle."""
        from app.models.rule import Rule

        self_ref = Rule(
            id=uuid.UUID("f1000000-0000-0000-0000-000000000001"),
            tenant_id=sample_tenant.id,
            rule_id="SELF.REF",
            title="Self Referencing Rule",
            status="active",
            risk_level="low",
            customer_facing=False,
            cost_impact=False,
            verified=True,
            downstream_rule_ids=["SELF.REF"],  # references itself
            upstream_rule_ids=[],
            editable_fields=[],
            editable_field_values={},
        )
        test_db.add(self_ref)
        await test_db.commit()
        await test_db.refresh(self_ref)

        svc = RuleService(test_db)
        engine = SimulationEngine(rule_service=svc)

        result = await engine.simulate_change(
            tenant_id=str(sample_tenant.id),
            rule_id=self_ref.id,
            proposed_changes={},
        )

        assert result is not None
        assert result.cycle_detected is True


# ---------------------------------------------------------------------------
# Risk aggregation
# ---------------------------------------------------------------------------

class TestRiskAggregation:
    async def test_aggregate_risk_reflects_highest_risk_in_chain(
        self,
        test_db: AsyncSession,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        """
        In the A→B→C chain, C is risk=critical. Simulating A should report
        aggregate_risk=critical.
        """
        svc = RuleService(test_db)
        engine = SimulationEngine(rule_service=svc)

        result = await engine.simulate_change(
            tenant_id=str(sample_tenant.id),
            rule_id=_rule_id_for_name("A"),
            proposed_changes={},
        )

        assert result is not None
        assert result.aggregate_risk == "critical"

    async def test_aggregate_risk_is_low_when_no_affected_rules(
        self,
        test_db: AsyncSession,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        """With no downstream rules, aggregate_risk defaults to 'low'."""
        svc = RuleService(test_db)
        engine = SimulationEngine(rule_service=svc)

        result = await engine.simulate_change(
            tenant_id=str(sample_tenant.id),
            rule_id=_rule_id_for_name("C"),  # leaf node
            proposed_changes={},
        )

        assert result is not None
        assert result.aggregate_risk == "low"


# ---------------------------------------------------------------------------
# Warnings
# ---------------------------------------------------------------------------

class TestWarnings:
    async def test_warning_for_customer_facing_downstream(
        self,
        test_db: AsyncSession,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        """
        Rule B is customer_facing=True.  Simulating A should include a warning
        about downstream customer-facing impact.
        """
        svc = RuleService(test_db)
        engine = SimulationEngine(rule_service=svc)

        result = await engine.simulate_change(
            tenant_id=str(sample_tenant.id),
            rule_id=_rule_id_for_name("A"),
            proposed_changes={},
        )

        assert result is not None
        warning_text = " ".join(result.warnings).lower()
        assert "customer" in warning_text or "customer-facing" in warning_text

    async def test_warning_for_unverified_downstream(
        self,
        test_db: AsyncSession,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        """
        Rule C is verified=False. Simulating A (which reaches C indirectly)
        should emit a warning about unverified downstream rules.
        """
        svc = RuleService(test_db)
        engine = SimulationEngine(rule_service=svc)

        result = await engine.simulate_change(
            tenant_id=str(sample_tenant.id),
            rule_id=_rule_id_for_name("A"),
            proposed_changes={},
        )

        assert result is not None
        warning_text = " ".join(result.warnings).lower()
        assert "unverified" in warning_text

    async def test_warning_for_isolated_rule(
        self,
        test_db: AsyncSession,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        """
        Standalone rule E has no downstream. The engine should emit a note
        that no downstream impact was detected.
        """
        svc = RuleService(test_db)
        engine = SimulationEngine(rule_service=svc)

        result = await engine.simulate_change(
            tenant_id=str(sample_tenant.id),
            rule_id=_rule_id_for_name("E"),
            proposed_changes={},
        )

        assert result is not None
        warning_text = " ".join(result.warnings).lower()
        assert "no downstream" in warning_text or "isolated" in warning_text

    async def test_warning_for_paused_downstream(
        self,
        test_db: AsyncSession,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        """
        Rule D is paused. Simulating A should include a paused downstream warning.
        """
        svc = RuleService(test_db)
        engine = SimulationEngine(rule_service=svc)

        result = await engine.simulate_change(
            tenant_id=str(sample_tenant.id),
            rule_id=_rule_id_for_name("A"),
            proposed_changes={},
        )

        assert result is not None
        warning_text = " ".join(result.warnings).lower()
        assert "paused" in warning_text


# ---------------------------------------------------------------------------
# SimulationResult.to_dict
# ---------------------------------------------------------------------------

class TestSimulationResultToDict:
    async def test_to_dict_has_required_keys(
        self,
        test_db: AsyncSession,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        """to_dict() includes all documented fields for the API response."""
        svc = RuleService(test_db)
        engine = SimulationEngine(rule_service=svc)

        result = await engine.simulate_change(
            tenant_id=str(sample_tenant.id),
            rule_id=_rule_id_for_name("A"),
            proposed_changes={"threshold": 90},
        )

        assert result is not None
        d = result.to_dict()
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
            assert key in d, f"Missing key in SimulationResult.to_dict(): {key!r}"

    async def test_impact_summary_counts(
        self,
        test_db: AsyncSession,
        sample_rules_with_graph: list[Rule],
        sample_tenant: Tenant,
    ) -> None:
        """impact_summary aggregates affected rule counts correctly."""
        svc = RuleService(test_db)
        engine = SimulationEngine(rule_service=svc)

        result = await engine.simulate_change(
            tenant_id=str(sample_tenant.id),
            rule_id=_rule_id_for_name("A"),
            proposed_changes={},
        )

        assert result is not None
        summary = result.to_dict()["impact_summary"]
        total = summary["total_affected"]
        direct = summary["directly_affected_count"]
        indirect = summary["indirectly_affected_count"]
        assert total == direct + indirect
