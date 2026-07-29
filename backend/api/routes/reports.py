"""Report download and chart-serving routes."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from api.config import Settings, get_settings
from api.services.job_manager import JobManager, get_job_manager

logger = logging.getLogger("api.reports")

router = APIRouter(tags=["reports"])


def _resolve_within(base: Path, candidate: Path) -> Path:
    """Resolve ``candidate`` and ensure it stays inside ``base`` (no traversal)."""
    base = base.resolve()
    resolved = (candidate if candidate.is_absolute() else base / candidate).resolve()
    if base not in resolved.parents and resolved != base:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid path.")
    return resolved


@router.get("/api/report/{job_id}")
async def download_report(
    job_id: str,
    settings: Settings = Depends(get_settings),
    manager: JobManager = Depends(get_job_manager),
) -> FileResponse:
    """Download the Agent 6 report (PDF when available, else HTML)."""
    job = manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown job_id: {job_id}")

    state = job.state or {}
    report_path = state.get("report_path")
    if not report_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not available for this job.")

    resolved = Path(report_path)
    if not resolved.is_absolute():
        resolved = (settings.backend_dir / report_path).resolve()
    if not resolved.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report file no longer exists on disk.")

    media_type = "application/pdf" if resolved.suffix.lower() == ".pdf" else "text/html"
    filename = f"insight_report_{job_id[:8]}{resolved.suffix}"
    return FileResponse(path=resolved, media_type=media_type, filename=filename)


@router.get("/plots/{filename}")
async def get_plot(
    filename: str,
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    """Serve a generated chart PNG from the charts directory."""
    # Reject any path separators to prevent traversal.
    if "/" in filename or "\\" in filename or filename in {"", ".", ".."}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename.")

    resolved = _resolve_within(settings.charts_dir, Path(filename))
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Chart not found: {filename}")

    return FileResponse(path=resolved, media_type="image/png")
