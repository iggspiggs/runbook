"""
Users router — list, create, role-assign. Demo-mode: no passwords.

In real auth this becomes read-only (users sync from SSO/SCIM). For now,
the admin role can create users and assign roles from the frontend.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.deps import get_current_user
from app.models.user import Role, User, UserRole, VALID_ROLES
from app.services.governance.permissions import is_admin

router = APIRouter(prefix="/api/users", tags=["users"])


class CreateUserRequest(BaseModel):
    email: str
    display_name: str
    roles: List[str] = Field(default_factory=list)


class RolesPayload(BaseModel):
    roles: List[str]


def _parse_uuid(value: str, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid UUID for {field_name}: {value!r}",
        )


@router.get("", summary="List users in a tenant")
async def list_users(
    tenant_id: str = Query(...),
    active: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    tenant_uuid = _parse_uuid(tenant_id, "tenant_id")
    stmt = (
        select(User)
        .where(User.tenant_id == tenant_uuid)
        .options(selectinload(User.role_assignments))
        .order_by(User.email)
    )
    if active is not None:
        stmt = stmt.where(User.active.is_(active))
    users = (await db.execute(stmt)).scalars().all()
    return {"items": [u.to_dict() for u in users], "total": len(users)}


@router.get("/me", summary="Return the current X-User-Id user")
async def me(current: User = Depends(get_current_user)) -> Dict[str, Any]:
    return current.to_dict()


@router.post("", summary="Create a user (admin only)")
async def create_user(
    body: CreateUserRequest,
    tenant_id: str = Query(...),
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    if not is_admin(current.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
    tenant_uuid = _parse_uuid(tenant_id, "tenant_id")

    invalid = [r for r in body.roles if r not in VALID_ROLES]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid roles: {invalid}",
        )

    user = User(tenant_id=tenant_uuid, email=body.email.strip().lower(),
                display_name=body.display_name, active=True)
    for r in body.roles:
        user.role_assignments.append(UserRole(role=r))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    # Re-load with eager roles
    user = (await db.execute(
        select(User).where(User.id == user.id).options(selectinload(User.role_assignments))
    )).scalar_one()
    return user.to_dict()


@router.put("/{user_id}/roles", summary="Replace roles on a user (admin only)")
async def set_roles(
    user_id: str,
    body: RolesPayload,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    if not is_admin(current.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")

    uid = _parse_uuid(user_id, "user_id")
    invalid = [r for r in body.roles if r not in VALID_ROLES]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid roles: {invalid}",
        )

    user = (await db.execute(
        select(User).where(User.id == uid).options(selectinload(User.role_assignments))
    )).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

    # Remove roles not in the new set
    keep = set(body.roles)
    user.role_assignments = [ra for ra in user.role_assignments if ra.role in keep]
    existing = {ra.role for ra in user.role_assignments}
    for r in body.roles:
        if r not in existing:
            user.role_assignments.append(UserRole(role=r))
    await db.commit()
    await db.refresh(user)
    user = (await db.execute(
        select(User).where(User.id == user.id).options(selectinload(User.role_assignments))
    )).scalar_one()
    return user.to_dict()
