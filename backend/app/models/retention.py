from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .base import Base, GUID, UUIDMixin


class RetentionCategory(str, enum.Enum):
    AUDIT_LOGS = "audit_logs"
    FILE_ACCESS_LOGS = "file_access_logs"
    EXTRACTION_RESULTS = "extraction_results"
    PENDING_CHANGES = "pending_changes"


class RetentionPolicy(UUIDMixin, Base):
    """
    Tenant-level retention: delete records older than N days per category.
    Legal holds override deletion. The actual sweep runs as a scheduled job
    (stub/admin-triggered today — `POST /compliance/retention/apply`).
    """

    __tablename__ = "retention_policies"
    __table_args__ = (
        Index("ix_retention_tenant_category", "tenant_id", "category"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=2555)  # 7 years default

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
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
        return {
            "id": _s(self.id),
            "tenant_id": _s(self.tenant_id),
            "category": self.category,
            "retention_days": self.retention_days,
            "active": self.active,
            "created_by_email": self.created_by_email,
            "created_at": _s(self.created_at),
        }


class LegalHold(UUIDMixin, Base):
    """
    Legal hold freezes specific records from retention deletion. Scope can
    target a rule_id, a date range, or all records for the tenant.
    """

    __tablename__ = "legal_holds"
    __table_args__ = (
        Index("ix_legal_hold_tenant_active", "tenant_id", "active"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Scope: any combination. Empty values mean unrestricted for that axis.
    rule_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    categories: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    date_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    date_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    placed_by_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    placed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

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
            "name": self.name,
            "description": self.description,
            "rule_ids": self.rule_ids or [],
            "categories": self.categories or [],
            "date_from": _s(self.date_from),
            "date_to": _s(self.date_to),
            "active": self.active,
            "placed_by_email": self.placed_by_email,
            "placed_at": _s(self.placed_at),
            "released_at": _s(self.released_at),
        }
