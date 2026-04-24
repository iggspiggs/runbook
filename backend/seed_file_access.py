"""
seed_file_access.py — demo data for the Data Access page.

Inserts ~30 FileAccessLog rows across 3 synthetic extraction jobs for the
Acme Logistics demo tenant.  Safe to re-run: deletes existing rows for the
synthetic job IDs first so counts stay stable.

Run from the backend/ directory:
    py -3.13 seed_file_access.py
"""
from __future__ import annotations

import hashlib
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select

from app.db import SyncSessionLocal, create_tables_sync
from app.models.tenant import Tenant
from app.models.file_access_log import (
    FileAccessAction,
    FileAccessLog,
    FileSensitivity,
    FileSourceType,
)
from app.services.file_access.access_logger import classify_sensitivity


DEMO_TENANT_SLUG = "acme-logistics"

# Synthetic job IDs so re-runs are idempotent.
JOB_A = "seed-job-acme-backend-001"
JOB_B = "seed-job-acme-billing-002"
JOB_C = "seed-job-dms-policies-003"

NOW = datetime.now(timezone.utc)


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _ago(minutes: int) -> datetime:
    return NOW - timedelta(minutes=minutes)


ENTRIES: list[dict] = [
    # ── Job A: acme-backend git repo (recent, healthy) ────────────────────
    dict(job=JOB_A, source_type=FileSourceType.GIT.value, source_name="github.com/acme/backend",
         path="app/jobs/billing_cycle.py", action="read", size=4821,
         lang="python", reason="pattern match: cron_expression, threshold_pattern", ago=5),
    dict(job=JOB_A, source_type=FileSourceType.GIT.value, source_name="github.com/acme/backend",
         path="app/jobs/retry_policy.py", action="read", size=2110,
         lang="python", reason="pattern match: retry_pattern", ago=5),
    dict(job=JOB_A, source_type=FileSourceType.GIT.value, source_name="github.com/acme/backend",
         path="app/config/schedules.yaml", action="read", size=912,
         lang="yaml", reason="pattern match: cron_expression, schedule_keyword", ago=5),
    dict(job=JOB_A, source_type=FileSourceType.GIT.value, source_name="github.com/acme/backend",
         path="app/services/notify.py", action="read", size=6301,
         lang="python", reason="pattern match: send_email, notification_keyword", ago=5),
    dict(job=JOB_A, source_type=FileSourceType.GIT.value, source_name="github.com/acme/backend",
         path="app/routers/webhooks.py", action="read", size=3102,
         lang="python", reason="pattern match: event_handler, webhook_url", ago=5),
    dict(job=JOB_A, source_type=FileSourceType.GIT.value, source_name="github.com/acme/backend",
         path="app/README.md", action="skipped_ext", size=1800,
         lang=None, reason="unsupported extension .md", ago=5),
    dict(job=JOB_A, source_type=FileSourceType.GIT.value, source_name="github.com/acme/backend",
         path="docs/architecture.pdf", action="skipped_ext", size=128_456,
         lang=None, reason="unsupported extension .pdf", ago=5),
    dict(job=JOB_A, source_type=FileSourceType.GIT.value, source_name="github.com/acme/backend",
         path="data/historical_dump.sql", action="skipped_size", size=812_404,
         lang="sql", reason=">500000 bytes", ago=5),
    # Accidental sensitive read in job A — triggers the classifier
    dict(job=JOB_A, source_type=FileSourceType.GIT.value, source_name="github.com/acme/backend",
         path=".env.production", action="read", size=612,
         lang="dotenv", reason="pattern match: config_threshold", ago=5),
    dict(job=JOB_A, source_type=FileSourceType.GIT.value, source_name="github.com/acme/backend",
         path="scripts/ops/deploy.sh", action="read", size=2402,
         lang="bash", reason="pattern match: schedule_keyword, api_call", ago=5),

    # ── Job B: acme-billing git repo ─────────────────────────────────────
    dict(job=JOB_B, source_type=FileSourceType.GIT.value, source_name="github.com/acme/billing",
         path="src/engine/dunning.py", action="read", size=5204,
         lang="python", reason="pattern match: threshold_pattern, if_then_block", ago=70),
    dict(job=JOB_B, source_type=FileSourceType.GIT.value, source_name="github.com/acme/billing",
         path="src/engine/late_fee.py", action="read", size=2841,
         lang="python", reason="pattern match: comparison_with_const, threshold_pattern", ago=70),
    dict(job=JOB_B, source_type=FileSourceType.GIT.value, source_name="github.com/acme/billing",
         path="config/feature_flags.toml", action="read", size=742,
         lang="toml", reason="pattern match: feature_flag", ago=70),
    dict(job=JOB_B, source_type=FileSourceType.GIT.value, source_name="github.com/acme/billing",
         path="src/approval/manager_approval.py", action="read", size=3911,
         lang="python", reason="pattern match: approval_gate", ago=70),
    # Credentials file — should be flagged by classifier
    dict(job=JOB_B, source_type=FileSourceType.GIT.value, source_name="github.com/acme/billing",
         path="deploy/secrets/prod_credentials.json", action="read", size=420,
         lang="json", reason="pattern match: config_threshold", ago=70),
    # PEM key
    dict(job=JOB_B, source_type=FileSourceType.GIT.value, source_name="github.com/acme/billing",
         path="deploy/keys/stripe_webhook.pem", action="read", size=1704,
         lang=None, reason="pattern match: webhook_url", ago=70),
    dict(job=JOB_B, source_type=FileSourceType.GIT.value, source_name="github.com/acme/billing",
         path="tests/fixtures/sample_invoice.pdf", action="skipped_ext", size=24_112,
         lang=None, reason="unsupported extension .pdf", ago=70),
    dict(job=JOB_B, source_type=FileSourceType.GIT.value, source_name="github.com/acme/billing",
         path="tests/fixtures/unreadable.bin", action="skipped_error", size=1024,
         lang=None, reason="read failed: UnicodeDecodeError", ago=70),

    # ── Job C: DMS scan (document management system, hypothetical) ───────
    dict(job=JOB_C, source_type=FileSourceType.DMS.value, source_name="sharepoint/ops-policies",
         path="Policies/SLA_matrix.yaml", action="read", size=2300,
         lang="yaml", reason="pattern match: threshold_pattern", ago=1440),
    dict(job=JOB_C, source_type=FileSourceType.DMS.value, source_name="sharepoint/ops-policies",
         path="Policies/escalation_tree.json", action="read", size=1872,
         lang="json", reason="pattern match: notification_keyword, approval_gate", ago=1440),
    # Customer data — flagged
    dict(job=JOB_C, source_type=FileSourceType.DMS.value, source_name="sharepoint/ops-policies",
         path="Exports/Customers.csv", action="read", size=402_112,
         lang=None, reason="pattern match: threshold_pattern (false positive)", ago=1440),
    dict(job=JOB_C, source_type=FileSourceType.DMS.value, source_name="sharepoint/ops-policies",
         path="Archive/2024/backup_db_jan.sql", action="read", size=98_432,
         lang="sql", reason="pattern match: cron_expression", ago=1440),
    dict(job=JOB_C, source_type=FileSourceType.DMS.value, source_name="sharepoint/ops-policies",
         path="Templates/invoice_template.docx", action="skipped_ext", size=18_200,
         lang=None, reason="unsupported extension .docx", ago=1440),
    dict(job=JOB_C, source_type=FileSourceType.DMS.value, source_name="sharepoint/ops-policies",
         path="Meeting_Notes/2024-11-02.txt", action="skipped_ext", size=4200,
         lang=None, reason="unsupported extension .txt", ago=1440),
    dict(job=JOB_C, source_type=FileSourceType.CLOUD.value, source_name="s3://acme-ops-backups",
         path="nightly/runbook_rules_2024-10-15.json", action="read", size=48_110,
         lang="json", reason="pattern match: schedule_keyword", ago=1440),
    # Cloud PII export — flagged
    dict(job=JOB_C, source_type=FileSourceType.CLOUD.value, source_name="s3://acme-ops-backups",
         path="exports/pii_redacted_2024Q3.json", action="read", size=120_440,
         lang="json", reason="pattern match: notification_keyword", ago=1440),
]


# Paths that the content classifier would have flagged; we seed pii_tags so
# the UI renders chips even without actually running the classifier.
_SEEDED_PII_TAGS: dict[str, list[dict]] = {
    "deploy/secrets/prod_credentials.json": [
        {"tag": "aws_key", "label": "AWS access key ID", "count": 1},
        {"tag": "jwt", "label": "JWT token", "count": 2},
    ],
    "deploy/keys/stripe_webhook.pem": [
        {"tag": "aws_key", "label": "AWS access key ID", "count": 1},
    ],
    "Exports/Customers.csv": [
        {"tag": "email_bulk", "label": "Bulk email list", "count": 1},
        {"tag": "phone_us",   "label": "US phone number", "count": 412},
        {"tag": "ssn",        "label": "US SSN",           "count": 3},
    ],
    "exports/pii_redacted_2024Q3.json": [
        {"tag": "ssn",      "label": "US SSN", "count": 12},
        {"tag": "phone_us", "label": "US phone number", "count": 87},
    ],
    ".env.production": [
        {"tag": "aws_key", "label": "AWS access key ID", "count": 1},
    ],
}


def seed() -> None:
    create_tables_sync()
    with SyncSessionLocal() as db:
        tenant = db.execute(
            select(Tenant).where(Tenant.slug == DEMO_TENANT_SLUG)
        ).scalar_one_or_none()
        if tenant is None:
            print(f"Demo tenant {DEMO_TENANT_SLUG!r} not found. Run seed_demo.py first.")
            return

        # Idempotent: remove rows from these synthetic jobs before re-inserting.
        synthetic_jobs = [JOB_A, JOB_B, JOB_C]
        existing = db.execute(
            select(FileAccessLog).where(
                FileAccessLog.tenant_id == tenant.id,
                FileAccessLog.extraction_job_id.in_(synthetic_jobs),
            )
        ).scalars().all()
        for row in existing:
            db.delete(row)
        db.flush()

        rows = []
        for e in ENTRIES:
            sensitivity = classify_sensitivity(e["path"])
            pii_tags = _SEEDED_PII_TAGS.get(e["path"], [])
            if pii_tags:
                sensitivity = FileSensitivity.FLAGGED.value
            rows.append(FileAccessLog(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                extraction_job_id=e["job"],
                source_type=e["source_type"],
                source_name=e["source_name"],
                path=e["path"],
                size_bytes=e["size"],
                content_hash=_hash(e["path"]),
                language=e["lang"],
                action=e["action"],
                sensitivity=sensitivity,
                pii_tags=pii_tags,
                agent="extractor",
                reason=e["reason"],
                accessed_at=_ago(e["ago"]),
            ))
        db.add_all(rows)
        db.commit()
        flagged = sum(1 for r in rows if r.sensitivity == FileSensitivity.FLAGGED.value)
        print(f"Seeded {len(rows)} file-access rows for tenant {tenant.slug} "
              f"({flagged} auto-flagged).")


if __name__ == "__main__":
    seed()
