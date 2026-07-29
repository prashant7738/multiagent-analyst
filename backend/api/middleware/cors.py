"""CORS configuration for the React/Vite frontend.

Origins are environment-driven (``API_CORS_ORIGINS``). The default of ``*`` is
convenient for local development; set explicit origins in production.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import get_settings


def configure_cors(app: FastAPI) -> None:
    """Attach the CORS middleware using configured origins."""
    settings = get_settings()
    allow_all = "*" in settings.cors_origins

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if allow_all else settings.cors_origins,
        # Credentials cannot be combined with a wildcard origin per the spec.
        allow_credentials=not allow_all,
        allow_methods=["*"],
        allow_headers=["*"],
        # SSE clients read custom headers; expose what may be useful.
        expose_headers=["Content-Type", "Cache-Control"],
    )
