"""
File-access router — surface every file the extraction agent touched.

Operators use this page to confirm the agent only looked at what it should,
spot accidental reads (credentials, PII), and flag items for follow-up.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.file_access_log import (
    FileAccessAction,
    FileAccessLog,
    FileSensitivity,
)

router = APIRouter(prefix="/api/file-access", tags=["file-access"])


class FlagRequest(BaseModel):
    sensitivity: str = Field(
        ...,
        description="New sensitivity classification",
        examples=["flagged", "ok", "unknown"],
    )
    reason: Optional[str] = Field(None, description="Operator note explaining the flag")


def _parse_uuid(value: str, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid UUID for {field_name}: {value!r}",
        )


@router.get("", summary="List file-access entries")
async def list_file_access(
    tenant_id: str = Query(...),
    extraction_job_id: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    sensitivity: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="Substring match on path"),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    tenant_uuid = _parse_uuid(tenant_id, "tenant_id")

    stmt = select(FileAccessLog).where(FileAccessLog.tenant_id == tenant_uuid)
    if extraction_job_id:
        stmt = stmt.where(FileAccessLog.extraction_job_id == extraction_job_id)
    if source_type:
        stmt = stmt.where(FileAccessLog.source_type == source_type)
    if action:
        stmt = stmt.where(FileAccessLog.action == action)
    if sensitivity:
        stmt = stmt.where(FileAccessLog.sensitivity == sensitivity)
    if search:
        stmt = stmt.where(FileAccessLog.path.ilike(f"%{search}%"))
    if date_from:
        stmt = stmt.where(FileAccessLog.accessed_at >= date_from)
    if date_to:
        stmt = stmt.where(FileAccessLog.accessed_at <= date_to)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_stmt)).scalar_one()

    stmt = stmt.order_by(FileAccessLog.accessed_at.desc()).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).scalars().all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [r.to_dict() for r in rows],
    }


@router.get("/stats", summary="Aggregate stats for the data-access dashboard")
async def get_stats(
    tenant_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    tenant_uuid = _parse_uuid(tenant_id, "tenant_id")

    total_q = select(func.count()).select_from(FileAccessLog).where(
        FileAccessLog.tenant_id == tenant_uuid
    )
    total = (await db.execute(total_q)).scalar_one()

    by_action_q = (
        select(FileAccessLog.action, func.count())
        .where(FileAccessLog.tenant_id == tenant_uuid)
        .group_by(FileAccessLog.action)
    )
    by_action = {row[0]: row[1] for row in (await db.execute(by_action_q)).all()}

    by_sensitivity_q = (
        select(FileAccessLog.sensitivity, func.count())
        .where(FileAccessLog.tenant_id == tenant_uuid)
        .group_by(FileAccessLog.sensitivity)
    )
    by_sensitivity = {row[0]: row[1] for row in (await db.execute(by_sensitivity_q)).all()}

    by_source_q = (
        select(FileAccessLog.source_type, func.count())
        .where(FileAccessLog.tenant_id == tenant_uuid)
        .group_by(FileAccessLog.source_type)
    )
    by_source = {row[0]: row[1] for row in (await db.execute(by_source_q)).all()}

    recent_jobs_q = (
        select(
            FileAccessLog.extraction_job_id,
            func.count().label("files"),
            func.max(FileAccessLog.accessed_at).label("last_seen"),
        )
        .where(FileAccessLog.tenant_id == tenant_uuid)
        .group_by(FileAccessLog.extraction_job_id)
        .order_by(func.max(FileAccessLog.accessed_at).desc())
        .limit(10)
    )
    recent_jobs = [
        {
            "extraction_job_id": row.extraction_job_id,
            "files": row.files,
            "last_seen": row.last_seen.isoformat() if row.last_seen else None,
        }
        for row in (await db.execute(recent_jobs_q)).all()
    ]

    return {
        "total_files": total,
        "by_action": by_action,
        "by_sensitivity": by_sensitivity,
        "by_source": by_source,
        "recent_jobs": recent_jobs,
        "flagged_count": by_sensitivity.get(FileSensitivity.FLAGGED.value, 0),
    }


@router.post("/{entry_id}/flag", summary="Change sensitivity classification")
async def flag_entry(
    entry_id: str,
    body: FlagRequest,
    tenant_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    tenant_uuid = _parse_uuid(tenant_id, "tenant_id")
    entry_uuid = _parse_uuid(entry_id, "entry_id")

    valid = {s.value for s in FileSensitivity}
    if body.sensitivity not in valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"sensitivity must be one of {sorted(valid)}",
        )

    stmt = select(FileAccessLog).where(
        FileAccessLog.id == entry_uuid,
        FileAccessLog.tenant_id == tenant_uuid,
    )
    entry = (await db.execute(stmt)).scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entry not found")

    entry.sensitivity = body.sensitivity
    if body.reason:
        prior = entry.reason or ""
        separator = " | " if prior else ""
        entry.reason = f"{prior}{separator}operator: {body.reason}"
    await db.commit()
    await db.refresh(entry)
    return entry.to_dict()
