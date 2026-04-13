"""
Simulation router — what-if impact analysis.

Before an operator commits a change to an editable field, they can POST
to /simulate with the proposed values. The engine walks the dependency
graph and returns:
  - directly_affected   — rules that directly read the changed rule's output
  - indirectly_affected — rules further downstream (up to max_depth hops)
  - aggregate_risk      — worst-case risk across all affected rules
  - warnings            — human-readable concerns (e.g. customer-facing rules,
                          cost-impact rules, rules pending verification)
"""
from __future__ import annotations

import uuid
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.registry.rule_service import RuleService
from app.services.simulator.engine import SimulationEngine

router = APIRouter(prefix="/api/simulate", tags=["simulation"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SimulationRequest(BaseModel):
    tenant_id: str
    rule_id: uuid.UUID = Field(..., description="The rule whose editable fields will change.")
    proposed_changes: Dict[str, Any] = Field(
        ...,
        description="Map of field_name → proposed_new_value. Same structure as the PATCH /editable body.",
        examples=[{"alert_threshold": 95, "retry_count": 5}],
    )

    model_config = {"json_schema_extra": {"examples": [
        {
            "tenant_id": "acme",
            "rule_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            "proposed_changes": {"alert_threshold": 95, "retry_count": 5},
        }
    ]}}


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------

def get_simulation_engine(db: AsyncSession = Depends(get_db)) -> SimulationEngine:
    service = RuleService(db)
    return SimulationEngine(rule_service=service)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("", summary="Run what-if impact simulation for a proposed rule change")
async def simulate_change(
    body: SimulationRequest,
    engine: SimulationEngine = Depends(get_simulation_engine),
) -> Dict[str, Any]:
    """
    Returns a full impact report without persisting any changes.

    The response is safe to display to an operator in a confirmation modal
    before they decide whether to proceed.
    """
    result = await engine.simulate_change(
        tenant_id=body.tenant_id,
        rule_id=body.rule_id,
        proposed_changes=body.proposed_changes,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found or does not belong to this tenant.",
        )
    return result.to_dict()
