from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base, GUID, TimestampMixin, UUIDMixin

# ── Status values ────────────────────────────────────────────────────────────
STATUS_ACTIVE = "active"
STATUS_PAUSED = "paused"
STATUS_PLANNED = "planned"
STATUS_DEFERRED = "deferred"
STATUS_DRAFT = "draft"
VALID_STATUSES = {STATUS_ACTIVE, STATUS_PAUSED, STATUS_PLANNED, STATUS_DEFERRED, STATUS_DRAFT}

# ── Risk levels ──────────────────────────────────────────────────────────────
RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"
RISK_CRITICAL = "critical"
VALID_RISK_LEVELS = {RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_CRITICAL}


class Rule(UUIDMixin, TimestampMixin, Base):
    """
    Core registry rule — the heart of the product.

    A Rule represents a single, named piece of automated system behaviour
    extracted from a codebase (or entered manually).  Operators can view
    every rule's trigger, conditions, actions, and editable parameters, and
    safely change values within their permitted bounds without touching code.

    Column reference
    ────────────────
    rule_id           Human-readable, stable identifier scoped to the tenant.
                      Convention:  SUBSYSTEM.CATEGORY.NAME
                      Example:     "SCN.RECIPIENTS.HIGH_VALUE_CC"

    slug              URL-safe alternate identifier; populated from rule_id on
                      extraction import.  Nullable for legacy / manually created
                      rules.

    editable_fields   JSON array describing which fields operators may tune.
                      Each element:
                      {
                        "name":          str,
                        "type":          "str" | "int" | "float" | "bool" | "list" | "email_list",
                        "current":       <any>,
                        "default":       <any>,
                        "description":   str,
                        "editable_by":   "operator" | "admin" | "dev",
                        "min_value":     num  (optional),
                        "max_value":     num  (optional),
                        "allowed_values": list (optional)
                      }

    editable_field_values   JSON object that stores the operator-set values
                            separately from the field definitions.  This lets
                            re-scans update the field definitions without
                            clobbering operator overrides.
                            { "field_name": <operator_value>, ... }

    actors            JSON array describing who/what executes this rule.
                      Each element:
                      {
                        "type":  "human" | "ai_agent" | "automated" | "external",
                        "name":  str,
                        "role":  str (optional)
                      }

    upstream_rule_ids /   Arrays of rule_id strings — used to render the
    downstream_rule_ids   dependency graph and assess blast radius before an edit.

    source_content    The raw source code snippet this rule was extracted from.

    language          Programming language of the source file (e.g. "python").
    """

    __tablename__ = "rules"

    __table_args__ = (
        UniqueConstraint("tenant_id", "rule_id", name="uq_rules_tenant_rule_id"),
    )

    # ── Ownership ────────────────────────────────────────────────────────────
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant: Mapped["Tenant"] = relationship(  # noqa: F821
        "Tenant",
        back_populates="rules",
    )

    # ── Identity ─────────────────────────────────────────────────────────────
    rule_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Stable human-readable ID scoped to tenant, e.g. SCN.RECIPIENTS.HIGH_VALUE_CC",
    )
    slug: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="URL-safe alternate identifier; populated from rule_id on extraction import",
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    why: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Business justification — why does this rule exist?",
    )

    # ── Organisational metadata ──────────────────────────────────────────────
    department: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    subsystem: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    owner: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Team or person responsible for this rule",
    )
    tags: Mapped[Optional[list[str]]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Free-form tags for filtering/grouping",
    )

    # ── Lifecycle ────────────────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=STATUS_ACTIVE,
        comment="active | paused | planned | deferred | draft",
    )

    # ── Behaviour definition ─────────────────────────────────────────────────
    trigger: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="What event or condition kicks this rule off",
    )
    conditions: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Structured conditions under which the rule applies",
    )
    actions: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="What the rule does when triggered",
    )
    actors: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Who or what executes this rule (human / ai_agent / automated / external)",
    )

    # ── Editable parameters ──────────────────────────────────────────────────
    editable_fields: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="Field definitions that operators may tune without touching code",
    )
    editable_field_values: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
        comment="Operator-set overrides keyed by field name; preserved across re-scans",
    )

    # ── Dependency graph ─────────────────────────────────────────────────────
    upstream_rule_ids: Mapped[Optional[list[str]]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="rule_ids whose output feeds into this rule",
    )
    downstream_rule_ids: Mapped[Optional[list[str]]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="rule_ids that depend on this rule",
    )

    # ── Source provenance ────────────────────────────────────────────────────
    source_file: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True,
        comment="Relative path to the source file this rule was extracted from",
    )
    source_start_line: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="First line number in source_file where this rule appears",
    )
    source_end_line: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Last line number in source_file where this rule appears",
    )
    source_content: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Raw source code snippet this rule was extracted from",
    )
    language: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Programming language of the source file, e.g. 'python'",
    )
    confidence: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="0.0–1.0 extraction confidence score assigned by the LLM",
    )

    # ── Verification ─────────────────────────────────────────────────────────
    verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True once a human has reviewed and confirmed this extraction",
    )
    verified_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Identity of the person who verified this rule",
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when the rule was verified",
    )

    # ── Risk and impact ──────────────────────────────────────────────────────
    risk_level: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="low | medium | high | critical",
    )
    cost_impact: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Free-text description of cost implications",
    )
    customer_facing: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
        comment="True if this rule has a direct customer-visible effect",
    )

    # ── Change tracking ──────────────────────────────────────────────────────
    last_changed: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_changed_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    # ── Catch-all ────────────────────────────────────────────────────────────
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
        default=dict,
        comment="Arbitrary extra metadata; use sparingly",
    )

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """
        Return a JSON-safe dict of all columns.

        Handles:
        - datetime  → ISO-8601 string
        - UUID      → string
        - None      → None (preserved)
        - metadata_ → exposed as "metadata" (matches the DB column name)
        """
        def _serialize(value: Any) -> Any:
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, uuid.UUID):
                return str(value)
            return value

        return {
            "id": _serialize(self.id),
            "tenant_id": _serialize(self.tenant_id),
            "rule_id": self.rule_id,
            "slug": self.slug,
            "title": self.title,
            "description": self.description,
            "why": self.why,
            "department": self.department,
            "subsystem": self.subsystem,
            "owner": self.owner,
            "tags": self.tags,
            "status": self.status,
            "trigger": self.trigger,
            "conditions": self.conditions,
            "actions": self.actions,
            "actors": self.actors,
            "editable_fields": self.editable_fields,
            "editable_field_values": self.editable_field_values,
            "upstream_rule_ids": self.upstream_rule_ids,
            "downstream_rule_ids": self.downstream_rule_ids,
            "source_file": self.source_file,
            "source_start_line": self.source_start_line,
            "source_end_line": self.source_end_line,
            "source_content": self.source_content,
            "language": self.language,
            "confidence": self.confidence,
            "verified": self.verified,
            "verified_by": self.verified_by,
            "verified_at": _serialize(self.verified_at),
            "risk_level": self.risk_level,
            "cost_impact": self.cost_impact,
            "customer_facing": self.customer_facing,
            "last_changed": _serialize(self.last_changed),
            "last_changed_by": self.last_changed_by,
            "metadata": self.metadata_,
            "created_at": _serialize(self.created_at),
            "updated_at": _serialize(self.updated_at),
        }

    def __repr__(self) -> str:
        return (
            f"<Rule id={self.id!s:.8} "
            f"rule_id={self.rule_id!r} "
            f"status={self.status!r} "
            f"risk={self.risk_level!r}>"
        )
