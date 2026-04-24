"""
Retention + legal-hold service. Today the sweep is admin-triggered via
POST /compliance/retention/apply. In prod this runs as a nightly cron.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.file_access_log import FileAccessLog
from app.models.pending_change import PendingChange, PendingStatus
from app.models.retention import (
    LegalHold,
    RetentionCategory,
    RetentionPolicy,
)


def _category_model(category: str):
    if category == RetentionCategory.AUDIT_LOGS.value:
        return AuditLog, "created_at", "rule_id"
    if category == RetentionCategory.FILE_ACCESS_LOGS.value:
        return FileAccessLog, "accessed_at", "path"
    if category == RetentionCategory.PENDING_CHANGES.value:
        return PendingChange, "requested_at", "rule_id"
    return None, None, None


async def _active_holds(db: AsyncSession, tenant_id: uuid.UUID) -> List[LegalHold]:
    stmt = select(LegalHold).where(
        LegalHold.tenant_id == tenant_id, LegalHold.active.is_(True)
    )
    return list((await db.execute(stmt)).scalars().all())


def _is_held(row, category: str, holds: List[LegalHold]) -> bool:
    for h in holds:
        if h.categories and category not in h.categories:
            continue
        # rule_ids filter
        if h.rule_ids:
            row_rule = getattr(row, "rule_id", None)
            if row_rule is None or str(row_rule) not in h.rule_ids:
                continue
        # date filter
        dt = getattr(row, "created_at", None) or getattr(row, "accessed_at", None) \
            or getattr(row, "requested_at", None)
        if h.date_from and dt and dt < h.date_from:
            continue
        if h.date_to and dt and dt > h.date_to:
            continue
        return True
    return False


async def dry_run(db: AsyncSession, tenant_id: uuid.UUID) -> Dict[str, Any]:
    """Return a summary of what retention would delete (without deleting)."""
    policies = list((await db.execute(
        select(RetentionPolicy).where(
            RetentionPolicy.tenant_id == tenant_id,
            RetentionPolicy.active.is_(True),
        )
    )).scalars().all())
    holds = await _active_holds(db, tenant_id)

    now = datetime.now(timezone.utc)
    summary: Dict[str, Any] = {
        "policies": [p.to_dict() for p in policies],
        "active_holds": [h.to_dict() for h in holds],
        "eligible_by_category": {},
        "held_by_category": {},
    }

    for p in policies:
        model, ts_col, _ = _category_model(p.category)
        if model is None:
            continue
        cutoff = now - timedelta(days=p.retention_days)
        col = getattr(model, ts_col)
        where_clauses = [model.tenant_id == tenant_id, col < cutoff]
        rows = list((await db.execute(select(model).where(*where_clauses))).scalars().all())
        held = [r for r in rows if _is_held(r, p.category, holds)]
        summary["eligible_by_category"][p.category] = len(rows) - len(held)
        summary["held_by_category"][p.category] = len(held)

    return summary


async def apply(db: AsyncSession, tenant_id: uuid.UUID) -> Dict[str, int]:
    """Actually delete eligible rows. Returns counts deleted per category."""
    policies = list((await db.execute(
        select(RetentionPolicy).where(
            RetentionPolicy.tenant_id == tenant_id,
            RetentionPolicy.active.is_(True),
        )
    )).scalars().all())
    holds = await _active_holds(db, tenant_id)
    now = datetime.now(timezone.utc)

    deleted: Dict[str, int] = {}
    for p in policies:
        model, ts_col, _ = _category_model(p.category)
        if model is None:
            continue
        cutoff = now - timedelta(days=p.retention_days)
        col = getattr(model, ts_col)
        rows = list((await db.execute(
            select(model).where(model.tenant_id == tenant_id, col < cutoff)
        )).scalars().all())
        to_delete = [r for r in rows if not _is_held(r, p.category, holds)]
        for row in to_delete:
            await db.delete(row)
        deleted[p.category] = len(to_delete)
    if deleted:
        await db.commit()
    return deleted
