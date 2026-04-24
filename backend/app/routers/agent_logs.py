"""
Agent-logs router — observability for every LLM agent invocation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.agent_run import AgentRun

router = APIRouter(prefix="/api/agent-logs", tags=["agent-logs"])


def _uuid(value: str, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid UUID for {field_name}: {value!r}",
        )


@router.get("", summary="List agent runs")
async def list_runs(
    tenant_id: str = Query(...),
    agent_name: Optional[str] = Query(None),
    job_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    since: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    tenant_uuid = _uuid(tenant_id, "tenant_id")

    stmt = select(AgentRun).where(AgentRun.tenant_id == tenant_uuid)
    if agent_name:
        stmt = stmt.where(AgentRun.agent_name == agent_name)
    if job_id:
        stmt = stmt.where(AgentRun.job_id == job_id)
    if status_filter:
        stmt = stmt.where(AgentRun.status == status_filter)
    if since:
        stmt = stmt.where(AgentRun.started_at >= since)

    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar_one()

    stmt = stmt.order_by(AgentRun.started_at.desc()).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).scalars().all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [r.to_dict() for r in rows],
    }


@router.get("/stats", summary="Aggregate stats")
async def get_stats(
    tenant_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    tenant_uuid = _uuid(tenant_id, "tenant_id")
    total = (await db.execute(
        select(func.count()).select_from(AgentRun).where(AgentRun.tenant_id == tenant_uuid)
    )).scalar_one()

    day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    today = (await db.execute(
        select(func.count()).select_from(AgentRun).where(
            AgentRun.tenant_id == tenant_uuid,
            AgentRun.started_at >= day_ago,
        )
    )).scalar_one()

    by_agent = {
        row[0]: row[1]
        for row in (await db.execute(
            select(AgentRun.agent_name, func.count())
            .where(AgentRun.tenant_id == tenant_uuid)
            .group_by(AgentRun.agent_name)
        )).all()
    }
    by_status = {
        row[0]: row[1]
        for row in (await db.execute(
            select(AgentRun.status, func.count())
            .where(AgentRun.tenant_id == tenant_uuid)
            .group_by(AgentRun.status)
        )).all()
    }

    # total tokens + avg duration
    agg = (await db.execute(
        select(
            func.sum(AgentRun.input_tokens),
            func.sum(AgentRun.output_tokens),
            func.avg(AgentRun.duration_ms),
        ).where(AgentRun.tenant_id == tenant_uuid)
    )).one()

    return {
        "total": total,
        "runs_last_24h": today,
        "by_agent": by_agent,
        "by_status": by_status,
        "total_input_tokens": int(agg[0] or 0),
        "total_output_tokens": int(agg[1] or 0),
        "avg_duration_ms": int(agg[2] or 0),
        "failed_count": by_status.get("failed", 0),
    }


@router.get("/{run_id}", summary="Get single agent run")
async def get_run(
    run_id: str,
    tenant_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    tenant_uuid = _uuid(tenant_id, "tenant_id")
    stmt = select(AgentRun).where(
        AgentRun.id == _uuid(run_id, "run_id"),
        AgentRun.tenant_id == tenant_uuid,
    )
    run = (await db.execute(stmt)).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="agent run not found")
    return run.to_dict()
