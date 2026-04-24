from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base, GUID, UUIDMixin


class FileSourceType(str, enum.Enum):
    LOCAL = "local"
    GIT = "git"
    DMS = "dms"
    CLOUD = "cloud"
    OTHER = "other"


class FileAccessAction(str, enum.Enum):
    READ = "read"
    LISTED = "listed"
    SKIPPED_SIZE = "skipped_size"
    SKIPPED_EXT = "skipped_ext"
    SKIPPED_ERROR = "skipped_error"


class FileSensitivity(str, enum.Enum):
    UNKNOWN = "unknown"
    OK = "ok"
    FLAGGED = "flagged"


class FileAccessLog(UUIDMixin, Base):
    """
    Per-file record of anything the extraction agent touched during a scan.

    Emitted by the CodebaseScanner on every file it opens, lists, or skips.
    Operators use this to confirm the agent only looked at what it should,
    and to flag accidental reads (credentials, customer data, etc.).
    """

    __tablename__ = "file_access_logs"

    __table_args__ = (
        Index("ix_file_access_tenant_accessed", "tenant_id", "accessed_at"),
        Index("ix_file_access_job", "extraction_job_id"),
        Index("ix_file_access_sensitivity", "sensitivity"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )

    extraction_job_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="Job UUID from the in-memory extractor; nullable for ad-hoc reads",
    )

    source_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=FileSourceType.LOCAL.value,
    )
    source_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Human label: repo URL, DMS site, cloud bucket, etc.",
    )

    path: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        comment="Path relative to the scan root",
    )
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA-256 of file contents at time of read",
    )
    language: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    action: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=FileAccessAction.READ.value,
    )
    sensitivity: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=FileSensitivity.UNKNOWN.value,
    )

    pii_tags: Mapped[Optional[list[dict]]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="PII findings from content classifier: [{label, tag, count}, ...]",
    )

    agent: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="extractor",
        comment="Which component touched the file",
    )
    reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Why it was touched or flagged (patterns matched, skip reason, operator note)",
    )

    accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def to_dict(self) -> dict[str, Any]:
        def _s(v: Any) -> Any:
            if isinstance(v, datetime):
                return v.isoformat()
            if isinstance(v, uuid.UUID):
                return str(v)
            return v

        return {
            "id": _s(self.id),
            "tenant_id": _s(self.tenant_id),
            "extraction_job_id": self.extraction_job_id,
            "source_type": self.source_type,
            "source_name": self.source_name,
            "path": self.path,
            "size_bytes": self.size_bytes,
            "content_hash": self.content_hash,
            "language": self.language,
            "action": self.action,
            "sensitivity": self.sensitivity,
            "pii_tags": self.pii_tags or [],
            "agent": self.agent,
            "reason": self.reason,
            "accessed_at": _s(self.accessed_at),
        }

    def __repr__(self) -> str:
        return (
            f"<FileAccessLog id={self.id!s:.8} "
            f"path={self.path!r} action={self.action!r} "
            f"sensitivity={self.sensitivity!r}>"
        )
