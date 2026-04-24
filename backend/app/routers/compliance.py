"""
Compliance router — evidence packs, SoD alerts, scan policies, retention,
legal holds. Every endpoint here is read-mostly except admin-gated mutations.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models.evidence_pack import EvidencePack
from app.models.retention import (
    LegalHold,
    RetentionCategory,
    RetentionPolicy,
)
from app.models.scan_policy import PolicyMode, ScanPolicy
from app.models.user import User
from app.services.governance import (
    compute_sod_alerts,
    evidence as evidence_service,
    retention as retention_service,
)
from app.services.governance.permissions import is_admin, can_read

router = APIRouter(prefix="/api/compliance", tags=["compliance"])


def _uuid(value: str, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid UUID for {field_name}: {value!r}",
        )


# ----------------------------------- evidence -----------------------------

class EvidenceRequest(BaseModel):
    label: str
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    filters: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Optional: { tags, risk_levels, departments, rule_ids }",
    )


@router.post("/evidence", summary="Generate and download an evidence pack (ZIP)")
async def generate_evidence(
    body: EvidenceRequest,
    tenant_id: str = Query(...),
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    tenant_uuid = _uuid(tenant_id, "tenant_id")
    payload, pack = await evidence_service.generate(
        db,
        tenant_id=tenant_uuid,
        label=body.label,
        date_from=body.date_from,
        date_to=body.date_to,
        filters=body.filters or {},
        requested_by_email=current.email,
    )
    filename = f"runbook_evidence_{pack.id}.zip"

    def _gen():
        yield payload

    return StreamingResponse(
        _gen(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Evidence-Pack-Id": str(pack.id),
            "X-Evidence-Pack-Sha256": pack.sha256 or "",
        },
    )


@router.get("/evidence", summary="List generated evidence packs")
async def list_evidence(
    tenant_id: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    tenant_uuid = _uuid(tenant_id, "tenant_id")
    stmt = (
        select(EvidencePack)
        .where(EvidencePack.tenant_id == tenant_uuid)
        .order_by(EvidencePack.generated_at.desc())
        .limit(limit)
    )
    items = (await db.execute(stmt)).scalars().all()
    return {"items": [p.to_dict() for p in items], "total": len(items)}


# ----------------------------------- SoD -------------------------------

@router.get("/sod-alerts", summary="Segregation-of-duties anomalies")
async def get_sod_alerts(
    tenant_id: str = Query(...),
    lookback_days: int = Query(30, ge=1, le=365),
    bulk_threshold: int = Query(10, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    tenant_uuid = _uuid(tenant_id, "tenant_id")
    alerts = await compute_sod_alerts(
        db, tenant_uuid,
        lookback_days=lookback_days,
        bulk_threshold=bulk_threshold,
    )
    return {
        "total": len(alerts),
        "lookback_days": lookback_days,
        "items": alerts,
    }


# ----------------------------------- scan policy ------------------------

class ScanPolicyPayload(BaseModel):
    name: str
    description: Optional[str] = None
    mode: str = Field("deny", description="allow | deny | hybrid")
    allow_patterns: List[str] = Field(default_factory=list)
    deny_patterns: List[str] = Field(default_factory=list)
    active: bool = True


@router.get("/scan-policies", summary="List scan policies")
async def list_scan_policies(
    tenant_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    tenant_uuid = _uuid(tenant_id, "tenant_id")
    stmt = (
        select(ScanPolicy)
        .where(ScanPolicy.tenant_id == tenant_uuid)
        .order_by(ScanPolicy.created_at.desc())
    )
    items = (await db.execute(stmt)).scalars().all()
    return {"items": [p.to_dict() for p in items], "total": len(items)}


@router.post("/scan-policies", summary="Create a scan policy (admin only)", status_code=201)
async def create_scan_policy(
    body: ScanPolicyPayload,
    tenant_id: str = Query(...),
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    if not is_admin(current.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
    if body.mode not in {m.value for m in PolicyMode}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"mode must be one of {[m.value for m in PolicyMode]}",
        )
    policy = ScanPolicy(
        tenant_id=_uuid(tenant_id, "tenant_id"),
        name=body.name,
        description=body.description,
        mode=body.mode,
        allow_patterns=body.allow_patterns,
        deny_patterns=body.deny_patterns,
        active=body.active,
        created_by_email=current.email,
    )
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return policy.to_dict()


@router.delete("/scan-policies/{policy_id}", summary="Deactivate a scan policy (admin only)")
async def delete_scan_policy(
    policy_id: str,
    tenant_id: str = Query(...),
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    if not is_admin(current.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
    policy = (await db.execute(
        select(ScanPolicy).where(
            ScanPolicy.id == _uuid(policy_id, "policy_id"),
            ScanPolicy.tenant_id == _uuid(tenant_id, "tenant_id"),
        )
    )).scalar_one_or_none()
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scan policy not found")
    policy.active = False
    await db.commit()
    return {"ok": True, "id": str(policy.id)}


# ----------------------------------- retention + legal holds -----------

class RetentionPolicyPayload(BaseModel):
    category: str
    retention_days: int = Field(..., ge=1)
    active: bool = True


@router.get("/retention/policies", summary="List retention policies")
async def list_retention_policies(
    tenant_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    tenant_uuid = _uuid(tenant_id, "tenant_id")
    stmt = select(RetentionPolicy).where(RetentionPolicy.tenant_id == tenant_uuid)
    items = (await db.execute(stmt)).scalars().all()
    return {"items": [p.to_dict() for p in items], "total": len(items)}


@router.post("/retention/policies", summary="Create or update retention policy (admin only)", status_code=201)
async def upsert_retention_policy(
    body: RetentionPolicyPayload,
    tenant_id: str = Query(...),
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    if not is_admin(current.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
    if body.category not in {c.value for c in RetentionCategory}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"category must be one of {[c.value for c in RetentionCategory]}",
        )
    tenant_uuid = _uuid(tenant_id, "tenant_id")
    existing = (await db.execute(
        select(RetentionPolicy).where(
            RetentionPolicy.tenant_id == tenant_uuid,
            RetentionPolicy.category == body.category,
        )
    )).scalar_one_or_none()
    if existing:
        existing.retention_days = body.retention_days
        existing.active = body.active
        await db.commit()
        await db.refresh(existing)
        return existing.to_dict()
    policy = RetentionPolicy(
        tenant_id=tenant_uuid,
        category=body.category,
        retention_days=body.retention_days,
        active=body.active,
        created_by_email=current.email,
    )
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return policy.to_dict()


@router.get("/retention/dry-run", summary="Preview what retention would delete")
async def retention_dry_run(
    tenant_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    return await retention_service.dry_run(db, _uuid(tenant_id, "tenant_id"))


@router.post("/retention/apply", summary="Apply retention and delete eligible rows (admin only)")
async def retention_apply(
    tenant_id: str = Query(...),
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    if not is_admin(current.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
    deleted = await retention_service.apply(db, _uuid(tenant_id, "tenant_id"))
    return {"deleted_by_category": deleted}


class LegalHoldPayload(BaseModel):
    name: str
    description: Optional[str] = None
    rule_ids: List[str] = Field(default_factory=list)
    categories: List[str] = Field(default_factory=list)
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


@router.get("/legal-holds", summary="List legal holds")
async def list_legal_holds(
    tenant_id: str = Query(...),
    active_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    tenant_uuid = _uuid(tenant_id, "tenant_id")
    stmt = select(LegalHold).where(LegalHold.tenant_id == tenant_uuid)
    if active_only:
        stmt = stmt.where(LegalHold.active.is_(True))
    stmt = stmt.order_by(LegalHold.placed_at.desc())
    items = (await db.execute(stmt)).scalars().all()
    return {"items": [h.to_dict() for h in items], "total": len(items)}


@router.post("/legal-holds", summary="Place a legal hold (admin only)", status_code=201)
async def create_legal_hold(
    body: LegalHoldPayload,
    tenant_id: str = Query(...),
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    if not is_admin(current.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
    hold = LegalHold(
        tenant_id=_uuid(tenant_id, "tenant_id"),
        name=body.name,
        description=body.description,
        rule_ids=body.rule_ids,
        categories=body.categories,
        date_from=body.date_from,
        date_to=body.date_to,
        active=True,
        placed_by_email=current.email,
    )
    db.add(hold)
    await db.commit()
    await db.refresh(hold)
    return hold.to_dict()


@router.post("/legal-holds/{hold_id}/release", summary="Release a legal hold (admin only)")
async def release_legal_hold(
    hold_id: str,
    tenant_id: str = Query(...),
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    if not is_admin(current.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
    hold = (await db.execute(
        select(LegalHold).where(
            LegalHold.id == _uuid(hold_id, "hold_id"),
            LegalHold.tenant_id == _uuid(tenant_id, "tenant_id"),
        )
    )).scalar_one_or_none()
    if hold is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="legal hold not found")
    hold.active = False
    hold.released_at = datetime.utcnow()
    await db.commit()
    await db.refresh(hold)
    return hold.to_dict()
