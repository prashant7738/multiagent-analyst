"""Job status / polling routes.

SSE is the primary progress channel, but a plain polling endpoint is provided
as a fallback for clients that cannot use EventSource.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from api.models.schemas import JobStatus, JobSummary
from api.services.job_manager import JobManager, get_job_manager

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _to_summary(job) -> JobSummary:
    return JobSummary(
        job_id=job.job_id,
        status=JobStatus(job.status),
        filename=job.filename,
        progress=job.progress,
        created_at=job.created_at,
        updated_at=job.updated_at,
        error=job.error,
    )


@router.get("", response_model=list[JobSummary])
async def list_jobs(manager: JobManager = Depends(get_job_manager)) -> list[JobSummary]:
    """Return summaries of all known jobs (most recent first)."""
    jobs = sorted(manager.list_jobs(), key=lambda j: j.created_at, reverse=True)
    return [_to_summary(j) for j in jobs]


@router.get("/{job_id}", response_model=JobSummary)
async def get_job(job_id: str, manager: JobManager = Depends(get_job_manager)) -> JobSummary:
    """Return a single job's status snapshot."""
    job = manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown job_id: {job_id}")
    return _to_summary(job)
