"""
seed_compliance.py — demo data for Tier 2 compliance features.

Creates:
  - One attestation campaign (current quarter) for all rules
  - One scan policy (deny secrets/credentials paths)
  - Retention policies on all 3 categories
  - One active legal hold

Run from backend/:
    py -3.13 seed_compliance.py
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select

from app.db import SyncSessionLocal, create_tables_sync
from app.models.attestation import Attestation, AttestationStatus
from app.models.retention import LegalHold, RetentionCategory, RetentionPolicy
from app.models.rule import Rule
from app.models.scan_policy import PolicyMode, ScanPolicy
from app.models.tenant import Tenant


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

        # ---------- scan policy (idempotent by name)
        existing_policy = db.execute(
            select(ScanPolicy).where(
                ScanPolicy.tenant_id == tenant.id,
                ScanPolicy.name == "Default secrets deny-list",
            )
        ).scalar_one_or_none()
        if existing_policy is None:
            db.add(ScanPolicy(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                name="Default secrets deny-list",
                description="Block obvious secrets/keys/credentials files from reaching the extraction agent.",
                mode=PolicyMode.DENY.value,
                allow_patterns=[],
                deny_patterns=[
                    "**/secrets/**",
                    "**/.env*",
                    "**/*.pem",
                    "**/*.key",
                    "**/*_credentials.*",
                    "**/id_rsa*",
                    "**/customers.csv",
                ],
                active=True,
                created_by_email="dave@acme.com",
            ))
            db.commit()

        # ---------- retention policies (upsert per category)
        retention_defaults = {
            RetentionCategory.AUDIT_LOGS.value:       2555,  # 7 years
            RetentionCategory.FILE_ACCESS_LOGS.value:  730,  # 2 years
            RetentionCategory.PENDING_CHANGES.value:   730,
        }
        for cat, days in retention_defaults.items():
            p = db.execute(
                select(RetentionPolicy).where(
                    RetentionPolicy.tenant_id == tenant.id,
                    RetentionPolicy.category == cat,
                )
            ).scalar_one_or_none()
            if p is None:
                db.add(RetentionPolicy(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    category=cat,
                    retention_days=days,
                    active=True,
                    created_by_email="dave@acme.com",
                ))
            else:
                p.retention_days = days
                p.active = True
        db.commit()

        # ---------- legal hold (idempotent by name)
        hold_name = "SOX 2026 audit hold"
        existing_hold = db.execute(
            select(LegalHold).where(
                LegalHold.tenant_id == tenant.id,
                LegalHold.name == hold_name,
            )
        ).scalar_one_or_none()
        if existing_hold is None:
            db.add(LegalHold(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                name=hold_name,
                description="Hold on all billing-related records for SOX audit — placed by legal.",
                rule_ids=[],  # all rules
                categories=["audit_logs", "pending_changes"],
                date_from=now - timedelta(days=180),
                date_to=None,
                active=True,
                placed_by_email="legal@acme.com",
            ))
        db.commit()

        # ---------- attestation campaign for current quarter
        period = _quarter_label(now)
        rules = db.execute(select(Rule).where(Rule.tenant_id == tenant.id)).scalars().all()
        existing_att = {
            a.rule_id for a in db.execute(
                select(Attestation).where(
                    Attestation.tenant_id == tenant.id,
                    Attestation.period_label == period,
                )
            ).scalars().all()
        }
        due = now + timedelta(days=14)
        created = 0
        for rule in rules:
            if rule.id in existing_att:
                continue
            db.add(Attestation(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                rule_id=rule.id,
                rule_title=rule.title,
                period_label=period,
                owner_email=rule.owner or "alice@acme.com",
                due_at=due,
                status=AttestationStatus.PENDING.value,
            ))
            created += 1
        db.commit()

        print(
            f"Seeded: 1 scan policy · {len(retention_defaults)} retention policies · "
            f"1 legal hold · {created} attestations for {period}"
        )


if __name__ == "__main__":
    seed()
