"""
SimulationEngine — what-if impact analysis for proposed rule edits.

When an operator wants to change a rule's editable field (e.g., raise an
alert threshold from 80% to 95%), this engine answers:
  "If I make this change, what else in the system will be affected?"

It does NOT persist any changes. It is purely a read/analysis path.

Impact tracing algorithm:
  1. Start from the target rule's downstream_rule_ids (direct dependents).
  2. Recursively walk each dependent's downstream_rule_ids up to max_depth.
  3. Collect a set of "directly affected" (depth=1) and "indirectly affected" (depth>1) rules.
  4. Aggregate risk: worst-case risk_level across all affected rules.
  5. Generate human-readable warnings for high-risk signals:
     - Any affected rule that is customer_facing
     - Any affected rule that has cost_impact
     - Any affected rule that is not yet verified
     - Cycles detected in the graph
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
import uuid

from app.services.registry.rule_service import RuleService

logger = logging.getLogger(__name__)

_RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
_RISK_LABELS = {v: k for k, v in _RISK_ORDER.items()}
_DEFAULT_MAX_DEPTH = 10


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------

@dataclass
class AffectedRule:
    rule_id: str
    title: str
    status: str
    risk_level: str
    customer_facing: bool
    cost_impact: bool
    verified: bool
    depth: int                      # hops from the changed rule
    relationship: str               # "direct" | "indirect"

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class SimulationResult:
    target_rule_id: str
    target_rule_title: str
    proposed_changes: Dict[str, Any]
    directly_affected: List[AffectedRule] = field(default_factory=list)
    indirectly_affected: List[AffectedRule] = field(default_factory=list)
    aggregate_risk: str = "low"
    warnings: List[str] = field(default_factory=list)
    cycle_detected: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_rule_id": self.target_rule_id,
            "target_rule_title": self.target_rule_title,
            "proposed_changes": self.proposed_changes,
            "aggregate_risk": self.aggregate_risk,
            "cycle_detected": self.cycle_detected,
            "warnings": self.warnings,
            "directly_affected": [r.to_dict() for r in self.directly_affected],
            "indirectly_affected": [r.to_dict() for r in self.indirectly_affected],
            "impact_summary": {
                "total_affected": len(self.directly_affected) + len(self.indirectly_affected),
                "directly_affected_count": len(self.directly_affected),
                "indirectly_affected_count": len(self.indirectly_affected),
                "customer_facing_affected": sum(
                    1 for r in (self.directly_affected + self.indirectly_affected)
                    if r.customer_facing
                ),
                "cost_impact_affected": sum(
                    1 for r in (self.directly_affected + self.indirectly_affected)
                    if r.cost_impact
                ),
                "unverified_affected": sum(
                    1 for r in (self.directly_affected + self.indirectly_affected)
                    if not r.verified
                ),
            },
        }


# ---------------------------------------------------------------------------
# SimulationEngine
# ---------------------------------------------------------------------------

class SimulationEngine:
    def __init__(self, rule_service: RuleService) -> None:
        self._svc = rule_service
        self._rule_cache: Dict[str, Any] = {}   # rule_id → Rule ORM object

    async def simulate_change(
        self,
        tenant_id: str,
        rule_id: uuid.UUID,
        proposed_changes: Dict[str, Any],
    ) -> Optional[SimulationResult]:
        """
        Trace the downstream impact of proposed_changes on rule_id.
        Returns None if the rule does not exist.
        """
        # Load all tenant rules into the cache for efficient graph traversal
        await self._warm_cache(tenant_id)

        # The cache is keyed by rule.rule_id (string business key).
        # rule_id here is the UUID db primary key; look up by rule_id string
        # after warming the cache, which maps rule.rule_id → rule ORM object.
        # We need to find the rule whose db UUID matches the requested rule_id.
        target = None
        for cached_rule in self._rule_cache.values():
            if str(cached_rule.id) == str(rule_id):
                target = cached_rule
                break
        if target is None:
            return None

        visited: Set[str] = set()
        directly_affected: List[AffectedRule] = []
        indirectly_affected: List[AffectedRule] = []
        cycle_detected = False

        target_business_id = target.rule_id

        # Trace downstream from direct dependents.
        # downstream_rule_ids contains string rule_id business keys; the cache
        # is keyed by rule.rule_id so lookups are direct.
        for downstream_rid in (target.downstream_rule_ids or []):
            if downstream_rid == target_business_id:
                cycle_detected = True
                continue
            direct_rule = self._rule_cache.get(downstream_rid)
            if direct_rule is None:
                continue

            affected = AffectedRule(
                rule_id=direct_rule.rule_id,
                title=direct_rule.title,
                status=direct_rule.status,
                risk_level=direct_rule.risk_level,
                customer_facing=direct_rule.customer_facing,
                cost_impact=direct_rule.cost_impact,
                verified=direct_rule.verified,
                depth=1,
                relationship="direct",
            )
            directly_affected.append(affected)
            visited.add(downstream_rid)

            # Now walk further downstream from this direct dependent
            sub_affected, sub_cycle = self._trace_downstream(
                rule_id=downstream_rid,
                start_rule_id=target_business_id,
                depth=2,
                max_depth=_DEFAULT_MAX_DEPTH,
                visited=visited,
            )
            indirectly_affected.extend(sub_affected)
            if sub_cycle:
                cycle_detected = True

        aggregate_risk = self._assess_risk(directly_affected + indirectly_affected)
        warnings = self._build_warnings(
            target=target,
            proposed_changes=proposed_changes,
            directly_affected=directly_affected,
            indirectly_affected=indirectly_affected,
            cycle_detected=cycle_detected,
        )

        return SimulationResult(
            target_rule_id=target.rule_id,
            target_rule_title=target.title,
            proposed_changes=proposed_changes,
            directly_affected=directly_affected,
            indirectly_affected=indirectly_affected,
            aggregate_risk=aggregate_risk,
            warnings=warnings,
            cycle_detected=cycle_detected,
        )

    # ------------------------------------------------------------------
    # Internal graph traversal
    # ------------------------------------------------------------------

    def _trace_downstream(
        self,
        rule_id: str,
        start_rule_id: str,
        depth: int,
        max_depth: int,
        visited: Set[str],
    ) -> tuple[List[AffectedRule], bool]:
        """
        Recursively walk downstream edges. Returns (affected_rules, cycle_detected).
        """
        if depth > max_depth:
            return [], False

        rule = self._rule_cache.get(rule_id)
        if rule is None:
            return [], False

        results: List[AffectedRule] = []
        cycle = False

        for downstream_rid in (rule.downstream_rule_ids or []):
            # downstream_rule_ids stores string rule_id business keys
            if downstream_rid == start_rule_id:
                cycle = True
                continue
            if downstream_rid in visited:
                continue

            downstream_rule = self._rule_cache.get(downstream_rid)
            if downstream_rule is None:
                continue

            visited.add(downstream_rid)
            results.append(AffectedRule(
                rule_id=downstream_rule.rule_id,
                title=downstream_rule.title,
                status=downstream_rule.status,
                risk_level=downstream_rule.risk_level,
                customer_facing=downstream_rule.customer_facing,
                cost_impact=downstream_rule.cost_impact,
                verified=downstream_rule.verified,
                depth=depth,
                relationship="indirect",
            ))

            sub_results, sub_cycle = self._trace_downstream(
                rule_id=downstream_rid,
                start_rule_id=start_rule_id,
                depth=depth + 1,
                max_depth=max_depth,
                visited=visited,
            )
            results.extend(sub_results)
            if sub_cycle:
                cycle = True

        return results, cycle

    # ------------------------------------------------------------------
    # Risk assessment
    # ------------------------------------------------------------------

    def _assess_risk(self, affected_rules: List[AffectedRule]) -> str:
        """
        Return the highest risk level across all affected rules.
        Defaults to "low" if no rules are affected.
        """
        if not affected_rules:
            return "low"
        max_score = max(
            _RISK_ORDER.get(r.risk_level, 0) for r in affected_rules
        )
        return _RISK_LABELS.get(max_score, "low")

    # ------------------------------------------------------------------
    # Warning generation
    # ------------------------------------------------------------------

    def _build_warnings(
        self,
        target: Any,
        proposed_changes: Dict[str, Any],
        directly_affected: List[AffectedRule],
        indirectly_affected: List[AffectedRule],
        cycle_detected: bool,
    ) -> List[str]:
        warnings: List[str] = []
        all_affected = directly_affected + indirectly_affected

        # Target rule warnings
        if target.risk_level in ("high", "critical"):
            warnings.append(
                f"The rule being changed is risk level '{target.risk_level}'. "
                "Consider requesting peer review before applying."
            )
        if not target.verified:
            warnings.append(
                "This rule has not been human-verified. Its documented behavior "
                "may not match the actual implementation."
            )
        if target.customer_facing:
            warnings.append(
                "This rule directly affects customers. A misconfigured change "
                "could impact user experience or trust."
            )
        if target.cost_impact:
            warnings.append(
                "This rule has a documented cost impact. Changing its parameters "
                "may increase or decrease operational costs."
            )

        # Downstream warnings
        customer_facing = [r for r in all_affected if r.customer_facing]
        if customer_facing:
            titles = ", ".join(r.title for r in customer_facing[:3])
            extra = f" (+{len(customer_facing) - 3} more)" if len(customer_facing) > 3 else ""
            warnings.append(
                f"{len(customer_facing)} downstream rule(s) are customer-facing: {titles}{extra}."
            )

        cost_impact = [r for r in all_affected if r.cost_impact]
        if cost_impact:
            warnings.append(
                f"{len(cost_impact)} downstream rule(s) have cost implications. "
                "Review cascading effects carefully."
            )

        unverified = [r for r in all_affected if not r.verified]
        if unverified:
            warnings.append(
                f"{len(unverified)} downstream rule(s) are unverified. Their "
                "response to upstream changes is uncertain."
            )

        paused = [r for r in all_affected if r.status == "paused"]
        if paused:
            warnings.append(
                f"{len(paused)} downstream rule(s) are currently paused. They "
                "will not react until re-activated, but may resume with new parameters."
            )

        if cycle_detected:
            warnings.append(
                "A dependency cycle was detected in the rule graph. Circular "
                "dependencies can cause unpredictable cascading behavior."
            )

        if not all_affected:
            warnings.append(
                "No downstream rules detected. This change appears to be isolated, "
                "but verify manually if this rule feeds data to other systems."
            )

        return warnings

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    async def _warm_cache(self, tenant_id: str) -> None:
        """Load all tenant rules into an in-memory dict for O(1) lookups."""
        if self._rule_cache:
            return   # Already warmed for this request (single-request lifetime)

        rules, _ = await self._svc.get_rules({
            "tenant_id": tenant_id,
            "limit": 10_000,
            "offset": 0,
        })
        for rule in rules:
            # Key by the string business rule_id so downstream_rule_ids lookups
            # (which also carry string rule_id values) resolve correctly.
            self._rule_cache[rule.rule_id] = rule
