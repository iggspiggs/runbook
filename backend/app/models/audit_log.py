from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base, GUID, UUIDMixin


class AuditAction(str, enum.Enum):
    """
    Exhaustive list of state transitions that are recorded for a rule.

    Using a Python enum ensures the set of valid actions is enforced at the
    application layer before any SQL is issued, giving readable error messages
    rather than a raw DB constraint violation.
    """

    CREATED = "created"
    UPDATED = "updated"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAUSED = "paused"
    ACTIVATED = "activated"
    # Actions produced by the service layer
    EDITABLE_UPDATE = "editable_update"
    STATUS_CHANGE = "status_change"
    VERIFY = "verify"
    EXTRACTION_CREATE = "extraction_create"
    EXTRACTION_UPDATE = "extraction_update"


class AuditLog(UUIDMixin, Base):
    """
    Immutable audit trail for all rule changes.

    Design decisions:
    - No TimestampMixin — there is only created_at; this record must never be
      modified after insert.  updated_at would be misleading and could give a
      false sense of integrity.
    - old_value / new_value stored as JSON so we can diff any field type
      without schema migrations when the Rule model evolves.
    - field_name is nullable because some actions (created, approved, rejected)
      apply to the whole rule, not a specific field.
    - rule_title is denormalised for audit readability: even if a rule is
      renamed or deleted, the title at time of change is preserved.
    """

    __tablename__ = "audit_logs"

    __table_args__: tuple = ()

    # ── Ownership ────────────────────────────────────────────────────────────
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant: Mapped["Tenant"] = relationship(  # noqa: F821
        "Tenant",
        back_populates="audit_logs",
    )

    # ── What changed ─────────────────────────────────────────────────────────
    rule_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Human-readable rule identifier (not the UUID PK)",
    )
    rule_title: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Denormalised rule title at time of change for audit readability",
    )
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Action type, e.g. editable_update, status_change, verify",
    )
    field_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Which field was changed; NULL for whole-rule actions",
    )
    old_value: Mapped[Optional[Any]] = mapped_column(
        JSON,
        nullable=True,
        comment="Value before the change",
    )
    new_value: Mapped[Optional[Any]] = mapped_column(
        JSON,
        nullable=True,
        comment="Value after the change",
    )

    # ── Who and why ──────────────────────────────────────────────────────────
    changed_by: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="User ID, service account, or 'system'",
    )
    reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Optional justification provided by the operator at time of change",
    )

    # ── When — immutable ─────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        comment="Set once on insert; never updated",
    )

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """
        Return a JSON-safe dict of all columns.

        The CSV export fieldnames map directly to the keys returned here:
        id, tenant_id, rule_id, rule_title, action, changed_by,
        field_name, old_value, new_value, reason, timestamp.
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
            "rule_title": self.rule_title,
            "action": self.action,
            "field_name": self.field_name,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "changed_by": self.changed_by,
            "reason": self.reason,
            # "timestamp" alias matches the CSV export fieldnames in audit.py
            "timestamp": _serialize(self.created_at),
            "created_at": _serialize(self.created_at),
        }

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id!s:.8} "
            f"rule_id={self.rule_id!r} "
            f"action={self.action!r} "
            f"by={self.changed_by!r}>"
        )
