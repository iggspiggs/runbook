"""
Permission checks. The whole product contract is:

    Viewer       — read only
    Editor       — can edit low/medium risk rules; proposals on high/critical
    Approver     — can approve pending_changes (cannot self-approve)
    Admin        — everything Editor + Approver can do, plus freeze windows + users
    Auditor      — read-only, including audit log export

Approval policy by risk level:

    low        → direct apply, 0 approvals required
    medium     → direct apply if editor+, 0 approvals required
    high       → 1 approval required (approver or admin, not the requester)
    critical   → 2 approvals required

These numbers live in one place so changing policy is one edit.
"""
from __future__ import annotations

from typing import Iterable

from app.models.user import Role


class PermissionError_(Exception):
    """Raised when a user lacks the role needed for an action."""


_READ_ROLES = {Role.VIEWER.value, Role.EDITOR.value, Role.APPROVER.value,
               Role.ADMIN.value, Role.AUDITOR.value}
_EDIT_ROLES = {Role.EDITOR.value, Role.ADMIN.value}
_APPROVE_ROLES = {Role.APPROVER.value, Role.ADMIN.value}
_ADMIN_ROLES = {Role.ADMIN.value}


def _has_any(user_roles: Iterable[str], allowed: set[str]) -> bool:
    return any(r in allowed for r in user_roles)


def can_read(user_roles: Iterable[str]) -> bool:
    return _has_any(user_roles, _READ_ROLES)


def can_edit_rule(user_roles: Iterable[str]) -> bool:
    return _has_any(user_roles, _EDIT_ROLES)


def can_approve(user_roles: Iterable[str]) -> bool:
    return _has_any(user_roles, _APPROVE_ROLES)


def is_admin(user_roles: Iterable[str]) -> bool:
    return _has_any(user_roles, _ADMIN_ROLES)


# Approval policy by risk level --------------------------------------------

_APPROVALS_BY_RISK: dict[str, int] = {
    "low": 0,
    "medium": 0,
    "high": 1,
    "critical": 2,
}


def required_approvals_for(risk_level: str | None) -> int:
    if not risk_level:
        return 0
    return _APPROVALS_BY_RISK.get(risk_level.lower(), 0)


def requires_approval(risk_level: str | None) -> bool:
    return required_approvals_for(risk_level) > 0
