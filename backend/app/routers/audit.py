"""
Audit router — query and export the system-wide audit log.

All mutations to rules (editable field changes, status changes,
verifications) produce audit records. This router exposes those
records for compliance review and export.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.registry.rule_service import RuleService

router = APIRouter(prefix="/api/audit", tags=["audit"])


def get_rule_service(db: AsyncSession = Depends(get_db)) -> RuleService:
    return RuleService(db)


@router.get("", summary="List audit log entries")
async def list_audit_logs(
    tenant_id: str = Query(...),
    rule_id: Optional[str] = Query(None, description="Filter to a single rule UUID"),
    action: Optional[str] = Query(
        None,
        description="Action type filter, e.g. editable_update, status_change, verify",
    ),
    changed_by: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None, description="ISO-8601 inclusive start"),
    date_to: Optional[datetime] = Query(None, description="ISO-8601 inclusive end"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    service: RuleService = Depends(get_rule_service),
) -> Dict[str, Any]:
    filters = {
        "tenant_id": tenant_id,
        "rule_id": rule_id,
        "action": action,
        "changed_by": changed_by,
        "date_from": date_from,
        "date_to": date_to,
        "limit": limit,
        "offset": offset,
    }
    entries, total = await service.get_audit_logs(filters)
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [e.to_dict() for e in entries],
    }


@router.get("/export", summary="Export audit logs as CSV")
async def export_audit_logs(
    tenant_id: str = Query(...),
    rule_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    changed_by: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    service: RuleService = Depends(get_rule_service),
) -> StreamingResponse:
    """
    Streams a CSV file. No pagination — returns the full result set for the
    applied filters. Use date range filters to keep file sizes manageable.
    """
    filters = {
        "tenant_id": tenant_id,
        "rule_id": rule_id,
        "action": action,
        "changed_by": changed_by,
        "date_from": date_from,
        "date_to": date_to,
        "limit": 100_000,  # safety ceiling
        "offset": 0,
    }
    entries, _ = await service.get_audit_logs(filters)

    def _generate_csv():
        output = io.StringIO()
        fieldnames = [
            "id",
            "tenant_id",
            "rule_id",
            "rule_title",
            "action",
            "changed_by",
            "field_name",
            "old_value",
            "new_value",
            "reason",
            "timestamp",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        output.seek(0)
        yield output.read()
        output.truncate(0)
        output.seek(0)

        for entry in entries:
            row = entry.to_dict()
            writer.writerow(row)
            output.seek(0)
            yield output.read()
            output.truncate(0)
            output.seek(0)

    filename = f"runbook_audit_{tenant_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        _generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
