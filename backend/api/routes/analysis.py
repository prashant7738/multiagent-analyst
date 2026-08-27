"""Analysis routes: upload CSV, stream progress (SSE), and fetch results."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from api.config import Settings, get_settings
from api.models.schemas import AnalyzeResponse, AuthUser, JobStatus
from api.routes.auth import get_current_user
from api.routes.settings import get_user_settings_store
from api.services.job_manager import JobManager, get_job_manager
from api.services.pipeline_runner import start_pipeline_job
from api.services.result_builder import build_result
from api.services.sse import event_stream
from api.utils.response import success


def _api_key_overrides_for(user: AuthUser, settings: Settings) -> dict[str, str]:
    """Fetch this user's own saved LLM keys, if any, to override the shared/env ones."""
    if not settings.database_url:
        return {}
    try:
        keys = get_user_settings_store(settings).get_keys(user.user_id)
    except Exception:  # noqa: BLE001 — a broken settings lookup must never block analysis
        logger.exception("Failed to load per-user API keys for %s; using shared keys.", user.user_id)
        return {}
    return {
        "groq": keys.get("groq_api_key") or "",
        "gemini": keys.get("gemini_api_key") or "",
        "hf_token": keys.get("hf_token") or "",
    }

logger = logging.getLogger("api.analysis")

router = APIRouter(prefix="/api/analyze", tags=["analysis"])


def _validate_upload(file: UploadFile, settings: Settings) -> None:
    """Reject uploads with an unexpected extension or content type."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in settings.allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(settings.allowed_extensions)}",
        )


def _parse_analysis_config(preprocessing_profile: str, raw_config: str | None) -> dict[str, object]:
    runtime_config: dict[str, object] = {
        "preprocessing_profile": preprocessing_profile.strip() or "balanced",
        "preprocessing_config": {},
    }

    if not raw_config:
        return runtime_config

    try:
        parsed = json.loads(raw_config)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="analysis_config must be valid JSON.",
        ) from exc

    if isinstance(parsed, dict):
        runtime_config["preprocessing_config"] = parsed
    return runtime_config


async def _persist_upload(file: UploadFile, dest: Path, max_bytes: int) -> None:
    """Stream the upload to disk, enforcing the max size without buffering it all."""
    written = 0
    with dest.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > max_bytes:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds the {max_bytes // (1024 * 1024)}MB limit.",
                )
            out.write(chunk)
    if written == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )


@router.post("", response_model=AnalyzeResponse, status_code=status.HTTP_202_ACCEPTED)
async def analyze(
    file: UploadFile = File(...),
    preprocessing_profile: str = Form("balanced"),
    analysis_config: str | None = Form(None),
    settings: Settings = Depends(get_settings),
    manager: JobManager = Depends(get_job_manager),
    user: AuthUser = Depends(get_current_user),
) -> AnalyzeResponse:
    """Accept a CSV, create a job, and launch the pipeline in the background.

    Returns immediately with a ``job_id`` — the frontend then opens the SSE
    stream to follow progress.
    """
    _validate_upload(file, settings)
    runtime_config = _parse_analysis_config(preprocessing_profile, analysis_config)

    job = manager.create_job(filename=file.filename, analysis_config=runtime_config, user_id=user.user_id)
    dest = settings.uploads_dir / f"{job.job_id}.csv"

    try:
        await _persist_upload(file, dest, settings.max_upload_bytes)
    except HTTPException:
        manager.fail(job.job_id, "Upload rejected.")
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to persist upload for job %s", job.job_id)
        manager.fail(job.job_id, str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store the uploaded file.",
        ) from exc

    job.csv_path = str(dest)
    api_key_overrides = _api_key_overrides_for(user, settings)
    start_pipeline_job(manager, job.job_id, str(dest), runtime_config, api_key_overrides=api_key_overrides)

    logger.info("Accepted job %s (file=%s)", job.job_id, file.filename)
    return AnalyzeResponse(
        job_id=job.job_id,
        status=JobStatus.PROCESSING,
        filename=file.filename,
        stream_url=f"/api/analyze/{job.job_id}/stream",
        result_url=f"/api/analyze/{job.job_id}/result",
    )


@router.get("/{job_id}/stream")
async def stream(
    job_id: str,
    manager: JobManager = Depends(get_job_manager),
    user: AuthUser = Depends(get_current_user),
) -> StreamingResponse:
    """Server-Sent-Events stream of pipeline progress for a job."""
    job = manager.get_job(job_id)
    if job is None or job.user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown job_id: {job_id}")

    return StreamingResponse(
        event_stream(manager, job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy buffering (nginx)
        },
    )


@router.post("/{job_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel(
    job_id: str,
    manager: JobManager = Depends(get_job_manager),
    user: AuthUser = Depends(get_current_user),
):
    """Request cancellation of a running analysis.

    Cooperative: the pipeline runner stops at the next agent boundary (it can't
    interrupt an agent mid-execution), then the job ends in the ``cancelled``
    state and the SSE stream closes with a ``pipeline_cancelled`` event.
    """
    job = manager.get_job(job_id)
    if job is None or job.user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown job_id: {job_id}")

    if not manager.request_cancel(job_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "This analysis isn't running.", "status": job.status},
        )
    return success({"job_id": job_id, "cancelling": True})


@router.get("/{job_id}/result")
async def result(
    job_id: str,
    manager: JobManager = Depends(get_job_manager),
    user: AuthUser = Depends(get_current_user),
):
    """Return the full frontend-friendly projection of the final GraphState."""
    job = manager.get_job(job_id)
    if job is None or job.user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown job_id: {job_id}")

    if job.status == "failed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "Pipeline failed.", "error": job.error},
        )

    if job.status != "completed" or job.state is None:
        raise HTTPException(
            status_code=status.HTTP_425_TOO_EARLY,
            detail={"message": "Result not ready yet.", "status": job.status},
        )

    payload = job.result or build_result(job_id, job.state, job.filename)
    return success(payload)
