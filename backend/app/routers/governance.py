"""
Governance router — pending-change queue + freeze-window admin.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models.attestation import Attestation, AttestationStatus
from app.models.freeze_window import FreezeScope, FreezeWindow
from app.models.pending_change import PendingStatus
from app.models.user import User
from app.services.governance import ApprovalService, AttestationService
from app.services.governance.permissions import (
    PermissionError_,
    can_approve,
    is_admin,
)

router = APIRouter(prefix="/api/governance", tags=["governance"])


# ---------------------------- schemas ----------------------------

class DecideRequest(BaseModel):
    decision: str = Field(..., description="'approve' or 'reject'")
    note: Optional[str] = None


class FreezeWindowPayload(BaseModel):
    name: str
    description: Optional[str] = None
    start_at: datetime
    end_at: datetime
    scope: str = Field("all", description="all | by_tag | by_risk | by_department")
    scope_values: List[str] = Field(default_factory=list)
    bypass_roles: List[str] = Field(default_factory=list)
    active: bool = True


def _tenant_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid tenant_id: {value!r}",
        )


# ---------------------------- pending changes ----------------------------

@router.get("/pending-changes", summary="List pending changes")
async def list_pending_changes(
    tenant_id: str = Query(...),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    tenant_uuid = _tenant_uuid(tenant_id)
    service = ApprovalService(db)
    items = await service.list_pending(
        tenant_id=tenant_uuid,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return {
        "total": len(items),
        "items": [i.to_dict() for i in items],
        "offset": offset,
        "limit": limit,
    }


@router.get("/pending-changes/{pc_id}", summary="Get a single pending change")
async def get_pending_change(
    pc_id: str,
    tenant_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    service = ApprovalService(db)
    pc = await service.get(_tenant_uuid(pc_id), _tenant_uuid(tenant_id))
    if pc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pending change not found")
    return pc.to_dict()


@router.post("/pending-changes/{pc_id}/decide", summary="Approve or reject a pending change")
async def decide_pending(
    pc_id: str,
    body: DecideRequest,
    tenant_id: str = Query(...),
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    if not can_approve(current.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="approver/admin role required")

    service = ApprovalService(db)
    try:
        pc = await service.decide(
            pending_id=_tenant_uuid(pc_id),
            tenant_id=_tenant_uuid(tenant_id),
            approver=current,
            decision=body.decision,
            note=body.note,
        )
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pending change not found")
    except PermissionError_ as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return pc.to_dict()


@router.post("/pending-changes/{pc_id}/cancel", summary="Cancel a pending change")
async def cancel_pending(
    pc_id: str,
    tenant_id: str = Query(...),
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    service = ApprovalService(db)
    try:
        pc = await service.cancel(
            pending_id=_tenant_uuid(pc_id),
            tenant_id=_tenant_uuid(tenant_id),
            user=current,
        )
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pending change not found")
    except PermissionError_ as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return pc.to_dict()


# ---------------------------- freeze windows ----------------------------

@router.get("/freezes", summary="List freeze windows")
async def list_freezes(
    tenant_id: str = Query(...),
    active_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    tenant_uuid = _tenant_uuid(tenant_id)
    stmt = select(FreezeWindow).where(FreezeWindow.tenant_id == tenant_uuid)
    if active_only:
        stmt = stmt.where(FreezeWindow.active.is_(True))
    stmt = stmt.order_by(FreezeWindow.start_at.desc())
    windows = (await db.execute(stmt)).scalars().all()
    return {"items": [w.to_dict() for w in windows], "total": len(windows)}


@router.post("/freezes", summary="Create a freeze window (admin only)", status_code=201)
async def create_freeze(
    body: FreezeWindowPayload,
    tenant_id: str = Query(...),
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    if not is_admin(current.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
    if body.scope not in {s.value for s in FreezeScope}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"scope must be one of {[s.value for s in FreezeScope]}",
        )
    if body.end_at <= body.start_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="end_at must be after start_at",
        )

    tenant_uuid = _tenant_uuid(tenant_id)
    window = FreezeWindow(
        tenant_id=tenant_uuid,
        name=body.name,
        description=body.description,
        start_at=body.start_at,
        end_at=body.end_at,
        scope=body.scope,
        scope_values=body.scope_values,
        bypass_roles=body.bypass_roles,
        active=body.active,
        created_by_email=current.email,
    )
    db.add(window)
    await db.commit()
    await db.refresh(window)
    return window.to_dict()


@router.delete("/freezes/{window_id}", summary="Deactivate a freeze window (admin only)")
async def delete_freeze(
    window_id: str,
    tenant_id: str = Query(...),
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    if not is_admin(current.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
    tenant_uuid = _tenant_uuid(tenant_id)
    wid = _tenant_uuid(window_id)
    window = (await db.execute(
        select(FreezeWindow).where(FreezeWindow.id == wid, FreezeWindow.tenant_id == tenant_uuid)
    )).scalar_one_or_none()
    if window is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="freeze window not found")
    window.active = False
    await db.commit()
    return {"ok": True, "id": str(window.id)}


# ---------------------------- attestations ----------------------------

class IssueCampaignRequest(BaseModel):
    period_label: str = Field(..., examples=["2026-Q2"])
    due_in_days: int = Field(14, ge=1, le=365)
    only_risk_levels: Optional[List[str]] = None


class AttestationResponse(BaseModel):
    status: str = Field(..., description="attested | changes_needed")
    note: Optional[str] = None


@router.get("/attestations", summary="List attestations")
async def list_attestations(
    tenant_id: str = Query(...),
    status_filter: Optional[str] = Query(None, alias="status"),
    period_label: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    tenant_uuid = _tenant_uuid(tenant_id)
    # Auto-mark overdue before listing
    service = AttestationService(db)
    await service.mark_overdue(tenant_uuid)

    stmt = select(Attestation).where(Attestation.tenant_id == tenant_uuid)
    if status_filter:
        stmt = stmt.where(Attestation.status == status_filter)
    if period_label:
        stmt = stmt.where(Attestation.period_label == period_label)
    stmt = stmt.order_by(Attestation.due_at.asc()).limit(limit)
    items = (await db.execute(stmt)).scalars().all()
    return {"items": [a.to_dict() for a in items], "total": len(items)}


@router.post("/attestations/campaign", summary="Issue a new attestation campaign (admin only)", status_code=201)
async def issue_campaign(
    body: IssueCampaignRequest,
    tenant_id: str = Query(...),
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    if not is_admin(current.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
    service = AttestationService(db)
    created, skipped = await service.issue_campaign(
        tenant_id=_tenant_uuid(tenant_id),
        period_label=body.period_label,
        due_in_days=body.due_in_days,
        only_risk_levels=body.only_risk_levels,
    )
    return {"period_label": body.period_label, "created": created, "skipped": skipped}


@router.post("/attestations/{att_id}/respond", summary="Respond to an attestation")
async def respond_attestation(
    att_id: str,
    body: AttestationResponse,
    tenant_id: str = Query(...),
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    service = AttestationService(db)
    try:
        att = await service.respond(
            tenant_id=_tenant_uuid(tenant_id),
            attestation_id=_tenant_uuid(att_id),
            responder_email=current.email,
            status=body.status,
            note=body.note,
        )
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="attestation not found")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return att.to_dict()
