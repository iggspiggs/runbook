"""
Extraction router — manage LLM-powered codebase scan jobs.

Flow:
  1. POST /extract        — kick off a new scan job (async)
  2. GET  /extract/{id}   — poll job status
  3. GET  /extract/{id}/results — preview extracted rules before committing
  4. POST /extract/{id}/commit  — persist rules into the registry
  5. GET  /extract/history      — audit trail of past jobs
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.registry.rule_service import RuleService
from app.services.extractor.scanner import CodebaseScanner
from app.services.extractor.analyzer import RuleAnalyzer
from app.config import settings

import anthropic

router = APIRouter(prefix="/api/extract", tags=["extraction"])


# ---------------------------------------------------------------------------
# In-memory job store (replace with a proper task queue / DB table in prod)
# ---------------------------------------------------------------------------

_jobs: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ExtractionRequest(BaseModel):
    tenant_id: str
    repo_url: Optional[str] = Field(
        None,
        description="Remote git repo URL. Cloned to a temp directory.",
        examples=["https://github.com/acme/backend.git"],
    )
    local_path: Optional[str] = Field(
        None,
        description="Absolute path on the server filesystem.",
        examples=["/srv/repos/acme-backend"],
    )
    branch: str = Field("main", description="Branch to check out when cloning.")
    initiated_by: str = Field(..., description="User who triggered the scan.")

    model_config = {"json_schema_extra": {"examples": [
        {
            "tenant_id": "acme",
            "repo_url": "https://github.com/acme/backend.git",
            "branch": "main",
            "initiated_by": "alice@acme.com",
        }
    ]}}


class CommitRequest(BaseModel):
    tenant_id: str
    committed_by: str
    rule_ids: Optional[List[str]] = Field(
        None,
        description="Subset of extracted rule IDs to commit. Omit to commit all.",
    )


# ---------------------------------------------------------------------------
# Background task: run full scan + analysis
# ---------------------------------------------------------------------------

async def _run_extraction(job_id: str, req: ExtractionRequest) -> None:
    job = _jobs[job_id]
    try:
        job["status"] = "scanning"

        repo_path = req.local_path
        if repo_path is None and req.repo_url:
            import tempfile
            import subprocess
            tmp = tempfile.mkdtemp(prefix="runbook_scan_")
            subprocess.run(
                ["git", "clone", "--depth", "1", "--branch", req.branch, req.repo_url, tmp],
                check=True,
                capture_output=True,
                text=True,
            )
            repo_path = tmp
            job["cloned_to"] = tmp

        if not repo_path:
            raise ValueError("Either repo_url or local_path must be provided.")

        scanner = CodebaseScanner(repo_path=repo_path, branch=req.branch)
        chunks = scanner.scan()
        job["chunks_found"] = len(chunks)
        job["status"] = "analyzing"

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        analyzer = RuleAnalyzer(anthropic_client=client)
        extracted_rules = await analyzer.analyze_batch(chunks)

        job["status"] = "complete"
        # Use to_dict() so editable_fields items are serialised as plain dicts
        # and all keys match the model column names expected by upsert_from_extraction.
        job["results"] = [r.to_dict() for r in extracted_rules]
        job["rule_count"] = len(extracted_rules)

    except Exception as exc:
        job["status"] = "failed"
        job["error"] = str(exc)
        raise


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", status_code=status.HTTP_202_ACCEPTED, summary="Start a new extraction job")
async def start_extraction(
    req: ExtractionRequest,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    if not req.repo_url and not req.local_path:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide either repo_url or local_path.",
        )

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "job_id": job_id,
        "tenant_id": req.tenant_id,
        "status": "queued",
        "initiated_by": req.initiated_by,
        "branch": req.branch,
        "repo_url": req.repo_url,
        "local_path": req.local_path,
        "chunks_found": None,
        "rule_count": None,
        "results": None,
        "error": None,
    }

    background_tasks.add_task(_run_extraction, job_id, req)
    return {"job_id": job_id, "status": "queued"}


@router.get("/history", summary="List past extraction jobs")
async def list_history(
    tenant_id: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    tenant_jobs = [
        {k: v for k, v in job.items() if k != "results"}
        for job in _jobs.values()
        if job.get("tenant_id") == tenant_id
    ]
    tenant_jobs.sort(key=lambda j: j.get("job_id", ""), reverse=True)
    return {
        "total": len(tenant_jobs),
        "items": tenant_jobs[:limit],
    }


@router.get("/{job_id}", summary="Get job status")
async def get_job_status(job_id: str) -> Dict[str, Any]:
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    # Return everything except the full results payload (use /results for that)
    return {k: v for k, v in job.items() if k != "results"}


@router.get("/{job_id}/results", summary="Preview extracted rules before committing")
async def get_job_results(job_id: str) -> Dict[str, Any]:
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job["status"] != "complete":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is not complete (current status: {job['status']}). Results are not available yet.",
        )
    return {
        "job_id": job_id,
        "rule_count": job["rule_count"],
        "results": job.get("results", []),
    }


@router.post("/{job_id}/commit", summary="Commit extracted rules into the registry")
async def commit_job(
    job_id: str,
    body: CommitRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job["status"] != "complete":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot commit job with status '{job['status']}'.",
        )
    if job["tenant_id"] != body.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="tenant_id does not match this job.",
        )

    results = job.get("results") or []
    if body.rule_ids is not None:
        results = [r for r in results if r.get("rule_id") in body.rule_ids]

    service = RuleService(db)
    committed, skipped = await service.upsert_from_extraction(
        tenant_id=body.tenant_id,
        extracted_rules=results,
        committed_by=body.committed_by,
    )

    job["committed"] = True
    return {
        "job_id": job_id,
        "committed": committed,
        "skipped": skipped,
    }
