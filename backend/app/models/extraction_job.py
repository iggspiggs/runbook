from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, GUID, TimestampMixin, UUIDMixin


class JobStatus(str, enum.Enum):
    """Lifecycle states of a single extraction run."""

    PENDING = "pending"
    SCANNING = "scanning"       # Cloning / reading the source
    EXTRACTING = "extracting"   # LLM is processing files
    REVIEWING = "reviewing"     # Diff is ready for human review
    COMPLETE = "complete"
    FAILED = "failed"


class SourceType(str, enum.Enum):
    """Where the source code comes from."""

    GIT_REPO = "git_repo"
    API_SCAN = "api_scan"
    MANUAL = "manual"


class ExtractionJob(UUIDMixin, TimestampMixin, Base):
    """
    Tracks a single end-to-end extraction run against a codebase.

    One job = one scan of one source at one point in time.  Rules discovered
    during the job are written to the Rule table and reference this job via
    their source provenance fields (source_file, source_lines, confidence).

    Counter columns (rules_found, rules_new, rules_changed, rules_removed)
    are updated incrementally as the extractor processes files so that
    operators can monitor live progress without polling the Rule table.
    """

    __tablename__ = "extraction_jobs"

    __table_args__: tuple = ()

    # ── Ownership ────────────────────────────────────────────────────────────
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant: Mapped["Tenant"] = relationship(  # noqa: F821
        "Tenant",
        back_populates="extraction_jobs",
    )

    # ── State machine ────────────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=JobStatus.PENDING.value,
        comment="pending | scanning | extracting | reviewing | complete | failed",
    )

    # ── Source location ──────────────────────────────────────────────────────
    source_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="git_repo | api_scan | manual",
    )
    source_uri: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
        comment="Repository URL or local path being scanned",
    )
    branch: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Git branch name; NULL for non-git sources",
    )
    commit_sha: Mapped[Optional[str]] = mapped_column(
        String(40),
        nullable=True,
        comment="Full SHA of the commit that was scanned",
    )

    # ── Result counters ──────────────────────────────────────────────────────
    rules_found: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Total rules seen in this scan",
    )
    rules_new: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Rules that did not previously exist in the registry",
    )
    rules_changed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Existing rules whose definition changed",
    )
    rules_removed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Rules present in the registry but absent from this scan",
    )

    # ── Timing ───────────────────────────────────────────────────────────────
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Set when the worker picks up the job",
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Set on success or failure",
    )

    # ── Failure detail ───────────────────────────────────────────────────────
    error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Full traceback or error message if status=failed",
    )

    @property
    def duration_seconds(self) -> Optional[float]:
        """Wall-clock seconds for completed or failed jobs."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def __repr__(self) -> str:
        return (
            f"<ExtractionJob id={self.id!s:.8} "
            f"status={self.status.value!r} "
            f"source={self.source_uri!r:.40} "
            f"rules_found={self.rules_found}>"
        )
