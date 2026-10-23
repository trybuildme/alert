"""Scanner API endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.scanner.engine import scan_engine, JobStatus
from app.scanner.registry import MODULE_REGISTRY, get_module_info, list_modules
from app.scanner.graphql import GraphQLScanner

router = APIRouter(prefix="/api/scanner", tags=["scanner"])

# Register modules on import
scan_engine.register_module(GraphQLScanner())


class ScanRequest(BaseModel):
    """Request to start a scan."""
    target: str
    modules: Optional[List[str]] = None
    config: Optional[Dict[str, Any]] = None
    profile: Optional[str] = None


class ModuleResponse(BaseModel):
    """Module info response."""
    name: str
    display_name: str
    description: str
    enabled: bool
    category: str


class ModulesResponse(BaseModel):
    """List of modules response."""
    modules: List[ModuleResponse]


class JobResponse(BaseModel):
    """Scan job response."""
    id: str
    target: str
    modules: List[str]
    status: str
    progress: float
    created_at: float
    started_at: Optional[float]
    completed_at: Optional[float]
    finding_count: Dict[str, int]
    error: Optional[str]


class FindingResponse(BaseModel):
    """Finding response."""
    title: str
    severity: str
    description: str
    evidence: Optional[str]
    remediation: Optional[str]
    references: List[str]
    metadata: Dict[str, Any]


class ScanResultResponse(BaseModel):
    """Scan result response."""
    module: str
    target: str
    started_at: float
    completed_at: Optional[float]
    findings: List[FindingResponse]
    error: Optional[str]
    metadata: Dict[str, Any]


@router.get("/modules", response_model=ModulesResponse)
async def get_modules():
    """List available scan modules."""
    modules = list_modules()
    return ModulesResponse(
        modules=[
            ModuleResponse(
                name=m.name,
                display_name=m.display_name,
                description=m.description,
                enabled=m.enabled,
                category=m.category
            )
            for m in modules
        ]
    )


@router.post("/scan", response_model=JobResponse)
async def start_scan(request: ScanRequest):
    """Start a new scan job."""
    try:
        job = await scan_engine.submit_job(
            target=request.target,
            modules=request.modules,
            config=request.config
        )
        return JobResponse(
            id=job.id,
            target=job.target,
            modules=job.modules,
            status=job.status.value,
            progress=job.progress,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            finding_count=job.finding_count,
            error=job.error
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    """Get scan job status."""
    job = scan_engine.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(
        id=job.id,
        target=job.target,
        modules=job.modules,
        status=job.status.value,
        progress=job.progress,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        finding_count=job.finding_count,
        error=job.error
    )


@router.get("/jobs/{job_id}/results", response_model=List[ScanResultResponse])
async def get_job_results(job_id: str):
    """Get scan job results."""
    job = scan_engine.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return [
        ScanResultResponse(
            module=r.module,
            target=r.target,
            started_at=r.started_at,
            completed_at=r.completed_at,
            findings=[
                FindingResponse(
                    title=f.title,
                    severity=f.severity.value,
                    description=f.description,
                    evidence=f.evidence,
                    remediation=f.remediation,
                    references=f.references,
                    metadata=f.metadata
                )
                for f in r.findings
            ],
            error=r.error,
            metadata=r.metadata
        )
        for r in job.results
    ]


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    """Cancel a running scan job."""
    success = await scan_engine.cancel_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found or not running")
    return {"status": "cancelled"}


@router.get("/jobs", response_model=List[JobResponse])
async def list_jobs(
    status: Optional[str] = None,
    limit: int = 100
):
    """List scan jobs."""
    job_status = JobStatus(status) if status else None
    jobs = scan_engine.list_jobs(status=job_status, limit=limit)
    return [
        JobResponse(
            id=job.id,
            target=job.target,
            modules=job.modules,
            status=job.status.value,
            progress=job.progress,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            finding_count=job.finding_count,
            error=job.error
        )
        for job in jobs
    ]
