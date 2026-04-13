from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base, GUID, TimestampMixin, UUIDMixin

# Valid subscription plans
PLAN_FREE = "free"
PLAN_PRO = "pro"
PLAN_ENTERPRISE = "enterprise"
VALID_PLANS = {PLAN_FREE, PLAN_PRO, PLAN_ENTERPRISE}


class Tenant(UUIDMixin, TimestampMixin, Base):
    """
    Top-level tenant (organisation) in the multi-tenant registry.

    Every rule, extraction job, and audit event belongs to exactly one tenant.
    Isolation is enforced at the query layer — every repository/service filters
    by tenant_id before touching any other table.
    """

    __tablename__ = "tenants"

    __table_args__ = (
        UniqueConstraint("slug", name="uq_tenants_slug"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment="URL-safe identifier, e.g. 'acme-corp'",
    )
    plan: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=PLAN_FREE,
        comment="free | pro | enterprise",
    )
    settings: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
        comment="Tenant-level feature flags and configuration overrides",
    )

    # Relationships (lazy by default; join explicitly when needed)
    rules: Mapped[list["Rule"]] = relationship(  # noqa: F821
        "Rule",
        back_populates="tenant",
        cascade="all, delete-orphan",
        lazy="select",
    )
    extraction_jobs: Mapped[list["ExtractionJob"]] = relationship(  # noqa: F821
        "ExtractionJob",
        back_populates="tenant",
        cascade="all, delete-orphan",
        lazy="select",
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(  # noqa: F821
        "AuditLog",
        back_populates="tenant",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Tenant id={self.id!s:.8} slug={self.slug!r} plan={self.plan!r}>"
