"""
FastAPI dependencies.

get_current_user — demo-mode auth: trusts the X-User-Id header. Real auth
plugs in here later (JWT/SSO) without changing call sites.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.models.user import User


async def get_current_user(
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-Id header required (demo-mode auth).",
        )
    try:
        user_uuid = uuid.UUID(x_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid X-User-Id: {x_user_id!r}",
        )
    stmt = (
        select(User)
        .where(User.id == user_uuid)
        .options(selectinload(User.role_assignments))
    )
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user is None or not user.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user not found or inactive",
        )
    return user


async def get_current_user_optional(
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Same as get_current_user but returns None when header absent."""
    if not x_user_id:
        return None
    try:
        return await get_current_user(x_user_id=x_user_id, db=db)
    except HTTPException:
        return None
