from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .base import Base, GUID, UUIDMixin


class PolicyMode(str, enum.Enum):
    ALLOW = "allow"  # only listed patterns are scanned
    DENY = "deny"    # listed patterns are never scanned
    HYBRID = "hybrid"  # first: block denies; second: if allow list non-empty require match


class ScanPolicy(UUIDMixin, Base):
    """
    Tenant-level allow/deny list for the extractor. Path patterns use glob
    syntax (e.g. 'hr/**', '**/secrets/**'). Matched before a file is read so
    a violation never reaches the LLM or the access log.
    """

    __tablename__ = "scan_policies"
    __table_args__ = (
        Index("ix_scan_policy_tenant_active", "tenant_id", "active"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    mode: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=PolicyMode.DENY.value,
    )
    allow_patterns: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    deny_patterns: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

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
            "name": self.name,
            "description": self.description,
            "mode": self.mode,
            "allow_patterns": self.allow_patterns or [],
            "deny_patterns": self.deny_patterns or [],
            "active": self.active,
            "created_by_email": self.created_by_email,
            "created_at": _s(self.created_at),
        }
