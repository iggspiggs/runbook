"""
runbook_sdk.models
==================

Pydantic v2 models that mirror the Runbook API's rule schema.

These models serve three purposes:

1. **Validation** — ensure SDK-annotated rule dicts are well-formed before
   they reach the API.
2. **Serialisation** — produce the exact JSON payload the API expects via
   ``model.model_dump(mode="json")``.
3. **Documentation** — act as the canonical source of truth for the
   Rule contract between the SDK and the backend.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Shared enums-as-literals ──────────────────────────────────────────────────

RiskLevel = Literal["low", "medium", "high", "critical"]
RuleStatus = Literal["active", "paused", "planned", "deferred"]
FieldType = Literal["string", "number", "boolean", "select", "list", "email", "json"]
EditableBy = Literal["operator", "admin", "dev"]
ActorType = Literal["human", "ai_agent", "automated", "external"]


# ── EditableField ─────────────────────────────────────────────────────────────


class FieldValidation(BaseModel):
    """
    Optional constraints on an editable field value.

    At least one constraint key should be present, but the model accepts any
    combination so the schema can evolve without breaking old SDK versions.
    """

    min: Optional[float] = Field(None, description="Minimum numeric value (inclusive)")
    max: Optional[float] = Field(None, description="Maximum numeric value (inclusive)")
    options: Optional[list[Any]] = Field(
        None, description="Allowed values for 'select' type fields"
    )
    pattern: Optional[str] = Field(
        None, description="Regex pattern the value must match"
    )
    max_items: Optional[int] = Field(
        None, alias="maxItems", description="Maximum list length"
    )

    model_config = {"populate_by_name": True, "extra": "allow"}


class EditableField(BaseModel):
    """
    A single operator-tunable parameter within a rule.

    These fields are surfaced in the Runbook dashboard as form controls.
    All changes are audit-logged and may be subject to approval workflows
    depending on the rule's ``risk_level``.
    """

    field_name: str = Field(
        ...,
        description="Name of the variable or config key being exposed",
        examples=["threshold", "cc_list", "retry_delay_seconds"],
    )
    field_type: FieldType = Field(
        ...,
        description="Data type that determines the dashboard widget",
    )
    current: Any = Field(
        ...,
        description="Live / currently-active value of this parameter",
    )
    default: Any = Field(
        ...,
        description="The value baked into code at annotation time",
    )
    description: str = Field(
        ...,
        description="One-sentence explanation shown to the operator",
    )
    editable_by: EditableBy = Field(
        "operator",
        description="Minimum role required to change this field",
    )
    validation: Optional[FieldValidation] = Field(
        None,
        description="Optional min/max/options/pattern constraints",
    )

    @field_validator("field_name")
    @classmethod
    def field_name_snake_case(cls, v: str) -> str:
        """Enforce snake_case to keep field names consistent across languages."""
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError(
                f"field_name must be alphanumeric with underscores/hyphens, got: {v!r}"
            )
        return v

    model_config = {"populate_by_name": True}


# ── Actor ─────────────────────────────────────────────────────────────────────


class Actor(BaseModel):
    """Describes who or what executes a rule."""

    type: ActorType = Field(..., description="Category of actor")
    name: str = Field(..., description="Display name of the actor")
    role: Optional[str] = Field(None, description="Optional role descriptor")

    model_config = {"extra": "allow"}


# ── RuleDefinition ────────────────────────────────────────────────────────────


class RuleDefinition(BaseModel):
    """
    Complete definition of a single automation rule.

    This is the canonical transfer object between the SDK and the API.
    It maps 1-to-1 to the ``Rule`` SQLAlchemy model in the backend.

    Rule ID convention
    ------------------
    ``DEPARTMENT.SUBSYSTEM.SPECIFIC`` — all caps, dot-separated.
    Examples:
    - ``"SCN.RECIPIENTS.HIGH_VALUE_CC"``
    - ``"BILLING.INVOICES.OVERDUE_ESCALATION"``
    - ``"OPS.INVENTORY.LOW_STOCK_ALERT"``
    """

    # ── Identity ──────────────────────────────────────────────────────────────
    rule_id: str = Field(
        ...,
        description=(
            "Stable, human-readable identifier. "
            "Convention: DEPARTMENT.SUBSYSTEM.SPECIFIC"
        ),
        examples=["SCN.RECIPIENTS.HIGH_VALUE_CC"],
        min_length=1,
        max_length=255,
    )
    title: str = Field(
        ...,
        description="Short name displayed in the dashboard",
        min_length=1,
        max_length=500,
    )
    description: Optional[str] = Field(
        None,
        description="Longer explanation of what this rule does",
    )
    why: Optional[str] = Field(
        None,
        description="Business justification — why does this rule exist?",
    )

    # ── Organisational metadata ───────────────────────────────────────────────
    department: Optional[str] = Field(
        None,
        description="Owning department",
        examples=["shipping", "finance", "operations"],
    )
    subsystem: Optional[str] = Field(
        None,
        description="Sub-component within the department",
        examples=["notifications", "billing", "inventory"],
    )
    owner: Optional[str] = Field(
        None,
        description="Team or person responsible for this rule",
    )
    tags: Optional[list[str]] = Field(
        default_factory=list,
        description="Free-form tags for filtering/grouping",
    )

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    status: RuleStatus = Field("active", description="Current lifecycle status")

    # ── Behaviour ─────────────────────────────────────────────────────────────
    trigger: Optional[str] = Field(
        None,
        description="What event or condition kicks this rule off",
        examples=["contract_value > threshold", "every day at 08:00 UTC"],
    )
    conditions: Optional[dict[str, Any]] = Field(
        None,
        description="Structured conditions under which the rule applies",
    )
    actions: Optional[dict[str, Any]] = Field(
        None,
        description="What the rule does when triggered",
    )
    actors: Optional[list[Actor]] = Field(
        None,
        description="Who or what executes this rule",
    )

    # ── Editable parameters ───────────────────────────────────────────────────
    editable: Optional[list[EditableField]] = Field(
        default_factory=list,
        description="Parameters operators may tune without touching code",
    )

    # ── Dependency graph ──────────────────────────────────────────────────────
    upstream: Optional[list[str]] = Field(
        default_factory=list,
        description="rule_ids whose output feeds into this rule",
    )
    downstream: Optional[list[str]] = Field(
        default_factory=list,
        description="rule_ids that depend on this rule",
    )

    # ── Source provenance ─────────────────────────────────────────────────────
    source_file: Optional[str] = Field(
        None,
        description="Relative path to the source file this rule was extracted from",
    )
    source_lines: Optional[dict[str, int]] = Field(
        None,
        description='{"start": int, "end": int} line numbers in source_file',
    )
    source_module: Optional[str] = Field(
        None,
        description="Fully qualified Python module name",
    )
    confidence: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="0.0–1.0 extraction confidence score assigned by the LLM",
    )

    # ── Risk and impact ───────────────────────────────────────────────────────
    risk_level: Optional[RiskLevel] = Field(
        None,
        description="Blast-radius assessment",
    )
    cost_impact: Optional[str] = Field(
        None,
        description="Free-text description of financial implications",
    )
    customer_facing: Optional[bool] = Field(
        None,
        description="True if this rule has a direct customer-visible effect",
    )

    # ── Extra metadata ────────────────────────────────────────────────────────
    metadata_extra: Optional[dict[str, Any]] = Field(
        None,
        alias="metadata",
        description="Arbitrary extra metadata",
    )

    @field_validator("rule_id")
    @classmethod
    def rule_id_format(cls, v: str) -> str:
        """
        Validate that rule_id follows the DEPARTMENT.SUBSYSTEM.SPECIFIC
        convention (all uppercase, dot-separated segments of [A-Z0-9_]).

        Enforced as a warning rather than an error so that auto-extracted IDs
        from LLM output can still be ingested pending normalisation.
        """
        import re
        import warnings

        if not re.match(r"^[A-Z0-9_]+(\.[A-Z0-9_]+)*$", v):
            warnings.warn(
                f"rule_id {v!r} does not follow the DEPT.SUB.NAME convention. "
                "Consider normalising to uppercase dot-notation.",
                UserWarning,
                stacklevel=2,
            )
        return v

    @model_validator(mode="after")
    def editable_types_consistent(self) -> "RuleDefinition":
        """
        Cross-field check: 'select' fields must supply validation.options.
        """
        for field in self.editable or []:
            if field.field_type == "select" and (
                field.validation is None or not field.validation.options
            ):
                raise ValueError(
                    f"EditableField '{field.field_name}' has type 'select' but "
                    "no validation.options were provided."
                )
        return self

    model_config = {"populate_by_name": True}


# ── ExtractionResult ──────────────────────────────────────────────────────────


class ExtractionMetadata(BaseModel):
    """Provenance and quality metadata for a single extraction run."""

    scanner_version: str = Field(..., description="Version of the scanner that ran")
    llm_model: Optional[str] = Field(
        None,
        description="LLM model identifier used for extraction",
    )
    scanned_at: datetime = Field(
        ...,
        description="UTC timestamp of when the scan completed",
    )
    files_scanned: int = Field(
        0,
        ge=0,
        description="Total number of source files processed",
    )
    chunks_analysed: int = Field(
        0,
        ge=0,
        description="Number of code chunks sent to the LLM",
    )
    total_tokens_used: Optional[int] = Field(
        None,
        description="Total LLM tokens consumed across the extraction run",
    )
    git_commit: Optional[str] = Field(
        None,
        description="Git SHA of the HEAD commit at scan time",
    )
    git_branch: Optional[str] = Field(
        None,
        description="Git branch name at scan time",
    )
    repo_path: Optional[str] = Field(
        None,
        description="Absolute or relative path to the scanned repository root",
    )


class ExtractionResult(BaseModel):
    """
    The full output of a codebase extraction run.

    Returned by the extractor service and stored as the basis for a
    human-review session in the Runbook dashboard.
    """

    rules: list[RuleDefinition] = Field(
        ...,
        description="All rules discovered during this extraction run",
    )
    metadata: ExtractionMetadata = Field(
        ...,
        description="Run-level provenance and quality metrics",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal issues encountered during extraction",
    )
    skipped_files: list[str] = Field(
        default_factory=list,
        description="Files that were skipped due to errors or exclusion rules",
    )

    @property
    def rule_count(self) -> int:
        """Number of rules extracted in this run."""
        return len(self.rules)

    @property
    def avg_confidence(self) -> Optional[float]:
        """
        Mean extraction confidence across rules that have a confidence score.
        Returns ``None`` if no rules have been scored.
        """
        scored = [r.confidence for r in self.rules if r.confidence is not None]
        if not scored:
            return None
        return sum(scored) / len(scored)

    def rules_by_risk(self) -> dict[str, list[RuleDefinition]]:
        """
        Group rules by ``risk_level``.

        Returns
        -------
        dict
            Keys are risk level strings (plus ``"unset"`` for rules with no
            assigned risk level), values are lists of ``RuleDefinition``.
        """
        groups: dict[str, list[RuleDefinition]] = {}
        for r in self.rules:
            key = r.risk_level or "unset"
            groups.setdefault(key, []).append(r)
        return groups

    def rules_by_department(self) -> dict[str, list[RuleDefinition]]:
        """Group rules by ``department``."""
        groups: dict[str, list[RuleDefinition]] = {}
        for r in self.rules:
            key = r.department or "unassigned"
            groups.setdefault(key, []).append(r)
        return groups

    model_config = {"populate_by_name": True}
