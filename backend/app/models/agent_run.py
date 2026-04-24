from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, GUID, UUIDMixin


class AgentStatus(str, enum.Enum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class AgentRun(UUIDMixin, Base):
    """
    One invocation of an LLM-backed agent. Emitted by:
      - extractor / RuleAnalyzer  (one row per chunk analyzed)
      - drift_detector            (one row per rule re-scan)
      - future agents

    The table is an observability log — every LLM call the platform makes on
    behalf of the tenant lands here with input/output summaries, token counts,
    latency, and error details. Non-sensitive fields only; full prompts stay
    in the extraction job payload.
    """

    __tablename__ = "agent_runs"

    __table_args__ = (
        Index("ix_agent_run_tenant_started", "tenant_id", "started_at"),
        Index("ix_agent_run_agent", "agent_name"),
        Index("ix_agent_run_job", "job_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
    )

    agent_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Which agent ran: extractor / drift_detector / describer / …",
    )
    agent_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    job_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="Extraction job UUID, drift job UUID, etc.",
    )
    step_index: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        comment="0-indexed position within a job; lets the UI render progression",
    )
    step_label: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
        comment="Human-readable step hint (file path, rule title, etc.)",
    )

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=AgentStatus.STARTED.value,
    )

    model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    input_summary: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Truncated input preview (first ~1KB of prompt).",
    )
    output_summary: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Truncated output preview. Full results live in ExtractionJob.",
    )
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

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
            "agent_name": self.agent_name,
            "agent_version": self.agent_version,
            "job_id": self.job_id,
            "step_index": self.step_index,
            "step_label": self.step_label,
            "status": self.status,
            "model": self.model,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "started_at": _s(self.started_at),
            "finished_at": _s(self.finished_at),
        }
