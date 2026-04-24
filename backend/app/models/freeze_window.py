from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .base import Base, GUID, UUIDMixin


class FreezeScope(str, enum.Enum):
    ALL = "all"
    BY_TAG = "by_tag"
    BY_RISK = "by_risk"
    BY_DEPARTMENT = "by_department"


class FreezeWindow(UUIDMixin, Base):
    """
    A calendar window during which rule edits are blocked for the matching
    scope. Users whose roles appear in bypass_roles can still edit.
    """

    __tablename__ = "freeze_windows"

    __table_args__ = (
        Index("ix_freeze_windows_tenant_active", "tenant_id", "active"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    scope: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=FreezeScope.ALL.value,
    )
    # Used when scope is BY_TAG / BY_RISK / BY_DEPARTMENT. Stored as JSON
    # array of string match values.
    scope_values: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True, default=list)

    # Roles that can still edit during this window. Empty = nobody bypasses.
    bypass_roles: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True, default=list)

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
            "start_at": _s(self.start_at),
            "end_at": _s(self.end_at),
            "scope": self.scope,
            "scope_values": self.scope_values or [],
            "bypass_roles": self.bypass_roles or [],
            "active": self.active,
            "created_by_email": self.created_by_email,
            "created_at": _s(self.created_at),
        }

    def is_in_effect(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        def _aware(dt):
            if dt is None:
                return None
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        start = _aware(self.start_at)
        end = _aware(self.end_at)
        return bool(self.active and start and end and start <= now <= end)
