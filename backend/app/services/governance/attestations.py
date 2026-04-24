"""
Attestation service — issue periodic "is this rule still correct?" records.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attestation import Attestation, AttestationStatus
from app.models.rule import Rule


class AttestationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def issue_campaign(
        self,
        *,
        tenant_id: uuid.UUID,
        period_label: str,
        due_in_days: int = 14,
        only_risk_levels: Optional[List[str]] = None,
    ) -> Tuple[int, int]:
        """
        Create one Attestation per qualifying rule for the given period.
        Idempotent: skips rules that already have an attestation for the period.
        Returns (created_count, skipped_count).
        """
        stmt = select(Rule).where(Rule.tenant_id == tenant_id)
        rules = list((await self.db.execute(stmt)).scalars().all())
        if only_risk_levels:
            rules = [r for r in rules if (r.risk_level or "").lower() in {x.lower() for x in only_risk_levels}]

        existing = {
            (a.rule_id, a.period_label)
            for a in (await self.db.execute(
                select(Attestation).where(
                    Attestation.tenant_id == tenant_id,
                    Attestation.period_label == period_label,
                )
            )).scalars().all()
        }

        due = datetime.now(timezone.utc) + timedelta(days=due_in_days)
        created = 0
        skipped = 0
        for rule in rules:
            if (rule.id, period_label) in existing:
                skipped += 1
                continue
            self.db.add(Attestation(
                tenant_id=tenant_id,
                rule_id=rule.id,
                rule_title=rule.title,
                period_label=period_label,
                owner_email=rule.owner,
                due_at=due,
                status=AttestationStatus.PENDING.value,
            ))
            created += 1

        if created:
            await self.db.commit()
        return created, skipped

    async def respond(
        self,
        *,
        tenant_id: uuid.UUID,
        attestation_id: uuid.UUID,
        responder_email: str,
        status: str,
        note: Optional[str] = None,
    ) -> Attestation:
        valid = {AttestationStatus.ATTESTED.value, AttestationStatus.CHANGES_NEEDED.value}
        if status not in valid:
            raise ValueError(f"status must be one of {sorted(valid)}")

        att = (await self.db.execute(
            select(Attestation).where(
                Attestation.id == attestation_id,
                Attestation.tenant_id == tenant_id,
            )
        )).scalar_one_or_none()
        if att is None:
            raise LookupError("attestation not found")
        if att.status not in (AttestationStatus.PENDING.value, AttestationStatus.OVERDUE.value):
            raise ValueError(f"attestation already {att.status}")

        att.status = status
        att.responded_by_email = responder_email
        att.responded_at = datetime.now(timezone.utc)
        att.response_note = note
        await self.db.commit()
        await self.db.refresh(att)
        return att

    async def mark_overdue(self, tenant_id: uuid.UUID) -> int:
        now = datetime.now(timezone.utc)
        stmt = select(Attestation).where(
            Attestation.tenant_id == tenant_id,
            Attestation.status == AttestationStatus.PENDING.value,
            Attestation.due_at < now,
        )
        stale = list((await self.db.execute(stmt)).scalars().all())
        for a in stale:
            a.status = AttestationStatus.OVERDUE.value
        if stale:
            await self.db.commit()
        return len(stale)
