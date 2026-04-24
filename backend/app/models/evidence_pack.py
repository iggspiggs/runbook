from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .base import Base, GUID, UUIDMixin


class EvidencePack(UUIDMixin, Base):
    """
    Record of a generated compliance-evidence bundle. The actual ZIP is
    streamed back to the caller; this table records metadata so auditors
    can see "who asked for what, when, covering which date range."
    """

    __tablename__ = "evidence_packs"

    __table_args__ = (
        Index("ix_evidence_tenant_generated", "tenant_id", "generated_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
    )

    label: Mapped[str] = mapped_column(String(255), nullable=False)
    scope_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    date_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    date_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    filters: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
        comment="Filters applied: tags, risk_levels, departments, rule_ids",
    )

    rule_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    audit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approval_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    requested_by_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
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
        return {
            "id": _s(self.id),
            "tenant_id": _s(self.tenant_id),
            "label": self.label,
            "scope_description": self.scope_description,
            "date_from": _s(self.date_from),
            "date_to": _s(self.date_to),
            "filters": self.filters or {},
            "rule_count": self.rule_count,
            "audit_count": self.audit_count,
            "approval_count": self.approval_count,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "requested_by_email": self.requested_by_email,
            "generated_at": _s(self.generated_at),
        }
