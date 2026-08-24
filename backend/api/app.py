"""FastAPI application factory.

Wires configuration, CORS, logging, global exception handling, and all routers
into a single ASGI app. Importing this module (via ``api.config``) also
bootstraps ``sys.path`` and the working directory so the existing pipeline and
agents import unchanged.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# NOTE: importing api.config first performs the sys.path / cwd bootstrap.
from api.config import Settings, get_settings
from api.middleware.cors import configure_cors
from api.routes import analysis, auth, chat, health, jobs, reports

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("api.app")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings: Settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description=(
            "HTTP + SSE communication layer around the MultiAgent DataAnalyst "
            "LangGraph pipeline (Agents 1-6)."
        ),
    )

    configure_cors(app)

    # ── Routers ───────────────────────────────────────────────────────────
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(analysis.router)
    app.include_router(reports.router)
    app.include_router(jobs.router)
    app.include_router(chat.router)

    # ── Global exception handlers — never crash, always JSON ─────────────
    @app.exception_handler(RequestValidationError)
    async def _on_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        logger.warning("Validation error on %s: %s", request.url.path, exc.errors())
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"status": "error", "message": "Request validation failed",
                     "detail": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def _on_unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "error", "message": "Internal server error",
                     "detail": str(exc)},
        )

    @app.get("/", tags=["meta"])
    async def root() -> dict[str, str]:
        return {
            "name": settings.app_name,
            "version": settings.version,
            "docs": "/docs",
            "health": "/api/health",
        }

    @app.on_event("startup")
    async def _sweep_stale_rag_builds() -> None:
        """Mark RAG builds orphaned by a previous server restart as failed.

        A ``building`` job whose build thread died with the old process would
        otherwise block rebuilds forever (try_begin_rag_build refuses while
        building) and leave the frontend indicator spinning indefinitely.
        """
        from api.services.job_manager import get_job_manager

        try:
            manager = get_job_manager()
        except Exception:  # noqa: BLE001 — persistence may be unavailable at boot
            logger.warning("RAG startup sweep skipped: job manager unavailable.")
            return
        for job in manager.list_jobs():
            if job.rag_status == "building":
                manager.set_rag_status(job.job_id, "failed", error="Indexing was interrupted by a server restart.")
                logger.warning("Marked stale RAG build for job %s as failed.", job.job_id)

    logger.info("%s v%s initialized.", settings.app_name, settings.version)
    return app


app = create_app()
