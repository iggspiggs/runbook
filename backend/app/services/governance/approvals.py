"""
ApprovalService — create / query / decide on pending_changes.

Business rules:

  - maker ≠ checker: requested_by cannot approve their own change
  - a given approver votes at most once per pending_change
  - once status leaves PENDING the vote is closed
  - N approvals (from rule.risk_level) flip status to APPROVED and apply the
    change; any REJECT flips status to REJECTED
  - entries past expires_at auto-expire on list()
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit_log import AuditLog
from app.models.pending_change import (
    ApprovalDecision,
    PendingChange,
    PendingChangeApproval,
    PendingStatus,
)
from app.models.rule import Rule
from app.models.user import User

from .permissions import PermissionError_, can_approve, required_approvals_for


# SLA: pending changes expire after 7 days if not acted upon.
_DEFAULT_TTL_DAYS = 7


class ApprovalService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------ create

    async def create_pending_change(
        self,
        *,
        tenant_id: uuid.UUID,
        rule: Rule,
        changes: Dict[str, Any],
        requested_by: User,
        reason: Optional[str],
        ticket_ref: Optional[str],
    ) -> PendingChange:
        approvals_needed = required_approvals_for(rule.risk_level)
        expires_at = datetime.now(timezone.utc) + timedelta(days=_DEFAULT_TTL_DAYS)

        pc = PendingChange(
            tenant_id=tenant_id,
            rule_id=rule.id,
            rule_title=rule.title,
            rule_risk_level=rule.risk_level,
            changes=changes,
            reason=reason,
            ticket_ref=ticket_ref,
            status=PendingStatus.PENDING.value,
            approvals_required=approvals_needed,
            requested_by=requested_by.id,
            requested_by_email=requested_by.email,
            expires_at=expires_at,
        )
        self.db.add(pc)
        await self.db.commit()
        await self.db.refresh(pc)
        return pc

    # ------------------------------------------------------------ query

    async def list_pending(
        self,
        *,
        tenant_id: uuid.UUID,
        status: Optional[str] = None,
        rule_id: Optional[uuid.UUID] = None,
        requested_by: Optional[uuid.UUID] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[PendingChange]:
        # Auto-expire first
        await self._expire_stale(tenant_id)

        stmt = (
            select(PendingChange)
            .where(PendingChange.tenant_id == tenant_id)
            .options(selectinload(PendingChange.approvals))
            .order_by(PendingChange.requested_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status:
            stmt = stmt.where(PendingChange.status == status)
        if rule_id:
            stmt = stmt.where(PendingChange.rule_id == rule_id)
        if requested_by:
            stmt = stmt.where(PendingChange.requested_by == requested_by)

        return list((await self.db.execute(stmt)).scalars().all())

    async def get(self, pending_id: uuid.UUID, tenant_id: uuid.UUID) -> Optional[PendingChange]:
        stmt = (
            select(PendingChange)
            .where(
                PendingChange.id == pending_id,
                PendingChange.tenant_id == tenant_id,
            )
            .options(selectinload(PendingChange.approvals))
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    # ------------------------------------------------------------ decide

    async def decide(
        self,
        *,
        pending_id: uuid.UUID,
        tenant_id: uuid.UUID,
        approver: User,
        decision: str,
        note: Optional[str],
    ) -> PendingChange:
        if decision not in {ApprovalDecision.APPROVE.value, ApprovalDecision.REJECT.value}:
            raise ValueError(f"decision must be approve|reject, got {decision!r}")

        if not can_approve(approver.roles):
            raise PermissionError_("user does not have approver/admin role")

        pc = await self.get(pending_id, tenant_id)
        if pc is None:
            raise LookupError("pending change not found")
        if pc.status != PendingStatus.PENDING.value:
            raise ValueError(f"pending change is not pending (current: {pc.status})")

        # Maker ≠ checker
        if pc.requested_by == approver.id:
            raise PermissionError_("the requester cannot approve their own change")

        # One vote per approver
        for prior in pc.approvals or []:
            if prior.approver_id == approver.id:
                raise ValueError("approver has already voted on this change")

        pc.approvals.append(
            PendingChangeApproval(
                pending_change_id=pc.id,
                approver_id=approver.id,
                approver_email=approver.email,
                decision=decision,
                note=note,
            )
        )

        if decision == ApprovalDecision.REJECT.value:
            pc.status = PendingStatus.REJECTED.value
            pc.rejection_reason = note or "rejected by approver"
        else:
            approves = sum(
                1 for a in pc.approvals if a.decision == ApprovalDecision.APPROVE.value
            )
            if approves >= pc.approvals_required:
                # Apply the change
                await self._apply(pc, applied_by=approver)

        await self.db.commit()
        await self.db.refresh(pc)
        return pc

    # ------------------------------------------------------------ cancel

    async def cancel(
        self,
        *,
        pending_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user: User,
    ) -> PendingChange:
        pc = await self.get(pending_id, tenant_id)
        if pc is None:
            raise LookupError("pending change not found")
        if pc.status != PendingStatus.PENDING.value:
            raise ValueError(f"cannot cancel pending change in status {pc.status}")
        if pc.requested_by != user.id and "admin" not in user.roles:
            raise PermissionError_("only the requester or an admin can cancel")
        pc.status = PendingStatus.CANCELLED.value
        await self.db.commit()
        await self.db.refresh(pc)
        return pc

    # ------------------------------------------------------------ internals

    async def _apply(self, pc: PendingChange, applied_by: User) -> None:
        """
        Merge pc.changes into the target rule's editable_field_values and
        write one audit record per field.
        """
        rule = (
            await self.db.execute(select(Rule).where(Rule.id == pc.rule_id))
        ).scalar_one_or_none()
        if rule is None:
            raise LookupError("target rule not found")

        current = dict(rule.editable_field_values or {})
        for field_name, new_value in (pc.changes or {}).items():
            old_value = current.get(field_name)
            current[field_name] = new_value
            self.db.add(AuditLog(
                tenant_id=pc.tenant_id,
                rule_id=str(rule.rule_id) if rule.rule_id else str(rule.id),
                rule_title=rule.title,
                action="editable_update",
                changed_by=applied_by.email,
                field_name=field_name,
                old_value=json.dumps(old_value),
                new_value=json.dumps(new_value),
                reason=(
                    f"approved-change id={pc.id} reason={pc.reason or ''} "
                    f"ticket={pc.ticket_ref or ''}"
                ).strip(),
            ))
        rule.editable_field_values = current
        rule.last_changed = datetime.now(timezone.utc)
        rule.last_changed_by = applied_by.email

        pc.status = PendingStatus.APPLIED.value
        pc.applied_at = datetime.now(timezone.utc)
        pc.applied_by = applied_by.id

    async def _expire_stale(self, tenant_id: uuid.UUID) -> None:
        now = datetime.now(timezone.utc)
        stmt = select(PendingChange).where(
            PendingChange.tenant_id == tenant_id,
            PendingChange.status == PendingStatus.PENDING.value,
            PendingChange.expires_at.is_not(None),
            PendingChange.expires_at < now,
        )
        stale = list((await self.db.execute(stmt)).scalars().all())
        if not stale:
            return
        for pc in stale:
            pc.status = PendingStatus.EXPIRED.value
        await self.db.commit()
