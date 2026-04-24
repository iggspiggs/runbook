"""
Freeze-window enforcement — blocks edits that fall inside an active
calendar window, unless the caller's role is in bypass_roles.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.freeze_window import FreezeScope, FreezeWindow


class FreezeBlock(Exception):
    """Raised when an edit is blocked by an active freeze window."""

    def __init__(self, window: FreezeWindow, message: str) -> None:
        super().__init__(message)
        self.window = window


def _window_matches_rule(window: FreezeWindow, rule) -> bool:
    if window.scope == FreezeScope.ALL.value:
        return True

    values = set(window.scope_values or [])
    if window.scope == FreezeScope.BY_TAG.value:
        rule_tags = set(rule.tags or [])
        return bool(values & rule_tags)
    if window.scope == FreezeScope.BY_RISK.value:
        return (rule.risk_level or "").lower() in {v.lower() for v in values}
    if window.scope == FreezeScope.BY_DEPARTMENT.value:
        return (rule.department or "") in values
    return False


async def check_freeze_windows(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID | str,
    rule,
    user_roles: Iterable[str],
    now: Optional[datetime] = None,
) -> None:
    """
    Raises FreezeBlock if an active window covers this rule and the user's
    roles do not include any of the window's bypass_roles.
    """
    if isinstance(tenant_id, str):
        tenant_id = uuid.UUID(tenant_id)
    now = now or datetime.now(timezone.utc)

    stmt = (
        select(FreezeWindow)
        .where(
            FreezeWindow.tenant_id == tenant_id,
            FreezeWindow.active.is_(True),
            FreezeWindow.start_at <= now,
            FreezeWindow.end_at >= now,
        )
    )
    all_windows: List[FreezeWindow] = list((await db.execute(stmt)).scalars().all())

    # SQLite strips tzinfo; do a Python-side check to avoid false-positives from
    # the SQL comparison when the stored ISO string lacks a zone.
    def _aware(dt):
        if dt is None:
            return None
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

    windows = [
        w for w in all_windows
        if _aware(w.start_at) and _aware(w.end_at)
        and _aware(w.start_at) <= now <= _aware(w.end_at)
    ]

    user_roleset = set(user_roles)

    for w in windows:
        if not _window_matches_rule(w, rule):
            continue
        bypass = set(w.bypass_roles or [])
        if bypass and (user_roleset & bypass):
            continue  # role can bypass
        raise FreezeBlock(
            w,
            f"Edits are frozen until {w.end_at.isoformat()} "
            f"by '{w.name}'."
            + (f" Scope: {w.scope} ({', '.join(w.scope_values or [])})."
               if w.scope_values else f" Scope: {w.scope}."),
        )
