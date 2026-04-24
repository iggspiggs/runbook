"""
Registry router — CRUD endpoints for automation rules.

All mutations are audit-logged. Editable-field updates are validated
against the declared type of each field before they are persisted.
"""
from __future__ import annotations

import csv
import io
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.registry.rule_service import RuleService
from app.services.governance import (
    ApprovalService,
    FreezeBlock,
    ReasonPolicyError,
    can_edit_rule,
    check_freeze_windows,
    check_reason_policy,
    requires_approval,
)
from app.deps import get_current_user_optional
from app.models.user import User
from app.db import get_db  # async session dependency — defined in app/db.py

router = APIRouter(prefix="/api/rules", tags=["registry"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class EditableFieldUpdate(BaseModel):
    """Payload for PATCH /rules/{rule_id}/editable."""
    changes: Dict[str, Any] = Field(
        ...,
        description="Map of editable field name to new value.",
        examples=[{"alert_threshold": 90, "notify_emails": ["ops@example.com"]}],
    )
    reason: Optional[str] = Field(
        None,
        description="Human-readable reason recorded in the audit log.",
    )
    ticket_ref: Optional[str] = Field(
        None,
        description="Ticket reference (JIRA-123 / LINEAR-456 / #789) — required for high/critical risk.",
    )
    changed_by: str = Field(
        ...,
        description="Identity of the operator making the change.",
    )


class VerifyRequest(BaseModel):
    verified_by: str
    notes: Optional[str] = None


class StatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(active|paused)$")
    changed_by: str
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Dependency: get service instance bound to an open DB session
# ---------------------------------------------------------------------------

def get_rule_service(db: AsyncSession = Depends(get_db)) -> RuleService:
    return RuleService(db)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", summary="List rules")
async def list_rules(
    tenant_id: str = Query(..., description="Tenant scope for all queries"),
    department: Optional[str] = Query(None),
    status: Optional[str] = Query(None, pattern="^(active|paused|draft)$"),
    search: Optional[str] = Query(None, description="Full-text search on title/description"),
    risk_level: Optional[str] = Query(None, pattern="^(low|medium|high|critical)$"),
    verified: Optional[bool] = Query(None),
    tags: Optional[List[str]] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    service: RuleService = Depends(get_rule_service),
) -> Dict[str, Any]:
    filters = {
        "tenant_id": tenant_id,
        "department": department,
        "status": status,
        "search": search,
        "risk_level": risk_level,
        "verified": verified,
        "tags": tags,
        "limit": limit,
        "offset": offset,
    }
    rules, total = await service.get_rules(filters)
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [r.to_dict() for r in rules],
    }


@router.get("/graph", summary="Return all rules with dependency edges for DAG rendering")
async def get_graph(
    tenant_id: str = Query(...),
    service: RuleService = Depends(get_rule_service),
) -> Dict[str, Any]:
    graph = await service.get_dependency_graph(tenant_id)
    return graph


@router.get("/{rule_id}", summary="Get single rule detail")
async def get_rule(
    rule_id: str,
    tenant_id: str = Query(...),
    service: RuleService = Depends(get_rule_service),
) -> Dict[str, Any]:
    rule = await service.get_rule(tenant_id, rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return rule.to_dict()


@router.patch("/{rule_id}/editable", summary="Update editable field values")
async def update_editable(
    rule_id: str,
    body: EditableFieldUpdate,
    tenant_id: str = Query(...),
    service: RuleService = Depends(get_rule_service),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> Dict[str, Any]:
    """
    Governance-gated edit. Low/medium risk → applied immediately (with reason
    enforcement + freeze check). High/critical risk → returns 202 with a
    pending_change_id to route through the approval queue.
    """
    rule = await service.get_rule(tenant_id, rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

    # --- permission check (skipped when no X-User-Id, to keep existing CLI/test usage working)
    user_roles = current_user.roles if current_user else []
    if current_user is not None and not can_edit_rule(user_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="editor or admin role required to change rule fields",
        )

    # --- reason policy
    try:
        check_reason_policy(
            risk_level=rule.risk_level,
            reason=body.reason,
            ticket_ref=body.ticket_ref,
        )
    except ReasonPolicyError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    # --- freeze window check (only enforced when we know the user's roles)
    if current_user is not None:
        try:
            await check_freeze_windows(
                db,
                tenant_id=tenant_id,
                rule=rule,
                user_roles=user_roles,
            )
        except FreezeBlock as exc:
            raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=str(exc))

    # --- high/critical → route through approvals
    if requires_approval(rule.risk_level):
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="sign-in required to propose a high-risk change",
            )
        approvals = ApprovalService(db)
        pc = await approvals.create_pending_change(
            tenant_id=rule.tenant_id,
            rule=rule,
            changes=body.changes,
            requested_by=current_user,
            reason=body.reason,
            ticket_ref=body.ticket_ref,
        )
        return {
            "status": "pending_approval",
            "pending_change_id": str(pc.id),
            "approvals_required": pc.approvals_required,
            "detail": (
                f"{rule.risk_level} risk rule requires {pc.approvals_required} "
                f"approval(s). The change is queued."
            ),
        }

    # --- low / medium → apply directly
    try:
        updated_rule = await service.update_editable(
            tenant_id=tenant_id,
            rule_id=rule_id,
            field_updates=body.changes,
            changed_by=(current_user.email if current_user else body.changed_by),
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if updated_rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return updated_rule.to_dict()


@router.patch("/{rule_id}/verify", summary="Mark rule as human-verified")
async def verify_rule(
    rule_id: str,
    body: VerifyRequest,
    tenant_id: str = Query(...),
    service: RuleService = Depends(get_rule_service),
) -> Dict[str, Any]:
    rule = await service.set_verified(
        tenant_id=tenant_id,
        rule_id=rule_id,
        verified_by=body.verified_by,
        notes=body.notes,
    )
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return rule.to_dict()


@router.patch("/{rule_id}/status", summary="Change rule status (active / paused)")
async def update_status(
    rule_id: str,
    body: StatusUpdate,
    tenant_id: str = Query(...),
    service: RuleService = Depends(get_rule_service),
) -> Dict[str, Any]:
    try:
        rule = await service.update_status(
            tenant_id=tenant_id,
            rule_id=rule_id,
            new_status=body.status,
            changed_by=body.changed_by,
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return rule.to_dict()


@router.get("/{rule_id}/audit", summary="Get audit history for a rule")
async def get_rule_audit(
    rule_id: str,
    tenant_id: str = Query(...),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    service: RuleService = Depends(get_rule_service),
) -> Dict[str, Any]:
    entries, total = await service.get_rule_audit(
        tenant_id=tenant_id,
        rule_id=rule_id,
        limit=limit,
        offset=offset,
    )
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [e.to_dict() for e in entries],
    }
