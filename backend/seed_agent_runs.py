"""
seed_agent_runs.py — populate AgentRun history for the Agent Logs demo page.

Creates ~45 synthetic runs across 3 extractor jobs + 5 drift_detector runs.
Idempotent: removes rows with synthetic job IDs first.

Run from backend/:
    py -3.13 seed_agent_runs.py
"""
from __future__ import annotations

import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import delete, select

from app.db import SyncSessionLocal, create_tables_sync
from app.models.agent_run import AgentRun, AgentStatus
from app.models.tenant import Tenant


DEMO_TENANT_SLUG = "acme-logistics"
SYNTHETIC_JOBS = [
    "seed-job-acme-backend-001",
    "seed-job-acme-billing-002",
    "seed-job-dms-policies-003",
    "seed-drift-001",
]

_FILES = {
    "seed-job-acme-backend-001": [
        "app/jobs/billing_cycle.py",
        "app/jobs/retry_policy.py",
        "app/config/schedules.yaml",
        "app/services/notify.py",
        "app/routers/webhooks.py",
        "scripts/ops/deploy.sh",
        ".env.production",
    ],
    "seed-job-acme-billing-002": [
        "src/engine/dunning.py",
        "src/engine/late_fee.py",
        "config/feature_flags.toml",
        "src/approval/manager_approval.py",
    ],
    "seed-job-dms-policies-003": [
        "Policies/SLA_matrix.yaml",
        "Policies/escalation_tree.json",
        "Archive/2024/backup_db_jan.sql",
        "nightly/runbook_rules_2024-10-15.json",
    ],
}

_DRIFT_RULES = [
    "Auto-Approve Low-Value Verified Orders",
    "Credit Hold on Overdue Balance",
    "Stale Shipment Escalation",
    "Backorder Customer Notification",
    "Shipping Label Generation",
]


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

        # idempotent: delete prior seeded rows
        db.execute(delete(AgentRun).where(
            AgentRun.tenant_id == tenant.id,
            AgentRun.job_id.in_(SYNTHETIC_JOBS),
        ))
        db.commit()

        created = 0
        # ----- 3 extractor jobs
        for job_ago_hours, job_id in [(1, SYNTHETIC_JOBS[0]), (28, SYNTHETIC_JOBS[1]), (48, SYNTHETIC_JOBS[2])]:
            base = now - timedelta(hours=job_ago_hours)
            files = _FILES[job_id]
            for i, fp in enumerate(files):
                started = base + timedelta(seconds=i * 6)
                duration_ms = random.randint(1800, 4200)
                # Make ~1 in 8 fail
                failed = (i == len(files) - 1) and (job_ago_hours == 48)
                in_tok = random.randint(1800, 4500)
                out_tok = random.randint(450, 1200)
                db.add(AgentRun(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    agent_name="extractor",
                    agent_version="v1",
                    job_id=job_id,
                    step_index=i,
                    step_label=fp,
                    status=(AgentStatus.FAILED.value if failed else AgentStatus.COMPLETED.value),
                    model="claude-opus-4-5",
                    input_summary=(
                        f"Analyze the following code snippet and extract any automation rule.\n\n"
                        f"File: {fp}\nPatterns detected: threshold_pattern, retry_pattern\n\n"
                        f"```python\n# (truncated ~{random.randint(600, 2000)} chars of source)\n```"
                    ),
                    output_summary=(
                        "rate limit: 429 from Anthropic — retry exhausted"
                        if failed
                        else (
                            '{"rule_id":"BILL.CYCLE","title":"Monthly billing cycle kick-off",'
                            '"trigger":"cron: 0 3 1 * *","risk_level":"high","editable_fields":['
                            '{"field_name":"cycle_day","field_type":"int","current":1,"description":"Day of month to run"}]}'
                        )
                    ),
                    input_tokens=in_tok,
                    output_tokens=(0 if failed else out_tok),
                    duration_ms=duration_ms,
                    error=("HTTP 429: rate_limit_error" if failed else None),
                    started_at=started,
                    finished_at=started + timedelta(milliseconds=duration_ms),
                ))
                created += 1

        # ----- drift detector (5 runs across rules)
        job_id = SYNTHETIC_JOBS[3]
        base = now - timedelta(hours=6)
        for i, rule_title in enumerate(_DRIFT_RULES):
            started = base + timedelta(minutes=i * 3)
            duration_ms = random.randint(900, 1800)
            drifted = (i in (1, 3))
            in_tok = random.randint(900, 1800)
            out_tok = random.randint(200, 500)
            db.add(AgentRun(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                agent_name="drift_detector",
                agent_version="v0.2",
                job_id=job_id,
                step_index=i,
                step_label=rule_title,
                status=AgentStatus.COMPLETED.value,
                model="claude-haiku-4-5",
                input_summary=(
                    f"Compare the current registry entry for '{rule_title}' against the extracted "
                    "structure from the latest codebase scan. Report any drift in trigger, "
                    "conditions, actions, or editable_fields."
                ),
                output_summary=(
                    '{"drift":true,"changes":["threshold_usd default increased 500→750","new field `escalate_to` detected"]}'
                    if drifted
                    else '{"drift":false,"changes":[]}'
                ),
                input_tokens=in_tok,
                output_tokens=out_tok,
                duration_ms=duration_ms,
                error=None,
                started_at=started,
                finished_at=started + timedelta(milliseconds=duration_ms),
            ))
            created += 1

        db.commit()
        print(f"Seeded {created} agent runs across {len(SYNTHETIC_JOBS)} synthetic jobs.")


if __name__ == "__main__":
    seed()
