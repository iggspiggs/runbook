"""
Reason-for-change enforcement.

Policy scales with risk_level:
    low        → reason optional
    medium     → reason required, min 10 chars
    high       → reason required, min 20 chars, ticket_ref required
    critical   → reason required, min 20 chars, ticket_ref required
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


class ReasonPolicyError(Exception):
    """Raised when a proposed change doesn't meet the reason-policy bar."""


@dataclass
class _Policy:
    reason_required: bool
    min_reason_chars: int
    ticket_required: bool


_POLICIES: dict[str, _Policy] = {
    "low":      _Policy(False, 0, False),
    "medium":   _Policy(True, 10, False),
    "high":     _Policy(True, 20, True),
    "critical": _Policy(True, 20, True),
}

# Ticket-reference shape: PROJ-123 style. Kept permissive so it can match
# JIRA / Linear / GitHub / internal tracker IDs.
_TICKET_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{1,16}-\d{1,8}$|^#\d{1,8}$")


def policy_for(risk_level: str | None) -> _Policy:
    if not risk_level:
        return _POLICIES["low"]
    return _POLICIES.get(risk_level.lower(), _POLICIES["low"])


def check_reason_policy(
    *,
    risk_level: str | None,
    reason: Optional[str],
    ticket_ref: Optional[str],
) -> None:
    """Raises ReasonPolicyError if the policy for risk_level is not satisfied."""
    p = policy_for(risk_level)

    r = (reason or "").strip()
    if p.reason_required and not r:
        raise ReasonPolicyError(
            f"A reason is required for {risk_level or 'this'} risk rules."
        )
    if p.min_reason_chars and len(r) < p.min_reason_chars:
        raise ReasonPolicyError(
            f"Reason must be at least {p.min_reason_chars} characters "
            f"(got {len(r)}) for {risk_level or 'this'} risk rules."
        )

    if p.ticket_required:
        t = (ticket_ref or "").strip()
        if not t:
            raise ReasonPolicyError(
                f"A ticket reference is required for {risk_level} risk rules."
            )
        if not _TICKET_RE.match(t):
            raise ReasonPolicyError(
                f"Ticket reference {t!r} doesn't look like a valid ID "
                "(expected something like JIRA-123, LINEAR-456, or #789)."
            )
