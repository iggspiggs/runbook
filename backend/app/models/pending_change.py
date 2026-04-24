from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base, GUID, UUIDMixin


class PendingStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ApprovalDecision(str, enum.Enum):
    APPROVE = "approve"
    REJECT = "reject"


class PendingChange(UUIDMixin, Base):
    """
    A proposed edit to a rule that is waiting for N-of-M approvals.

    Maker/checker invariant: the user in requested_by must NOT appear in
    the approvals list. Enforced at the service layer.
    """

    __tablename__ = "pending_changes"

    __table_args__ = (
        Index("ix_pending_changes_tenant_status", "tenant_id", "status"),
        Index("ix_pending_changes_rule", "rule_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )

    rule_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("rules.id", ondelete="CASCADE"),
        nullable=False,
    )
    rule_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    rule_risk_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # What was proposed
    changes: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        comment="Map of editable field_name → proposed new value",
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ticket_ref: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Workflow state
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=PendingStatus.PENDING.value,
    )
    approvals_required: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1,
        comment="N in N-of-M approval. Set from rule.risk_level at submit time.",
    )

    requested_by: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    requested_by_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_by: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    approvals: Mapped[list["PendingChangeApproval"]] = relationship(
        "PendingChangeApproval",
        back_populates="pending_change",
        cascade="all, delete-orphan",
    )

    def to_dict(self) -> dict[str, Any]:
        def _s(v):
            if isinstance(v, datetime):
                return v.isoformat()
            if isinstance(v, uuid.UUID):
                return str(v)
            return v

        return {
            "id": _s(self.id),
            "tenant_id": _s(self.tenant_id),
            "rule_id": _s(self.rule_id),
            "rule_title": self.rule_title,
            "rule_risk_level": self.rule_risk_level,
            "changes": self.changes,
            "reason": self.reason,
            "ticket_ref": self.ticket_ref,
            "status": self.status,
            "approvals_required": self.approvals_required,
            "requested_by": _s(self.requested_by),
            "requested_by_email": self.requested_by_email,
            "requested_at": _s(self.requested_at),
            "expires_at": _s(self.expires_at),
            "applied_at": _s(self.applied_at),
            "applied_by": _s(self.applied_by),
            "rejection_reason": self.rejection_reason,
            "approvals": [a.to_dict() for a in (self.approvals or [])],
        }


class PendingChangeApproval(UUIDMixin, Base):
    __tablename__ = "pending_change_approvals"
    __table_args__ = (
        Index("ix_pc_approvals_change", "pending_change_id"),
    )

    pending_change_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("pending_changes.id", ondelete="CASCADE"),
        nullable=False,
    )
    approver_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    approver_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    pending_change: Mapped["PendingChange"] = relationship(
        "PendingChange", back_populates="approvals",
    )

    def to_dict(self) -> dict[str, Any]:
        def _s(v):
            if isinstance(v, datetime):
                return v.isoformat()
            if isinstance(v, uuid.UUID):
                return str(v)
            return v

        return {
            "id": _s(self.id),
            "pending_change_id": _s(self.pending_change_id),
            "approver_id": _s(self.approver_id),
            "approver_email": self.approver_email,
            "decision": self.decision,
            "decided_at": _s(self.decided_at),
            "note": self.note,
        }
