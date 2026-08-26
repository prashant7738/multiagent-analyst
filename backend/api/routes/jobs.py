"""Job status / polling routes.

SSE is the primary progress channel, but a plain polling endpoint is provided
as a fallback for clients that cannot use EventSource.
"""

from __future__ import annotations

import logging
import shutil

from fastapi import APIRouter, Depends, HTTPException, status

from api.config import Settings, get_settings
from api.models.schemas import AuthUser, JobStatus, JobSummary
from api.routes.auth import get_current_user
from api.services.job_manager import Job, JobManager, get_job_manager
from api.utils.response import success

logger = logging.getLogger("api.jobs")

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _to_summary(job) -> JobSummary:
    return JobSummary(
        job_id=job.job_id,
        status=JobStatus(job.status),
        filename=job.filename,
        analysis_config=job.analysis_config,
        progress=job.progress,
        created_at=job.created_at,
        updated_at=job.updated_at,
        error=job.error,
        rag_status=job.rag_status,
        rag_error=job.rag_error,
        rag_sample_info=job.rag_sample_info,
        rag_progress=job.rag_progress,
    )


def _require_owned_job(manager: JobManager, job_id: str, user: AuthUser) -> Job:
    """Fetch a job and verify ``user`` owns it. 404s on both missing and not-owned

    (never distinguishes the two — that would leak whether a given job_id exists
    for someone else).
    """
    job = manager.get_job(job_id)
    if job is None or job.user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown job_id: {job_id}")
    return job


@router.get("", response_model=list[JobSummary])
async def list_jobs(
    manager: JobManager = Depends(get_job_manager),
    user: AuthUser = Depends(get_current_user),
) -> list[JobSummary]:
    """Return summaries of the caller's own jobs (most recent first)."""
    jobs = sorted(manager.list_jobs(user_id=user.user_id), key=lambda j: j.created_at, reverse=True)
    return [_to_summary(j) for j in jobs]


@router.get("/{job_id}", response_model=JobSummary)
async def get_job(
    job_id: str,
    manager: JobManager = Depends(get_job_manager),
    user: AuthUser = Depends(get_current_user),
) -> JobSummary:
    """Return a single job's status snapshot."""
    job = _require_owned_job(manager, job_id, user)
    return _to_summary(job)


def _delete_artifacts(job: Job, settings: Settings) -> None:
    """Best-effort removal of every on-disk artifact belonging to a job.

    Covers the uploaded CSV (``uploads/{job_id}.csv``), per-job chart/report
    folders (``outputs/charts/<job_id>/``, ``outputs/reports/<job_id>/``) and
    the flat chat charts named ``chat_<job_id[:8]>_*.png``.
    """
    upload = settings.uploads_dir / f"{job.job_id}.csv"
    upload.unlink(missing_ok=True)

    for directory in (settings.charts_dir / job.job_id, settings.reports_dir / job.job_id):
        shutil.rmtree(directory, ignore_errors=True)

    prefix = f"chat_{job.job_id[:8]}_"
    for chat_chart in settings.charts_dir.glob(f"{prefix}*.png"):
        chat_chart.unlink(missing_ok=True)


def _purge_job(job: Job, settings: Settings, manager: JobManager) -> None:
    """Remove one job's artifacts, RAG embeddings, and stored record."""
    _delete_artifacts(job, settings)

    try:
        from api.services.rag_service import delete_job_documents

        delete_job_documents(job.job_id)
    except Exception:  # noqa: BLE001 — embeddings live only when Postgres is configured
        logger.debug("RAG cleanup skipped for job %s", job.job_id)

    manager.delete_job(job.job_id)
    logger.info("Deleted job %s (file=%s)", job.job_id, job.filename)


def _is_running(job: Job) -> bool:
    return not job.finished and job.status in {"queued", "processing"}


@router.delete("/{job_id}")
async def delete_job(
    job_id: str,
    settings: Settings = Depends(get_settings),
    manager: JobManager = Depends(get_job_manager),
    user: AuthUser = Depends(get_current_user),
):
    """Delete a past analysis from history along with all of its artifacts."""
    job = _require_owned_job(manager, job_id, user)
    if _is_running(job):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This analysis is still running — wait for it to finish before deleting.",
        )

    _purge_job(job, settings, manager)
    return success({"job_id": job_id, "deleted": True})


@router.delete("")
async def delete_all_jobs(
    settings: Settings = Depends(get_settings),
    manager: JobManager = Depends(get_job_manager),
    user: AuthUser = Depends(get_current_user),
):
    """Delete every finished analysis from the caller's own history. Running jobs are skipped."""
    deleted = 0
    skipped = 0
    for job in sorted(manager.list_jobs(user_id=user.user_id), key=lambda j: j.created_at):
        if _is_running(job):
            skipped += 1
            continue
        _purge_job(job, settings, manager)
        deleted += 1

    return success({"deleted": deleted, "skipped": skipped})
