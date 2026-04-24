"""
AccessLogger — buffered recorder of file reads performed by the extraction agent.

The scanner calls `logger.record(...)` on every file it touches. Entries are
buffered in memory and flushed to `file_access_logs` in a single batch when
`flush()` is invoked (typically at the end of an extraction job).
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file_access_log import (
    FileAccessAction,
    FileAccessLog,
    FileSensitivity,
    FileSourceType,
)

_log = logging.getLogger(__name__)


# Paths whose names suggest secrets / customer data. A match flips sensitivity
# to FLAGGED so operators notice during review. These are heuristics, not
# guarantees — the point is to surface obvious cases for human confirmation.
_SENSITIVE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\.env(\.|$)", re.IGNORECASE),
    re.compile(r"secrets?(\.|/)", re.IGNORECASE),
    re.compile(r"credentials?(\.|/)", re.IGNORECASE),
    re.compile(r"\.pem$|\.key$|\.pfx$|\.p12$", re.IGNORECASE),
    re.compile(r"id_rsa|id_dsa|id_ecdsa|id_ed25519", re.IGNORECASE),
    re.compile(r"customers?\.(csv|json|xlsx?)$", re.IGNORECASE),
    re.compile(r"pii|ssn|social_security", re.IGNORECASE),
    re.compile(r"backup.*\.(sql|dump)$", re.IGNORECASE),
]


def classify_sensitivity(path: str) -> str:
    for pat in _SENSITIVE_PATTERNS:
        if pat.search(path):
            return FileSensitivity.FLAGGED.value
    return FileSensitivity.UNKNOWN.value


@dataclass
class _PendingEntry:
    tenant_id: uuid.UUID
    extraction_job_id: Optional[str]
    source_type: str
    source_name: Optional[str]
    path: str
    size_bytes: Optional[int]
    content_hash: Optional[str]
    language: Optional[str]
    action: str
    sensitivity: str
    pii_tags: Optional[list]
    agent: str
    reason: Optional[str]
    accessed_at: datetime


class AccessLogger:
    """
    Thread-unsafe buffer — intended to live for the duration of a single
    extraction job which runs in a single background task.
    """

    def __init__(
        self,
        tenant_id: uuid.UUID | str,
        extraction_job_id: Optional[str] = None,
        source_type: str = FileSourceType.LOCAL.value,
        source_name: Optional[str] = None,
        agent: str = "extractor",
    ) -> None:
        if isinstance(tenant_id, str):
            tenant_id = uuid.UUID(tenant_id)
        self.tenant_id = tenant_id
        self.extraction_job_id = extraction_job_id
        self.source_type = source_type
        self.source_name = source_name
        self.agent = agent
        self._buffer: List[_PendingEntry] = []

    # ------------------------------------------------------------------ record

    def record(
        self,
        path: str,
        action: str = FileAccessAction.READ.value,
        *,
        size_bytes: Optional[int] = None,
        content_hash: Optional[str] = None,
        language: Optional[str] = None,
        reason: Optional[str] = None,
        sensitivity: Optional[str] = None,
        pii_tags: Optional[list] = None,
    ) -> None:
        self._buffer.append(
            _PendingEntry(
                tenant_id=self.tenant_id,
                extraction_job_id=self.extraction_job_id,
                source_type=self.source_type,
                source_name=self.source_name,
                path=path,
                size_bytes=size_bytes,
                content_hash=content_hash,
                language=language,
                action=action,
                sensitivity=sensitivity or classify_sensitivity(path),
                pii_tags=pii_tags or [],
                agent=self.agent,
                reason=reason,
                accessed_at=datetime.now(timezone.utc),
            )
        )

    # ------------------------------------------------------------------ flush

    @property
    def pending_count(self) -> int:
        return len(self._buffer)

    async def flush(self, session: AsyncSession) -> int:
        if not self._buffer:
            return 0
        rows = [
            FileAccessLog(
                tenant_id=e.tenant_id,
                extraction_job_id=e.extraction_job_id,
                source_type=e.source_type,
                source_name=e.source_name,
                path=e.path,
                size_bytes=e.size_bytes,
                content_hash=e.content_hash,
                language=e.language,
                action=e.action,
                sensitivity=e.sensitivity,
                pii_tags=e.pii_tags or [],
                agent=e.agent,
                reason=e.reason,
                accessed_at=e.accessed_at,
            )
            for e in self._buffer
        ]
        session.add_all(rows)
        await session.commit()
        count = len(rows)
        _log.info(
            "AccessLogger flushed %d rows (job=%s, tenant=%s)",
            count,
            self.extraction_job_id,
            self.tenant_id,
        )
        self._buffer.clear()
        return count
