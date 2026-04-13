"""
Model registry — import all ORM models here so that:

1. Alembic's env.py can do `from app.models import Base` and see every table.
2. Relationship back-references resolve without circular import errors.
3. Any module can do `from app.models import Rule, Tenant, ...` from one place.
"""

from .audit_log import AuditAction, AuditLog
from .base import Base, TimestampMixin, UUIDMixin
from .extraction_job import ExtractionJob, JobStatus, SourceType
from .rule import Rule
from .tenant import Tenant

__all__ = [
    # Base classes
    "Base",
    "TimestampMixin",
    "UUIDMixin",
    # Domain models
    "Tenant",
    "Rule",
    "AuditLog",
    "ExtractionJob",
    # Enums
    "AuditAction",
    "JobStatus",
    "SourceType",
]
