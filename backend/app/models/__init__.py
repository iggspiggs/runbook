"""
Model registry — import all ORM models here so that:

1. Alembic's env.py can do `from app.models import Base` and see every table.
2. Relationship back-references resolve without circular import errors.
3. Any module can do `from app.models import Rule, Tenant, ...` from one place.
"""

from .agent_run import AgentRun, AgentStatus
from .attestation import Attestation, AttestationStatus
from .audit_log import AuditAction, AuditLog
from .base import Base, TimestampMixin, UUIDMixin
from .evidence_pack import EvidencePack
from .extraction_job import ExtractionJob, JobStatus, SourceType
from .file_access_log import (
    FileAccessAction,
    FileAccessLog,
    FileSensitivity,
    FileSourceType,
)
from .freeze_window import FreezeScope, FreezeWindow
from .pending_change import (
    ApprovalDecision,
    PendingChange,
    PendingChangeApproval,
    PendingStatus,
)
from .retention import LegalHold, RetentionCategory, RetentionPolicy
from .rule import Rule
from .scan_policy import PolicyMode, ScanPolicy
from .tenant import Tenant
from .user import Role, User, UserRole, VALID_ROLES

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
    "FileAccessLog",
    "User",
    "UserRole",
    "PendingChange",
    "PendingChangeApproval",
    "FreezeWindow",
    "Attestation",
    "EvidencePack",
    "ScanPolicy",
    "RetentionPolicy",
    "LegalHold",
    "AgentRun",
    # Enums
    "AuditAction",
    "JobStatus",
    "SourceType",
    "FileAccessAction",
    "FileSensitivity",
    "FileSourceType",
    "Role",
    "VALID_ROLES",
    "PendingStatus",
    "ApprovalDecision",
    "FreezeScope",
    "AttestationStatus",
    "PolicyMode",
    "RetentionCategory",
    "AgentStatus",
]
