"""
DriftDetector — compares the current state of a codebase against the
registered rules and produces a DriftReport describing what has changed.

This is the engine behind the "Drift" step in the Runbook core loop.
It answers: "Since we last scanned, has the code that backs our registered
rules actually changed?"

Drift categories:
  new_rules       — Found in current scan, not in the registry
  changed_rules   — In both, but source location or extracted content differs
  missing_rules   — In the registry, not found in current scan (possible deletion/move)
  unchanged_rules — In both and identical within tolerance

For changed rules a ChangeDetail diff is produced describing exactly
what shifted: source moved, logic changed, editable params changed, etc.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from app.services.extractor.scanner import CodebaseScanner, CodeChunk
from app.services.registry.rule_service import RuleService

logger = logging.getLogger(__name__)

_CONTENT_SIMILARITY_THRESHOLD = 0.85  # below this → "logic changed"


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------

@dataclass
class ChangeDetail:
    """Describes what specifically changed for a single rule."""
    rule_id: str
    rule_title: str
    source_moved: bool = False
    old_file: Optional[str] = None
    new_file: Optional[str] = None
    old_start_line: Optional[int] = None
    new_start_line: Optional[int] = None
    logic_changed: bool = False
    content_similarity: float = 1.0   # 0.0 = completely different, 1.0 = identical
    params_changed: bool = False       # editable field definitions changed
    added_params: List[str] = field(default_factory=list)
    removed_params: List[str] = field(default_factory=list)
    changed_param_types: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class DriftReport:
    tenant_id: str
    repo_path: str
    scanned_at: str                              # ISO-8601 timestamp
    new_rules: List[Dict[str, Any]] = field(default_factory=list)
    changed_rules: List[ChangeDetail] = field(default_factory=list)
    missing_rules: List[Dict[str, Any]] = field(default_factory=list)
    unchanged_rules: List[str] = field(default_factory=list)   # rule IDs

    @property
    def has_drift(self) -> bool:
        return bool(self.new_rules or self.changed_rules or self.missing_rules)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "repo_path": self.repo_path,
            "scanned_at": self.scanned_at,
            "has_drift": self.has_drift,
            "summary": {
                "new": len(self.new_rules),
                "changed": len(self.changed_rules),
                "missing": len(self.missing_rules),
                "unchanged": len(self.unchanged_rules),
            },
            "new_rules": self.new_rules,
            "changed_rules": [c.to_dict() for c in self.changed_rules],
            "missing_rules": self.missing_rules,
            "unchanged_rule_ids": self.unchanged_rules,
        }


# ---------------------------------------------------------------------------
# DriftDetector
# ---------------------------------------------------------------------------

class DriftDetector:
    """
    Usage:
        scanner  = CodebaseScanner(repo_path="/srv/repos/acme")
        detector = DriftDetector(scanner=scanner, registry=rule_service)
        report   = await detector.detect(tenant_id="acme", repo_path="/srv/repos/acme")
    """

    def __init__(self, scanner: CodebaseScanner, registry: RuleService) -> None:
        self._scanner = scanner
        self._registry = registry

    async def detect(self, tenant_id: str, repo_path: str) -> DriftReport:
        """
        Run a fresh scan and diff the results against the registered rules
        for the given tenant. Returns a DriftReport.
        """
        from datetime import datetime, timezone

        # 1. Fresh scan
        logger.info("DriftDetector: scanning %s for tenant %s", repo_path, tenant_id)
        chunks: List[CodeChunk] = self._scanner.scan()

        # 2. Load registered rules
        registered_rules, _ = await self._registry.get_rules({
            "tenant_id": tenant_id,
            "limit": 10_000,
            "offset": 0,
        })

        report = DriftReport(
            tenant_id=tenant_id,
            repo_path=repo_path,
            scanned_at=datetime.now(timezone.utc).isoformat(),
        )

        # 3. Build lookup structures
        # Registered rules indexed by (source_file, source_lines["start"])
        # source_lines is a JSON column: {"start": N, "end": N}
        reg_by_location: Dict[tuple, Any] = {
            (r.source_file, (r.source_lines or {}).get("start")): r
            for r in registered_rules
            if r.source_file and (r.source_lines or {}).get("start") is not None
        }
        # All registered business rule IDs
        reg_ids = {r.rule_id for r in registered_rules}

        # Scanned chunks indexed by (file_path, start_line)
        scanned_by_location: Dict[tuple, CodeChunk] = {
            (c.file_path, c.start_line): c for c in chunks
        }

        matched_reg_keys: set = set()

        # 4. For each scanned chunk, find the matching registered rule
        for loc_key, chunk in scanned_by_location.items():
            if loc_key in reg_by_location:
                # Exact location match — check for content drift
                registered = reg_by_location[loc_key]
                matched_reg_keys.add(loc_key)
                change = self._diff_rule(registered, chunk)
                if change is not None:
                    report.changed_rules.append(change)
                else:
                    report.unchanged_rules.append(registered.rule_id)
            else:
                # Not in registry at this location — could be a new rule or a moved rule
                moved_from = self._find_moved_rule(chunk, reg_by_location, matched_reg_keys)
                if moved_from is not None:
                    reg_key, registered = moved_from
                    matched_reg_keys.add(reg_key)
                    change = self._diff_rule(registered, chunk, moved=True)
                    if change is not None:
                        report.changed_rules.append(change)
                    else:
                        report.unchanged_rules.append(registered.rule_id)
                else:
                    # Genuinely new — convert chunk to a lightweight dict for the report
                    report.new_rules.append(chunk.to_dict())

        # 5. Any registered rule not matched in the scan is missing
        for loc_key, registered in reg_by_location.items():
            if loc_key not in matched_reg_keys:
                report.missing_rules.append({
                    "rule_id": registered.rule_id,
                    "title": registered.title,
                    "source_file": registered.source_file,
                    "source_start_line": (registered.source_lines or {}).get("start"),
                    "status": registered.status,
                })

        logger.info(
            "DriftDetector complete: %d new, %d changed, %d missing, %d unchanged",
            len(report.new_rules),
            len(report.changed_rules),
            len(report.missing_rules),
            len(report.unchanged_rules),
        )
        return report

    # ------------------------------------------------------------------
    # Diff helpers
    # ------------------------------------------------------------------

    def _diff_rule(
        self,
        registered: Any,
        chunk: CodeChunk,
        moved: bool = False,
    ) -> Optional[ChangeDetail]:
        """
        Compare a registered rule against the current chunk. Returns a
        ChangeDetail if any meaningful difference is found, else None.
        """
        detail = ChangeDetail(
            rule_id=registered.rule_id,
            rule_title=registered.title,
        )
        changed = False

        # source_lines is {"start": N, "end": N}; fall back gracefully if absent
        registered_start = (registered.source_lines or {}).get("start")

        # Source moved?
        if moved or registered.source_file != chunk.file_path:
            detail.source_moved = True
            detail.old_file = registered.source_file
            detail.new_file = chunk.file_path
            detail.old_start_line = registered_start
            detail.new_start_line = chunk.start_line
            changed = True

        # Logic changed? Compare stored source content to current chunk content.
        stored_content = getattr(registered, "source_content", "") or ""
        similarity = _text_similarity(stored_content, chunk.content)
        detail.content_similarity = round(similarity, 4)
        if stored_content and similarity < _CONTENT_SIMILARITY_THRESHOLD:
            detail.logic_changed = True
            changed = True

        # Editable params changed?
        # editable_fields items use field_name / field_type per the model spec.
        registered_params: Dict[str, str] = {
            ef["field_name"]: ef.get("field_type", "str")
            for ef in (registered.editable_fields or [])
        }
        # We don't have the freshly-extracted editable fields at this point
        # (that requires an LLM call). We flag params_changed as unknown here;
        # the full extraction + compare happens in commit workflow.
        # For now, compare what we can: if the registered params are non-empty
        # and the content similarity is low, flag it.
        if registered_params and detail.logic_changed:
            detail.params_changed = True
            changed = True

        return detail if changed else None

    def _find_moved_rule(
        self,
        chunk: CodeChunk,
        reg_by_location: Dict[tuple, Any],
        already_matched: set,
    ) -> Optional[tuple[tuple, Any]]:
        """
        Try to match a chunk to a registered rule at a different location
        using content similarity. Returns (reg_key, registered_rule) or None.
        """
        best_score = _CONTENT_SIMILARITY_THRESHOLD
        best_match: Optional[tuple[tuple, Any]] = None

        for loc_key, registered in reg_by_location.items():
            if loc_key in already_matched:
                continue
            stored_content = getattr(registered, "source_content", "") or ""
            if not stored_content:
                continue
            score = _text_similarity(stored_content, chunk.content)
            if score > best_score:
                best_score = score
                best_match = (loc_key, registered)

        return best_match


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text_similarity(a: str, b: str) -> float:
    """Ratio of matching characters between two strings (0.0–1.0)."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()
