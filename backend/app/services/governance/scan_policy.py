"""
Scan-scope policy evaluation.

Called by the extractor BEFORE a file is opened so a denied path never
reaches the LLM or the access log (except as a 'policy_denied' entry).
"""
from __future__ import annotations

import fnmatch
import uuid
from typing import Iterable, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scan_policy import PolicyMode, ScanPolicy


def _match_any(path: str, patterns: Iterable[str]) -> Optional[str]:
    for pat in patterns:
        if fnmatch.fnmatch(path, pat):
            return pat
        # also match against basename — makes "*.env*" work without **/
        if fnmatch.fnmatch(path.rsplit("/", 1)[-1], pat):
            return pat
    return None


def evaluate(
    path: str,
    *,
    mode: str,
    allow_patterns: List[str],
    deny_patterns: List[str],
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Returns (allowed, policy_name_match, reason).
    policy_name_match is the matched pattern; reason explains the verdict.
    """
    denied = _match_any(path, deny_patterns)
    if denied and mode in (PolicyMode.DENY.value, PolicyMode.HYBRID.value):
        return False, denied, f"matches deny pattern {denied!r}"

    if mode == PolicyMode.ALLOW.value:
        matched = _match_any(path, allow_patterns)
        if matched is None:
            return False, None, "allow-only mode and no allow pattern matches"
        return True, matched, f"matches allow pattern {matched!r}"

    if mode == PolicyMode.HYBRID.value and allow_patterns:
        matched = _match_any(path, allow_patterns)
        if matched is None:
            return False, None, "hybrid mode: no allow pattern matches"
        return True, matched, f"matches allow pattern {matched!r}"

    return True, None, "allowed (no blocking policy)"


async def get_active_policy(
    db: AsyncSession, tenant_id: uuid.UUID
) -> Optional[ScanPolicy]:
    """Returns the single active policy for the tenant (most recently created)."""
    stmt = (
        select(ScanPolicy)
        .where(ScanPolicy.tenant_id == tenant_id, ScanPolicy.active.is_(True))
        .order_by(ScanPolicy.created_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()
