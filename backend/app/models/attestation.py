from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, GUID, UUIDMixin


class AttestationStatus(str, enum.Enum):
    PENDING = "pending"
    ATTESTED = "attested"
    CHANGES_NEEDED = "changes_needed"
    OVERDUE = "overdue"


class Attestation(UUIDMixin, Base):
    """
    A periodic "is this rule still correct?" ask to the rule's owner.
    Campaigns issue one Attestation per rule per period; owners respond via
    POST /api/governance/attestations/{id}/respond.
    """

    __tablename__ = "attestations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "rule_id", "period_label", name="uq_attestation_period"),
        Index("ix_attestation_tenant_status", "tenant_id", "status"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("rules.id", ondelete="CASCADE"), nullable=False,
    )
    rule_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    period_label: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="Campaign label e.g. '2026-Q2'",
    )

    owner_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=AttestationStatus.PENDING.value,
    )

    responded_by_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    response_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def to_dict(self) -> dict[str, Any]:
        def _s(v):
            if isinstance(v, datetime):
                return v.isoformat()
            if isinstance(v, uuid.UUID):
                return str(v)
            return v

        # SQLite strips tzinfo on readback — treat naive datetimes as UTC so
        # the comparison below doesn't explode with mixed-awareness errors.
        def _aware(dt):
            if dt is None:
                return None
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

        due_aware = _aware(self.due_at)
        return {
            "id": _s(self.id),
            "tenant_id": _s(self.tenant_id),
            "rule_id": _s(self.rule_id),
            "rule_title": self.rule_title,
            "period_label": self.period_label,
            "owner_email": self.owner_email,
            "due_at": _s(self.due_at),
            "status": self.status,
            "responded_by_email": self.responded_by_email,
            "responded_at": _s(self.responded_at),
            "response_note": self.response_note,
            "created_at": _s(self.created_at),
            "is_overdue": (
                self.status == AttestationStatus.PENDING.value
                and due_aware is not None
                and due_aware < datetime.now(timezone.utc)
            ),
        }
