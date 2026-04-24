"""
Segregation-of-Duties detection.

Computes SoD alerts on-demand from existing tables. No new storage — alerts
are derived views, so they always reflect current state.

Signals:

  1. self_approved          — a user both requested and approved the same
                              pending change. Should be impossible (blocked
                              at service layer), but we surface any that slip
                              through via DB writes.

  2. single_approver_bulk   — one approver has greenlit > N high/critical
                              changes in the last 30 days without variation
                              (suggests rubber-stamping).

  3. maker_is_owner         — the rule.owner email made the edit themselves
                              (they're supposed to attest, not author).

  4. requester_verified     — same user who extracted/ingested a rule then
                              verified it (no second pair of eyes).
"""
from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit_log import AuditLog
from app.models.pending_change import PendingChange, PendingChangeApproval
from app.models.rule import Rule


async def compute_sod_alerts(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    lookback_days: int = 30,
    bulk_threshold: int = 10,
) -> List[Dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    alerts: List[Dict[str, Any]] = []

    # 1 — self_approved
    pcs = (await db.execute(
        select(PendingChange)
        .where(
            PendingChange.tenant_id == tenant_id,
            PendingChange.requested_at >= cutoff,
        )
        .options(selectinload(PendingChange.approvals))
    )).scalars().all()

    for pc in pcs:
        for approval in pc.approvals or []:
            if approval.approver_id and approval.approver_id == pc.requested_by:
                alerts.append({
                    "signal": "self_approved",
                    "severity": "critical",
                    "title": f"Self-approval detected on {pc.rule_title or pc.rule_id}",
                    "detail": (
                        f"{approval.approver_email or '(unknown)'} approved their own "
                        f"pending change ({pc.id})."
                    ),
                    "subject_email": approval.approver_email,
                    "rule_id": str(pc.rule_id),
                    "occurred_at": approval.decided_at.isoformat() if approval.decided_at else None,
                })

    # 2 — single_approver_bulk (high/critical approvals by one approver)
    approver_counts: Counter[str] = Counter()
    approver_details: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"rules": set(), "last": None})
    for pc in pcs:
        if (pc.rule_risk_level or "").lower() not in {"high", "critical"}:
            continue
        for approval in pc.approvals or []:
            if approval.decision != "approve":
                continue
            key = approval.approver_email or "(unknown)"
            approver_counts[key] += 1
            approver_details[key]["rules"].add(str(pc.rule_id))
            if approval.decided_at and (
                approver_details[key]["last"] is None
                or approval.decided_at > approver_details[key]["last"]
            ):
                approver_details[key]["last"] = approval.decided_at

    for email, count in approver_counts.items():
        if count >= bulk_threshold:
            d = approver_details[email]
            alerts.append({
                "signal": "single_approver_bulk",
                "severity": "high",
                "title": f"High approval volume from {email}",
                "detail": (
                    f"{email} approved {count} high/critical changes across "
                    f"{len(d['rules'])} rule(s) in the last {lookback_days} days. "
                    "Rotate approvers to avoid rubber-stamping."
                ),
                "subject_email": email,
                "rule_id": None,
                "occurred_at": d["last"].isoformat() if d["last"] else None,
            })

    # 3 — maker_is_owner: look at audit_log edits where changed_by matches rule.owner
    audit_stmt = (
        select(AuditLog)
        .where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.action == "editable_update",
            AuditLog.created_at >= cutoff,
        )
    )
    audit_rows = (await db.execute(audit_stmt)).scalars().all()

    rule_owner_by_id = {}
    rule_title_by_id = {}
    for r in (await db.execute(select(Rule).where(Rule.tenant_id == tenant_id))).scalars().all():
        key = str(r.rule_id) if r.rule_id else str(r.id)
        rule_owner_by_id[key] = (r.owner or "").lower()
        rule_title_by_id[key] = r.title

    for a in audit_rows:
        owner = rule_owner_by_id.get(str(a.rule_id))
        if owner and a.changed_by and owner == a.changed_by.lower():
            alerts.append({
                "signal": "maker_is_owner",
                "severity": "medium",
                "title": f"{a.changed_by} edited a rule they also own",
                "detail": (
                    f"The owner of record for '{rule_title_by_id.get(str(a.rule_id), a.rule_id)}' "
                    f"made the edit themselves. Owners should attest, not author."
                ),
                "subject_email": a.changed_by,
                "rule_id": a.rule_id,
                "occurred_at": a.created_at.isoformat() if a.created_at else None,
            })

    # 4 — requester_verified: user who verified also appears as earliest audit entry
    # (indicator that the same person ingested and then self-verified). This is a
    # cheap approximation — a future iteration can join extraction_jobs.
    # (Skipped for v1 to keep signal-to-noise high.)

    return alerts
