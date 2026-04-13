"""
RuleService — the single authoritative interface for all rule data operations.

All callers (routers, drift detector, simulation engine) go through this
class rather than issuing SQLAlchemy queries directly. This keeps query
logic in one place and makes the service straightforward to test with a
mock DB session.

Models live in app/models/. All model imports are deferred inside each
method to avoid circular import issues at module load time.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, asc, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Value type registry for editable-field validation
# ---------------------------------------------------------------------------

_TYPE_COERCERS: Dict[str, Any] = {
    "str":        str,
    "int":        int,
    "float":      float,
    "bool":       lambda v: v if isinstance(v, bool) else str(v).lower() in ("true", "1", "yes"),
    "list":       lambda v: v if isinstance(v, list) else json.loads(v),
    "email_list": lambda v: _validate_email_list(v),
}


def _validate_email_list(value: Any) -> List[str]:
    import re
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, list):
        raise ValueError("email_list must be a JSON array of strings")
    email_pattern = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    for addr in value:
        if not email_pattern.match(addr):
            raise ValueError(f"Invalid email address: {addr!r}")
    return value


# ---------------------------------------------------------------------------
# RuleService
# ---------------------------------------------------------------------------

class RuleService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get_rules(
        self, filters: Dict[str, Any]
    ) -> Tuple[List[Any], int]:
        """
        Dynamically-filtered rule query. Returns (items, total_count).
        Caller is responsible for pagination via limit/offset in filters.

        Filter keys understood:
          tenant_id (required), department, status, search (ILIKE on title+desc),
          risk_level, verified (bool), tags (list of strings), limit, offset.
        """
        from app.models.rule import Rule as RuleModel  # deferred import

        tenant_id = filters["tenant_id"]
        conditions = [RuleModel.tenant_id == tenant_id]

        if filters.get("department"):
            conditions.append(RuleModel.department == filters["department"])
        if filters.get("status"):
            conditions.append(RuleModel.status == filters["status"])
        if filters.get("risk_level"):
            conditions.append(RuleModel.risk_level == filters["risk_level"])
        if filters.get("verified") is not None:
            conditions.append(RuleModel.verified == filters["verified"])
        if filters.get("search"):
            term = f"%{filters['search']}%"
            conditions.append(
                or_(
                    RuleModel.title.ilike(term),
                    RuleModel.description.ilike(term),
                )
            )
        if filters.get("tags"):
            # Postgres JSONB array containment: rule.tags @> '["tag1"]'::jsonb
            for tag in filters["tags"]:
                conditions.append(RuleModel.tags.contains([tag]))

        where_clause = and_(*conditions)
        limit = filters.get("limit", 50)
        offset = filters.get("offset", 0)

        count_stmt = select(func.count()).select_from(RuleModel).where(where_clause)
        total: int = (await self._db.execute(count_stmt)).scalar_one()

        stmt = (
            select(RuleModel)
            .where(where_clause)
            .order_by(asc(RuleModel.title))
            .limit(limit)
            .offset(offset)
        )
        result = await self._db.execute(stmt)
        items = list(result.scalars().all())
        return items, total

    async def get_rule(
        self, tenant_id: str, rule_id: str
    ) -> Optional[Any]:
        from app.models.rule import Rule as RuleModel

        stmt = select(RuleModel).where(
            and_(RuleModel.tenant_id == tenant_id, RuleModel.rule_id == rule_id)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_rule_audit(
        self,
        tenant_id: str,
        rule_id: uuid.UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Any], int]:
        from app.models.audit_log import AuditLog as AuditLogModel

        conditions = [
            AuditLogModel.tenant_id == tenant_id,
            AuditLogModel.rule_id == rule_id,
        ]
        where_clause = and_(*conditions)

        count_stmt = select(func.count()).select_from(AuditLogModel).where(where_clause)
        total: int = (await self._db.execute(count_stmt)).scalar_one()

        stmt = (
            select(AuditLogModel)
            .where(where_clause)
            .order_by(desc(AuditLogModel.created_at))
            .limit(limit)
            .offset(offset)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    async def get_audit_logs(
        self, filters: Dict[str, Any]
    ) -> Tuple[List[Any], int]:
        from app.models.audit_log import AuditLog as AuditLogModel

        tenant_id = filters["tenant_id"]
        conditions = [AuditLogModel.tenant_id == tenant_id]

        if filters.get("rule_id"):
            conditions.append(AuditLogModel.rule_id == uuid.UUID(str(filters["rule_id"])))
        if filters.get("action"):
            conditions.append(AuditLogModel.action == filters["action"])
        if filters.get("changed_by"):
            conditions.append(AuditLogModel.changed_by == filters["changed_by"])
        if filters.get("date_from"):
            conditions.append(AuditLogModel.created_at >= filters["date_from"])
        if filters.get("date_to"):
            conditions.append(AuditLogModel.created_at <= filters["date_to"])

        where_clause = and_(*conditions)
        limit = filters.get("limit", 100)
        offset = filters.get("offset", 0)

        count_stmt = select(func.count()).select_from(AuditLogModel).where(where_clause)
        total: int = (await self._db.execute(count_stmt)).scalar_one()

        stmt = (
            select(AuditLogModel)
            .where(where_clause)
            .order_by(desc(AuditLogModel.created_at))
            .limit(limit)
            .offset(offset)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    async def get_dependency_graph(self, tenant_id: str) -> Dict[str, Any]:
        """
        Build a graph payload suitable for React Flow / DAG rendering.

        Returns:
          {
            "nodes": [{"id": str, "data": {...rule summary...}}, ...],
            "edges": [{"id": str, "source": str, "target": str}, ...]
          }
        """
        from app.models.rule import Rule as RuleModel

        stmt = select(RuleModel).where(RuleModel.tenant_id == tenant_id)
        result = await self._db.execute(stmt)
        rules = list(result.scalars().all())

        nodes = []
        edges = []

        for rule in rules:
            # rule.rule_id is the string business identifier used in
            # upstream_rule_ids / downstream_rule_ids arrays.
            node_id = rule.rule_id
            nodes.append({
                "id": node_id,
                "data": {
                    "rule_id": node_id,
                    "db_id": str(rule.id),
                    "title": rule.title,
                    "status": rule.status,
                    "risk_level": rule.risk_level,
                    "verified": rule.verified,
                    "customer_facing": rule.customer_facing,
                    "department": rule.department,
                },
            })
            # upstream edges: upstream_rule_ids contains string rule_id values
            for upstream_rid in (rule.upstream_rule_ids or []):
                edges.append({
                    "id": f"{upstream_rid}->{node_id}",
                    "source": upstream_rid,
                    "target": node_id,
                })

        return {"nodes": nodes, "edges": edges}

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    async def update_editable(
        self,
        tenant_id: str,
        rule_id: uuid.UUID,
        field_updates: Dict[str, Any],
        changed_by: str,
        reason: Optional[str] = None,
    ) -> Optional[Any]:
        """
        Validate each field_update against the declared editable_fields on the
        rule model, coerce to the correct type, persist the update, and write
        one AuditLog record per changed field.

        Raises ValueError with a descriptive message if:
          - A field name is not in the rule's editable_fields list
          - A value fails type coercion or range validation
        """
        from app.models.rule import Rule as RuleModel
        from app.models.audit_log import AuditLog as AuditLogModel

        rule = await self.get_rule(tenant_id, rule_id)
        if rule is None:
            return None

        editable_map: Dict[str, Any] = {
            ef["field_name"]: ef for ef in (rule.editable_fields or [])
        }

        validated_updates: Dict[str, Any] = {}
        audit_records: List[Dict[str, Any]] = []

        for field_name, new_value in field_updates.items():
            if field_name not in editable_map:
                raise ValueError(
                    f"Field '{field_name}' is not declared as editable on rule '{rule.title}'. "
                    f"Editable fields: {list(editable_map.keys())}"
                )

            field_def = editable_map[field_name]
            field_type = field_def.get("field_type", "str")

            coercer = _TYPE_COERCERS.get(field_type)
            if coercer is None:
                raise ValueError(f"Unknown field type '{field_type}' for field '{field_name}'")

            try:
                coerced_value = coercer(new_value)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"Invalid value for field '{field_name}' (expected {field_type}): {exc}"
                )

            # Range validation for numeric types
            if field_type in ("int", "float"):
                if field_def.get("min_value") is not None and coerced_value < field_def["min_value"]:
                    raise ValueError(
                        f"Field '{field_name}' value {coerced_value} is below minimum {field_def['min_value']}"
                    )
                if field_def.get("max_value") is not None and coerced_value > field_def["max_value"]:
                    raise ValueError(
                        f"Field '{field_name}' value {coerced_value} exceeds maximum {field_def['max_value']}"
                    )

            # Allowed values check
            if field_def.get("allowed_values") and coerced_value not in field_def["allowed_values"]:
                raise ValueError(
                    f"Value {coerced_value!r} is not in allowed_values for '{field_name}': "
                    f"{field_def['allowed_values']}"
                )

            old_value = (rule.editable_field_values or {}).get(field_name)
            validated_updates[field_name] = coerced_value

            audit_records.append({
                "tenant_id": tenant_id,
                "rule_id": rule_id,
                "action": "editable_update",
                "changed_by": changed_by,
                "field_name": field_name,
                "old_value": json.dumps(old_value),
                "new_value": json.dumps(coerced_value),
                "reason": reason,
            })

        # Merge updates into the rule's JSONB editable_field_values column
        current_values = dict(rule.editable_field_values or {})
        current_values.update(validated_updates)

        stmt = (
            update(RuleModel)
            .where(and_(RuleModel.tenant_id == tenant_id, RuleModel.rule_id == rule_id))
            .values(editable_field_values=current_values)
            .returning(RuleModel)
        )
        result = await self._db.execute(stmt)
        updated_rule = result.scalar_one()

        for ar in audit_records:
            self._db.add(AuditLogModel(**ar))

        await self._db.commit()
        await self._db.refresh(updated_rule)
        return updated_rule

    async def set_verified(
        self,
        tenant_id: str,
        rule_id: uuid.UUID,
        verified_by: str,
        notes: Optional[str] = None,
    ) -> Optional[Any]:
        from app.models.rule import Rule as RuleModel
        from app.models.audit_log import AuditLog as AuditLogModel

        rule = await self.get_rule(tenant_id, rule_id)
        if rule is None:
            return None

        stmt = (
            update(RuleModel)
            .where(and_(RuleModel.tenant_id == tenant_id, RuleModel.rule_id == rule_id))
            .values(verified=True, verified_by=verified_by, verified_at=datetime.utcnow())
            .returning(RuleModel)
        )
        result = await self._db.execute(stmt)
        updated_rule = result.scalar_one()

        self._db.add(AuditLogModel(
            tenant_id=tenant_id,
            rule_id=rule_id,
            action="verify",
            changed_by=verified_by,
            field_name=None,
            old_value=json.dumps(False),
            new_value=json.dumps(True),
            reason=notes,
        ))
        await self._db.commit()
        await self._db.refresh(updated_rule)
        return updated_rule

    async def update_status(
        self,
        tenant_id: str,
        rule_id: uuid.UUID,
        new_status: str,
        changed_by: str,
        reason: Optional[str] = None,
    ) -> Optional[Any]:
        from app.models.rule import Rule as RuleModel
        from app.models.audit_log import AuditLog as AuditLogModel

        valid_statuses = {"active", "paused", "draft"}
        if new_status not in valid_statuses:
            raise ValueError(f"Invalid status '{new_status}'. Must be one of: {valid_statuses}")

        rule = await self.get_rule(tenant_id, rule_id)
        if rule is None:
            return None

        old_status = rule.status
        stmt = (
            update(RuleModel)
            .where(and_(RuleModel.tenant_id == tenant_id, RuleModel.rule_id == rule_id))
            .values(status=new_status)
            .returning(RuleModel)
        )
        result = await self._db.execute(stmt)
        updated_rule = result.scalar_one()

        self._db.add(AuditLogModel(
            tenant_id=tenant_id,
            rule_id=rule_id,
            action="status_change",
            changed_by=changed_by,
            field_name="status",
            old_value=json.dumps(old_status),
            new_value=json.dumps(new_status),
            reason=reason,
        ))
        await self._db.commit()
        await self._db.refresh(updated_rule)
        return updated_rule

    async def upsert_from_extraction(
        self,
        tenant_id: str,
        extracted_rules: List[Dict[str, Any]],
        committed_by: str,
    ) -> Tuple[int, int]:
        """
        Idempotent upsert of extracted rules into the registry.

        Strategy:
          - Match on (tenant_id, rule_id) — rule_id is the stable string business
            key emitted by the extractor (e.g. "send-low-balance-alert").
          - If a rule exists: update extraction-sourced fields ONLY if there are
            no pending admin edits (editable_field_values is empty / unchanged).
            This preserves operator overrides across re-scans.
          - If a rule does not exist: insert it with status='draft'.

        The extracted_rules dicts use the model column names directly:
          rule_id, source_file, source_lines ({"start": N, "end": N}),
          upstream_rule_ids, downstream_rule_ids, editable_fields, etc.

        Returns (committed_count, skipped_count).
        """
        from app.models.rule import Rule as RuleModel
        from app.models.audit_log import AuditLog as AuditLogModel

        committed = 0
        skipped = 0

        for rule_data in extracted_rules:
            business_rule_id = rule_data.get("rule_id", "")
            source_lines = rule_data.get("source_lines", {})
            source_file = rule_data.get("source_file", "")

            stmt = select(RuleModel).where(
                and_(
                    RuleModel.tenant_id == tenant_id,
                    RuleModel.rule_id == business_rule_id,
                )
            )
            result = await self._db.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing is not None:
                # Only update if operator hasn't made manual edits
                has_admin_edits = bool(existing.editable_field_values)
                if has_admin_edits:
                    skipped += 1
                    continue
                # Update extraction-derived fields; preserve editable_field_values
                for col in (
                    "title", "description", "trigger", "conditions",
                    "actions", "editable_fields", "risk_level",
                    "customer_facing", "cost_impact", "upstream_rule_ids",
                    "downstream_rule_ids", "tags", "language",
                    "source_file", "source_content", "source_lines",
                ):
                    if col in rule_data:
                        setattr(existing, col, rule_data[col])
                self._db.add(AuditLogModel(
                    tenant_id=tenant_id,
                    rule_id=existing.id,
                    action="extraction_update",
                    changed_by=committed_by,
                    reason="Re-scan committed updated extraction data",
                ))
            else:
                new_rule = RuleModel(
                    tenant_id=tenant_id,
                    rule_id=business_rule_id or str(uuid.uuid4()),
                    slug=rule_data.get("slug"),
                    title=rule_data.get("title", "Untitled Rule"),
                    description=rule_data.get("description", ""),
                    trigger=rule_data.get("trigger", ""),
                    conditions=rule_data.get("conditions", []),
                    actions=rule_data.get("actions", []),
                    editable_fields=rule_data.get("editable_fields", []),
                    editable_field_values={},
                    risk_level=rule_data.get("risk_level", "medium"),
                    customer_facing=rule_data.get("customer_facing", False),
                    cost_impact=rule_data.get("cost_impact", False),
                    source_file=source_file,
                    source_content=rule_data.get("source_content", ""),
                    source_lines=source_lines,
                    language=rule_data.get("language", ""),
                    upstream_rule_ids=rule_data.get("upstream_rule_ids", []),
                    downstream_rule_ids=rule_data.get("downstream_rule_ids", []),
                    tags=rule_data.get("tags", []),
                    status="draft",
                    verified=False,
                )
                self._db.add(new_rule)
                self._db.add(AuditLogModel(
                    tenant_id=tenant_id,
                    rule_id=new_rule.id,
                    action="extraction_create",
                    changed_by=committed_by,
                    reason="Initial extraction commit",
                ))

            committed += 1

        await self._db.commit()
        return committed, skipped
