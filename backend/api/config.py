"""Centralized configuration for the API layer.

All tunables are read from environment variables (optionally via a local
``.env`` file) so nothing is hardcoded. Importing this module also guarantees
that:

* the ``backend/`` directory is importable (agents use ``from main import ...``
  and ``from agents.agent_1 import ...``), and
* the process working directory is ``backend/`` so the agents' relative output
  paths (``outputs/charts``, ``outputs/reports``) resolve correctly.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Path bootstrapping — run BEFORE the pipeline/agents are imported anywhere.
# ---------------------------------------------------------------------------
# api/ -> backend/
BACKEND_DIR: Path = Path(__file__).resolve().parent.parent

# The existing agents print Unicode (box-drawing) characters. On Windows the
# default console code page is cp1252, which raises UnicodeEncodeError on those
# prints and would abort the pipeline. Force UTF-8 on stdout/stderr so agent
# logging never crashes the background job. This does not modify any agent.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

# Make ``main`` and ``agents`` importable regardless of how uvicorn is launched.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Agents write charts/reports using paths relative to the current working
# directory. Anchor the process at backend/ so those land in backend/outputs/.
try:
    os.chdir(BACKEND_DIR)
except OSError:
    pass

# Load environment variables from backend/.env (GROQ_API_KEY, GEMINI_API_KEY…).
load_dotenv(BACKEND_DIR / ".env")
load_dotenv()  # also honor a repo-root .env if present


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _build_database_url() -> str | None:
    raw = os.getenv("DATABASE_URL")
    if raw:
        return raw

    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB")
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    if not all([host, database, user, password]):
        return None

    return (
        f"postgresql://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{database}"
    )


class Settings:
    """Immutable-ish view over environment-driven settings."""

    def __init__(self) -> None:
        self.app_name: str = os.getenv("API_APP_NAME", "MultiAgent DataAnalyst API")
        self.version: str = os.getenv("API_VERSION", "1.0.0")

        self.host: str = os.getenv("API_HOST", "0.0.0.0")
        self.port: int = _get_int("API_PORT", 8000)
        self.reload: bool = _get_bool("API_RELOAD", False)
        self.log_level: str = os.getenv("API_LOG_LEVEL", "info")

        # Optional PostgreSQL persistence for job history / results.
        self.database_url: str | None = _build_database_url()
        self.postgres_schema: str = os.getenv("POSTGRES_SCHEMA", "public")
        self.postgres_jobs_table: str = os.getenv("POSTGRES_JOBS_TABLE", "analysis_jobs")
        self.postgres_users_table: str = os.getenv("POSTGRES_USERS_TABLE", "app_users")

        # Filesystem layout (all absolute, derived from backend/).
        self.backend_dir: Path = BACKEND_DIR
        self.outputs_dir: Path = BACKEND_DIR / os.getenv("API_OUTPUTS_DIR", "outputs")
        self.charts_dir: Path = self.outputs_dir / "charts"
        self.reports_dir: Path = self.outputs_dir / "reports"
        self.uploads_dir: Path = BACKEND_DIR / os.getenv("API_UPLOADS_DIR", "uploads")

        # Upload constraints.
        self.max_upload_bytes: int = _get_int("API_MAX_UPLOAD_MB", 50) * 1024 * 1024
        self.allowed_extensions: set[str] = {".csv"}

        # SSE tuning.
        self.sse_poll_interval: float = float(os.getenv("API_SSE_POLL_INTERVAL", "0.15"))
        self.sse_keepalive_interval: float = float(os.getenv("API_SSE_KEEPALIVE", "15"))

        # Job retention / concurrency.
        self.max_concurrent_jobs: int = _get_int("API_MAX_CONCURRENT_JOBS", 4)
        self.job_ttl_seconds: int = _get_int("API_JOB_TTL_SECONDS", 60 * 60)

        # CORS — comma-separated origins. "*" allows all (dev default).
        origins = os.getenv("API_CORS_ORIGINS", "*")
        self.cors_origins: list[str] = [o.strip() for o in origins.split(",") if o.strip()]

        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        for directory in (self.outputs_dir, self.charts_dir, self.reports_dir, self.uploads_dir):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton of the application settings."""
    return Settings()
