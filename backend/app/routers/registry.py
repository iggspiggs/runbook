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
) -> Dict[str, Any]:
    """
    Accepts a map of field_name → new_value.  The service validates each
    value against the declared type of the editable field and rejects unknown
    or non-editable fields with a 422. Every accepted change is written to
    the audit log atomically with the rule update.
    """
    try:
        updated_rule = await service.update_editable(
            tenant_id=tenant_id,
            rule_id=rule_id,
            field_updates=body.changes,
            changed_by=body.changed_by,
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
