"""
seed_governance_demo.py — repopulates Governance & Compliance demo data that
gets exhausted once a reviewer clicks through the flow in a demo session.

Creates / refreshes:
  - A fresh attestation campaign for the current quarter (resets any prior
    responses so the Attestations tab has pending + overdue + attested items)
  - 3 new pending_changes in PENDING status on high/critical risk rules
    so the Approvals tab isn't empty
  - SoD-triggering signals:
      * self_approved — one pending_change where requested_by == approver_id
      * single_approver_bulk — 12 high-risk approvals all by Carol
      * maker_is_owner — an audit_log edit where changed_by == rule.owner

Run from backend/:
    py -3.13 seed_governance_demo.py
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select, delete

from app.db import SyncSessionLocal, create_tables_sync
from app.models.attestation import Attestation, AttestationStatus
from app.models.audit_log import AuditLog
from app.models.pending_change import (
    PendingChange,
    PendingChangeApproval,
    PendingStatus,
)
from app.models.rule import Rule
from app.models.tenant import Tenant
from app.models.user import User


DEMO_TENANT_SLUG = "acme-logistics"


def _quarter_label(now: datetime) -> str:
    q = (now.month - 1) // 3 + 1
    return f"{now.year}-Q{q}"


def seed() -> None:
    create_tables_sync()
    now = datetime.now(timezone.utc)

    with SyncSessionLocal() as db:
        tenant = db.execute(
            select(Tenant).where(Tenant.slug == DEMO_TENANT_SLUG)
        ).scalar_one_or_none()
        if tenant is None:
            print("Demo tenant not found. Run seed_demo.py first.")
            return

        users = {
            u.email: u for u in
            db.execute(select(User).where(User.tenant_id == tenant.id)).scalars().all()
        }
        needed = ["alice@acme.com", "bob@acme.com", "carol@acme.com", "dave@acme.com", "eve@acme.com"]
        missing = [e for e in needed if e not in users]
        if missing:
            print(f"Missing demo users: {missing}. Run seed_governance.py first.")
            return

        bob, carol, dave = users["bob@acme.com"], users["carol@acme.com"], users["dave@acme.com"]

        rules = db.execute(select(Rule).where(Rule.tenant_id == tenant.id)).scalars().all()
        high_rules = [r for r in rules if (r.risk_level or "").lower() in ("high", "critical")]
        if not high_rules:
            print("No high/critical rules found — skipping approval demo data.")
            return

        # -------------------- Fresh attestation campaign (this quarter) ----
        period = _quarter_label(now)
        # Delete prior attestations for this period so responses reset for demos
        db.execute(
            delete(Attestation).where(
                Attestation.tenant_id == tenant.id,
                Attestation.period_label == period,
            )
        )
        db.commit()

        due_soon = now + timedelta(days=5)        # most pending
        already_overdue = now - timedelta(days=2)  # a few overdue
        attested_days_ago = now - timedelta(days=1)

        for i, rule in enumerate(rules):
            # Determine status mix for a realistic demo
            if i % 8 == 0:
                # overdue-pending
                db.add(Attestation(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id, rule_id=rule.id, rule_title=rule.title,
                    period_label=period,
                    owner_email=rule.owner or "alice@acme.com",
                    due_at=already_overdue,
                    status=AttestationStatus.OVERDUE.value,
                ))
            elif i % 9 == 0:
                # already attested
                db.add(Attestation(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id, rule_id=rule.id, rule_title=rule.title,
                    period_label=period,
                    owner_email=rule.owner or "bob@acme.com",
                    due_at=due_soon,
                    status=AttestationStatus.ATTESTED.value,
                    responded_by_email=rule.owner or "bob@acme.com",
                    responded_at=attested_days_ago,
                    response_note="reviewed, still accurate",
                ))
            else:
                db.add(Attestation(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id, rule_id=rule.id, rule_title=rule.title,
                    period_label=period,
                    owner_email=rule.owner or "alice@acme.com",
                    due_at=due_soon,
                    status=AttestationStatus.PENDING.value,
                ))
        db.commit()

        # -------------------- Pending changes for the approval queue ------
        for i, rule in enumerate(high_rules[:3]):
            existing = db.execute(
                select(PendingChange).where(
                    PendingChange.tenant_id == tenant.id,
                    PendingChange.rule_id == rule.id,
                    PendingChange.status == PendingStatus.PENDING.value,
                )
            ).scalar_one_or_none()
            if existing:
                continue

            field_name = "threshold_usd"
            ef = rule.editable_fields or []
            if ef:
                field_name = ef[0].get("field_name") or ef[0].get("name") or field_name

            db.add(PendingChange(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                rule_id=rule.id,
                rule_title=rule.title,
                rule_risk_level=rule.risk_level,
                changes={field_name: (100 + i * 50)},
                reason=[
                    "Raising threshold to reduce operator queue pressure; validated in staging for 48h.",
                    "Adjusting based on Q1 data showing volume has doubled — value should scale with it.",
                    "Compliance request following internal audit finding #A-2026-14.",
                ][i],
                ticket_ref=f"FIN-{100 + i}",
                status=PendingStatus.PENDING.value,
                approvals_required=1 if (rule.risk_level or "").lower() == "high" else 2,
                requested_by=bob.id,
                requested_by_email=bob.email,
                requested_at=now - timedelta(hours=i * 6 + 2),
                expires_at=now + timedelta(days=7 - i),
            ))
        db.commit()

        # -------------------- SoD: self_approved --------------------------
        # Intentionally bypass service validation by writing directly to DB.
        rule_for_self = high_rules[0]
        sa_pc_id = uuid.uuid4()
        existing_sa = db.execute(
            select(PendingChange).where(
                PendingChange.tenant_id == tenant.id,
                PendingChange.rule_title == rule_for_self.title,
                PendingChange.requested_by == carol.id,
            )
        ).scalar_one_or_none()
        if existing_sa is None:
            pc = PendingChange(
                id=sa_pc_id,
                tenant_id=tenant.id,
                rule_id=rule_for_self.id,
                rule_title=rule_for_self.title,
                rule_risk_level=rule_for_self.risk_level,
                changes={"threshold_usd": 500},
                reason="Quick fix before demo — self-approved by accident.",
                ticket_ref="DEMO-SOD-1",
                status=PendingStatus.APPLIED.value,
                approvals_required=1,
                requested_by=carol.id,
                requested_by_email=carol.email,
                requested_at=now - timedelta(hours=3),
                applied_at=now - timedelta(hours=2, minutes=55),
                applied_by=carol.id,
            )
            db.add(pc)
            db.flush()
            db.add(PendingChangeApproval(
                id=uuid.uuid4(),
                pending_change_id=pc.id,
                approver_id=carol.id,  # SAME as requested_by — this is the SoD violation
                approver_email=carol.email,
                decision="approve",
                decided_at=now - timedelta(hours=2, minutes=58),
                note="lgtm",
            ))
            db.commit()

        # -------------------- SoD: single_approver_bulk -------------------
        # Carol approves 12 recent high/critical changes (trigger bulk_threshold=10).
        bulk_rules = high_rules[: min(12, len(high_rules))]
        if len(bulk_rules) >= 10:
            # Clean any old bulk demo entries first
            db.execute(
                delete(PendingChangeApproval).where(
                    PendingChangeApproval.note == "bulk-demo"
                )
            )
            db.commit()

            for i, rule in enumerate(bulk_rules):
                # Find-or-create an applied pending_change for this rule
                pc = PendingChange(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    rule_id=rule.id,
                    rule_title=rule.title,
                    rule_risk_level=rule.risk_level,
                    changes={"setting": f"bulk-{i}"},
                    reason="Routine threshold tune — demo seed.",
                    ticket_ref=f"DEMO-BULK-{i}",
                    status=PendingStatus.APPLIED.value,
                    approvals_required=1,
                    requested_by=bob.id,
                    requested_by_email=bob.email,
                    requested_at=now - timedelta(days=20, hours=i),
                    applied_at=now - timedelta(days=20, hours=i - 1),
                    applied_by=carol.id,
                )
                db.add(pc)
                db.flush()
                db.add(PendingChangeApproval(
                    id=uuid.uuid4(),
                    pending_change_id=pc.id,
                    approver_id=carol.id,
                    approver_email=carol.email,
                    decision="approve",
                    decided_at=now - timedelta(days=20, hours=i, minutes=-5),
                    note="bulk-demo",
                ))
            db.commit()

        # -------------------- SoD: maker_is_owner -------------------------
        # Pick a rule whose owner matches a user we have, then write an audit
        # entry where changed_by equals that owner (= self-edit by owner).
        maker_rule = next(
            (r for r in rules if (r.owner or "").lower() in {u.lower() for u in users}),
            None,
        )
        if maker_rule is None:
            # Force it: assign alice as owner on some rule
            maker_rule = rules[0]
            maker_rule.owner = "alice@acme.com"
            db.commit()

        owner_email = maker_rule.owner
        existing_maker = db.execute(
            select(AuditLog).where(
                AuditLog.tenant_id == tenant.id,
                AuditLog.rule_id == (str(maker_rule.rule_id) if maker_rule.rule_id else str(maker_rule.id)),
                AuditLog.changed_by == owner_email,
                AuditLog.reason.like("demo-sod-maker-is-owner%"),
            )
        ).scalar_one_or_none()
        if existing_maker is None:
            db.add(AuditLog(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                rule_id=str(maker_rule.rule_id) if maker_rule.rule_id else str(maker_rule.id),
                rule_title=maker_rule.title,
                action="editable_update",
                field_name="threshold_usd",
                old_value=json.dumps(1000),
                new_value=json.dumps(1500),
                changed_by=owner_email,
                reason="demo-sod-maker-is-owner — rule owner edited their own rule",
            ))
            db.commit()

        print(
            f"Seeded governance demo data: fresh {period} attestations, "
            f"3 pending changes, SoD triggers (self_approved + single_approver_bulk + maker_is_owner)."
        )


if __name__ == "__main__":
    seed()
