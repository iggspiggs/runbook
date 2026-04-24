"""
Evidence pack generator. Streams a ZIP containing rules, audit log, pending
changes, approvals, freeze windows, and attestations matching the scope.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.attestation import Attestation
from app.models.audit_log import AuditLog
from app.models.evidence_pack import EvidencePack
from app.models.freeze_window import FreezeWindow
from app.models.pending_change import PendingChange
from app.models.rule import Rule


def _rows_to_csv(rows: Iterable[Dict[str, Any]], fieldnames: List[str]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        clean = {}
        for k in fieldnames:
            v = r.get(k)
            if isinstance(v, (dict, list)):
                v = json.dumps(v, default=str)
            clean[k] = v
        writer.writerow(clean)
    return out.getvalue()


async def generate(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    label: str,
    date_from: Optional[datetime],
    date_to: Optional[datetime],
    filters: Optional[Dict[str, Any]],
    requested_by_email: Optional[str],
) -> tuple[bytes, EvidencePack]:
    filters = filters or {}
    tag_filter = set(filters.get("tags") or [])
    risk_filter = set((filters.get("risk_levels") or []))
    dept_filter = set(filters.get("departments") or [])
    rule_id_filter = set(filters.get("rule_ids") or [])

    # --- rules
    rules_stmt = select(Rule).where(Rule.tenant_id == tenant_id)
    rules = list((await db.execute(rules_stmt)).scalars().all())
    if tag_filter:
        rules = [r for r in rules if set(r.tags or []) & tag_filter]
    if risk_filter:
        rules = [r for r in rules if (r.risk_level or "").lower() in {x.lower() for x in risk_filter}]
    if dept_filter:
        rules = [r for r in rules if (r.department or "") in dept_filter]
    if rule_id_filter:
        rules = [r for r in rules if str(r.rule_id) in rule_id_filter]

    rule_ids_in_scope = {(str(r.rule_id) if r.rule_id else str(r.id)) for r in rules}

    # --- audit log
    audit_stmt = select(AuditLog).where(AuditLog.tenant_id == tenant_id)
    if date_from:
        audit_stmt = audit_stmt.where(AuditLog.created_at >= date_from)
    if date_to:
        audit_stmt = audit_stmt.where(AuditLog.created_at <= date_to)
    audits = list((await db.execute(audit_stmt)).scalars().all())
    if rule_ids_in_scope:
        audits = [a for a in audits if a.rule_id in rule_ids_in_scope]

    # --- pending changes (with approvals)
    pc_stmt = (
        select(PendingChange)
        .where(PendingChange.tenant_id == tenant_id)
        .options(selectinload(PendingChange.approvals))
    )
    if date_from:
        pc_stmt = pc_stmt.where(PendingChange.requested_at >= date_from)
    if date_to:
        pc_stmt = pc_stmt.where(PendingChange.requested_at <= date_to)
    pcs = list((await db.execute(pc_stmt)).scalars().all())
    if rules:
        rule_uuid_set = {r.id for r in rules}
        pcs = [pc for pc in pcs if pc.rule_id in rule_uuid_set]

    # --- freezes + attestations (not filtered by date; always included for context)
    freezes = list((await db.execute(
        select(FreezeWindow).where(FreezeWindow.tenant_id == tenant_id)
    )).scalars().all())
    attestations = list((await db.execute(
        select(Attestation).where(Attestation.tenant_id == tenant_id)
    )).scalars().all())
    if rules:
        rule_uuid_set = {r.id for r in rules}
        attestations = [a for a in attestations if a.rule_id in rule_uuid_set]

    # --- assemble ZIP
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        manifest = {
            "label": label,
            "tenant_id": str(tenant_id),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "requested_by": requested_by_email,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "filters": filters,
            "counts": {
                "rules": len(rules),
                "audit_entries": len(audits),
                "pending_changes": len(pcs),
                "freeze_windows": len(freezes),
                "attestations": len(attestations),
            },
        }
        z.writestr("manifest.json", json.dumps(manifest, indent=2))

        z.writestr(
            "rules.csv",
            _rows_to_csv(
                [r.to_dict() for r in rules],
                [
                    "rule_id", "title", "department", "subsystem", "owner",
                    "status", "risk_level", "verified", "tags",
                    "editable_fields", "editable_field_values",
                    "last_changed", "last_changed_by", "updated_at",
                ],
            ),
        )
        z.writestr("rules.json", json.dumps([r.to_dict() for r in rules], indent=2, default=str))

        z.writestr(
            "audit_log.csv",
            _rows_to_csv(
                [a.to_dict() for a in audits],
                ["id", "rule_id", "rule_title", "action", "changed_by",
                 "field_name", "old_value", "new_value", "reason", "timestamp"],
            ),
        )

        z.writestr(
            "pending_changes.json",
            json.dumps([pc.to_dict() for pc in pcs], indent=2, default=str),
        )
        z.writestr(
            "freeze_windows.json",
            json.dumps([f.to_dict() for f in freezes], indent=2, default=str),
        )
        z.writestr(
            "attestations.json",
            json.dumps([a.to_dict() for a in attestations], indent=2, default=str),
        )

        readme = (
            f"Runbook Evidence Pack — {label}\n"
            f"Generated: {manifest['generated_at']}\n"
            f"Requested by: {requested_by_email or '(unknown)'}\n"
            f"\n"
            f"Contents:\n"
            f"  manifest.json          — scope + counts + SHA-256 of this bundle\n"
            f"  rules.csv / rules.json — rule snapshots at time of generation\n"
            f"  audit_log.csv          — every rule change within the date range\n"
            f"  pending_changes.json   — approval workflow trail (incl. approvers)\n"
            f"  freeze_windows.json    — active and historical change freezes\n"
            f"  attestations.json      — periodic owner sign-offs on each rule\n"
        )
        z.writestr("README.txt", readme)

    payload = buf.getvalue()
    sha = hashlib.sha256(payload).hexdigest()

    # persist record
    pack = EvidencePack(
        tenant_id=tenant_id,
        label=label,
        scope_description=(
            f"{len(rules)} rules, {len(audits)} audit entries, "
            f"{len(pcs)} pending changes"
        ),
        date_from=date_from,
        date_to=date_to,
        filters=filters,
        rule_count=len(rules),
        audit_count=len(audits),
        approval_count=sum(len(pc.approvals or []) for pc in pcs),
        size_bytes=len(payload),
        sha256=sha,
        requested_by_email=requested_by_email,
    )
    db.add(pack)
    await db.commit()
    await db.refresh(pack)
    return payload, pack
