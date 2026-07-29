"""Entry point for launching the API server.

Usage:
    python run.py

Configuration is environment-driven (see api/config.py). This wrapper simply
starts uvicorn with the configured host/port/reload settings.
"""

from __future__ import annotations

import uvicorn

from api.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "api.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level=settings.log_level,
    )


if __name__ == "__main__":
    main()
