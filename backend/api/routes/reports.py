"""Report download and chart-serving routes."""

from __future__ import annotations

import io
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, StreamingResponse, Response

from api.config import Settings, get_settings
from api.models.schemas import AuthUser
from api.routes.auth import get_current_user
from api.services.job_manager import JobManager, get_job_manager

try:
    from weasyprint import HTML as WeasyHTML
    HAS_WEASYPRINT = True
except ImportError:
    HAS_WEASYPRINT = False

logger = logging.getLogger("api.reports")

router = APIRouter(tags=["reports"])


def _resolve_within(base: Path, candidate: Path) -> Path:
    """Resolve ``candidate`` and ensure it stays inside ``base`` (no traversal)."""
    base = base.resolve()
    resolved = (candidate if candidate.is_absolute() else base / candidate).resolve()
    if base not in resolved.parents and resolved != base:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid path.")
    return resolved


@router.get("/api/report/{job_id}", response_model=None)
async def download_report(
    job_id: str,
    format: str = Query("html", pattern="^(html|pdf)$"),
    settings: Settings = Depends(get_settings),
    manager: JobManager = Depends(get_job_manager),
    user: AuthUser = Depends(get_current_user),
) -> Response:
    """Download the Agent 6 report in HTML or PDF format.

    Query parameters:
    - format: 'html' or 'pdf' (default: 'html')

    If format='pdf' and WeasyPrint is available, converts HTML to PDF on-the-fly.
    Falls back to HTML if PDF generation fails.
    """
    job = manager.get_job(job_id)
    if job is None or job.user_id != user.user_id:
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

    if format == "html":
        if resolved.suffix.lower() == ".pdf":
            resolved = resolved.with_suffix(".html")
        if not resolved.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="HTML report file no longer exists on disk.")
        filename = f"insight_report_{job_id[:8]}.html"
        return FileResponse(path=resolved, media_type="text/html", filename=filename)

    if resolved.suffix.lower() == ".pdf":
        filename = f"insight_report_{job_id[:8]}.pdf"
        return FileResponse(path=resolved, media_type="application/pdf", filename=filename)

    # If PDF is requested and we have WeasyPrint, convert HTML to PDF
    if format == "pdf" and HAS_WEASYPRINT and resolved.suffix.lower() == ".html":
        try:
            # Read HTML file
            html_content = resolved.read_text(encoding="utf-8")

            # Convert HTML to PDF using WeasyPrint with error handling
            try:
                pdf_bytes = WeasyHTML(string=html_content).write_pdf()

                # Return as streaming response
                filename = f"insight_report_{job_id[:8]}.pdf"
                return StreamingResponse(
                    io.BytesIO(pdf_bytes),
                    media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={filename}"}
                )
            except Exception as pdf_error:
                logger.warning(f"WeasyPrint failed for job {job_id}: {pdf_error}")
                # Fall back to HTML if PDF generation fails
                logger.info(f"Falling back to HTML format for job {job_id}")
                filename = f"insight_report_{job_id[:8]}.html"
                return FileResponse(path=resolved, media_type="text/html", filename=filename)

        except Exception as e:
            logger.error(f"Error processing report for job {job_id}: {e}")
            # Final fallback to HTML
            filename = f"insight_report_{job_id[:8]}.html"
            return FileResponse(path=resolved, media_type="text/html", filename=filename)

    # Default: return HTML
    filename = f"insight_report_{job_id[:8]}.html"
    return FileResponse(path=resolved, media_type="text/html", filename=filename)


@router.get("/plots/{file_path:path}")
async def get_plot(
    file_path: str,
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    """Serve a generated chart PNG from the charts directory.

    Charts may live flat in ``outputs/charts`` or in per-job subfolders
    (``outputs/charts/<job_id>/…``); both resolve here. Path traversal is
    rejected via :func:`_resolve_within`.
    """
    if not file_path or file_path.strip(".") in {"", "."}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid path.")
    if "\\" in file_path or ".." in file_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename.")

    resolved = _resolve_within(settings.charts_dir, Path(file_path))
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Chart not found: {file_path}")

    return FileResponse(path=resolved, media_type="image/png")
