"""
AgentLogger — buffered recorder for LLM agent invocations.

Mirrors AccessLogger: buffer in-memory during a job, flush to DB in one commit.
Context-manager friendly so a caller can wrap each LLM call:

    async with logger.run(step_index=i, step_label=chunk.file_path) as rec:
        resp = await anthropic_client.messages.create(...)
        rec.set_result(resp)
"""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentRun, AgentStatus

_log = logging.getLogger(__name__)

_MAX_PREVIEW_CHARS = 2000


def _truncate(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    if len(text) <= _MAX_PREVIEW_CHARS:
        return text
    return text[: _MAX_PREVIEW_CHARS] + f"… (+{len(text) - _MAX_PREVIEW_CHARS} chars)"


@dataclass
class _Pending:
    tenant_id: uuid.UUID
    agent_name: str
    agent_version: Optional[str]
    job_id: Optional[str]
    step_index: Optional[int]
    step_label: Optional[str]
    status: str
    model: Optional[str]
    input_summary: Optional[str]
    output_summary: Optional[str]
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    duration_ms: Optional[int]
    error: Optional[str]
    started_at: datetime
    finished_at: Optional[datetime]


class _Record:
    """Handle returned by AgentLogger.run() — caller fills in the result."""

    def __init__(self, entry: _Pending) -> None:
        self._entry = entry

    def set_input(self, text: str) -> None:
        self._entry.input_summary = _truncate(text)

    def set_output(self, text: str) -> None:
        self._entry.output_summary = _truncate(text)

    def set_model(self, model: str) -> None:
        self._entry.model = model

    def set_tokens(self, input_tokens: Optional[int], output_tokens: Optional[int]) -> None:
        self._entry.input_tokens = input_tokens
        self._entry.output_tokens = output_tokens

    def set_skipped(self, reason: str) -> None:
        self._entry.status = AgentStatus.SKIPPED.value
        self._entry.error = reason

    def set_anthropic_response(self, response: Any) -> None:
        """Convenience: pull common fields off an anthropic.Message."""
        model = getattr(response, "model", None)
        usage = getattr(response, "usage", None)
        in_tok = getattr(usage, "input_tokens", None) if usage else None
        out_tok = getattr(usage, "output_tokens", None) if usage else None
        if model:
            self.set_model(model)
        self.set_tokens(in_tok, out_tok)
        # flatten text blocks if present
        content = getattr(response, "content", None)
        if content:
            parts = []
            for blk in content:
                text = getattr(blk, "text", None)
                if text:
                    parts.append(text)
            if parts:
                self.set_output("\n".join(parts))


class AgentLogger:
    def __init__(
        self,
        tenant_id: uuid.UUID | str,
        *,
        agent_name: str,
        agent_version: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> None:
        if isinstance(tenant_id, str):
            tenant_id = uuid.UUID(tenant_id)
        self.tenant_id = tenant_id
        self.agent_name = agent_name
        self.agent_version = agent_version
        self.job_id = job_id
        self._buffer: List[_Pending] = []

    @asynccontextmanager
    async def run(
        self,
        *,
        step_index: Optional[int] = None,
        step_label: Optional[str] = None,
        input_summary: Optional[str] = None,
    ) -> AsyncIterator[_Record]:
        entry = _Pending(
            tenant_id=self.tenant_id,
            agent_name=self.agent_name,
            agent_version=self.agent_version,
            job_id=self.job_id,
            step_index=step_index,
            step_label=step_label,
            status=AgentStatus.STARTED.value,
            model=None,
            input_summary=_truncate(input_summary),
            output_summary=None,
            input_tokens=None,
            output_tokens=None,
            duration_ms=None,
            error=None,
            started_at=datetime.now(timezone.utc),
            finished_at=None,
        )
        start = time.perf_counter()
        record = _Record(entry)
        try:
            yield record
            if entry.status == AgentStatus.STARTED.value:
                entry.status = AgentStatus.COMPLETED.value
        except Exception as exc:
            entry.status = AgentStatus.FAILED.value
            entry.error = str(exc)
            raise
        finally:
            entry.finished_at = datetime.now(timezone.utc)
            entry.duration_ms = int((time.perf_counter() - start) * 1000)
            self._buffer.append(entry)

    @property
    def pending_count(self) -> int:
        return len(self._buffer)

    async def flush(self, session: AsyncSession) -> int:
        if not self._buffer:
            return 0
        rows = [
            AgentRun(
                tenant_id=e.tenant_id,
                agent_name=e.agent_name,
                agent_version=e.agent_version,
                job_id=e.job_id,
                step_index=e.step_index,
                step_label=e.step_label,
                status=e.status,
                model=e.model,
                input_summary=e.input_summary,
                output_summary=e.output_summary,
                input_tokens=e.input_tokens,
                output_tokens=e.output_tokens,
                duration_ms=e.duration_ms,
                error=e.error,
                started_at=e.started_at,
                finished_at=e.finished_at,
            )
            for e in self._buffer
        ]
        session.add_all(rows)
        await session.commit()
        count = len(rows)
        _log.info(
            "AgentLogger flushed %d rows (agent=%s job=%s)",
            count, self.agent_name, self.job_id,
        )
        self._buffer.clear()
        return count
