"""Health check route."""

from __future__ import annotations

import os
import time
import logging
from fastapi import APIRouter, Depends

from api.config import Settings, get_settings
from api.models.schemas import AuthUser, HealthResponse, LLMHealthStatus, RAGHealthStatus
from api.routes.auth import get_optional_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["health"])

# The passive /api/health poll (frontend hits this every 30s) now makes a real
# completion/generation call per provider instead of a free listing call, to catch
# decommissioned models and exhausted quota (see the check functions below). Some
# providers' free tiers are tiny (Gemini here: 20 requests/day) — polling that
# unthrottled would exhaust the quota through the health check alone. Cache each
# provider's result for a short TTL so passive polling stays cheap; the manual
# "Test Connections" button (/health/test-llm) always bypasses this cache.
_HEALTH_CACHE_TTL_SECONDS = 90
_health_cache: dict[str, tuple[float, str]] = {}


def _cached_check(key: str, check_fn) -> str:
    now = time.monotonic()
    cached = _health_cache.get(key)
    if cached is not None and (now - cached[0]) < _HEALTH_CACHE_TTL_SECONDS:
        return cached[1]
    value = check_fn()
    _health_cache[key] = (now, value)
    return value


def _check_groq_health(api_key: str | None = None) -> str:
    """Check Groq using the exact production model + call shape, not just connectivity.

    A bare ``models.list()`` call only proves the API key is valid — it stays "healthy"
    even when the model string agents actually call has been decommissioned by Groq, or
    the account is out of quota. This sends the same minimal completion request every
    real agent call makes, against the same ``agents.agent_2.GROQ_MODEL`` constant, so a
    dead model or exhausted quota shows up here instead of silently degrading every
    semantic-tagging and RAG-chat call to the deterministic fallback.

    ``api_key``, when passed, is tested in place of the configured ``GROQ_API_KEY`` env
    var — used by the "test my key" flow before a user-submitted key is saved.
    """
    try:
        api_key = api_key or os.getenv("GROQ_API_KEY")
        if not api_key:
            logger.debug("Groq: API key not configured")
            return "not_configured"

        from groq import Groq
        from agents.agent_2 import GROQ_MODEL, GROQ_REASONING_EFFORT

        client = Groq(api_key=api_key)
        client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            max_tokens=5,
            reasoning_effort=GROQ_REASONING_EFFORT,
        )
        logger.debug("Groq: Health check passed")
        return "healthy"
    except Exception as e:
        error_msg = str(e).lower()
        logger.debug(f"Groq health check failed: {e}")
        if "decommissioned" in error_msg or "model_not_found" in error_msg or "does not exist" in error_msg:
            return "model_unavailable"
        if "rate limit" in error_msg or "quota" in error_msg or "429" in error_msg:
            return "quota_exceeded"
        if "api key" in error_msg or "403" in error_msg:
            return "invalid_key"
        if "401" in error_msg:
            return "unauthorized"
        return "unreachable"


def _check_gemini_health(api_key: str | None = None) -> str:
    """Check Gemini using the exact production model + SDK + call shape, not just connectivity.

    Two gaps in the old check: (1) it used the deprecated ``google.generativeai`` package
    while production code (``agents/agent_2.py``) uses the current ``google.genai`` SDK, so
    it was testing a code path nothing else in this app uses; (2) ``list_models()`` proves
    the key works but not that the configured model/quota can actually serve a request.
    This sends a minimal real ``generate_content`` call with the production
    ``agents.agent_2.GEMINI_MODEL`` and the same client construction agents use, so a
    retired model or exhausted quota (both seen on this project) shows up as non-healthy.

    ``api_key``, when passed, is tested in place of the configured env-var keys — used by
    the "test my key" flow before a user-submitted key is saved.
    """
    try:
        from agents.agent_2 import GEMINI_MODEL, _get_configured_gemini_api_keys

        resolved_key = api_key or (
            os.getenv("GEMINI_API_KEY")
            or os.getenv("Gemini_API_Key")
            or os.getenv("GOOGLE_API_KEY")
        )
        configured_keys = [] if api_key else _get_configured_gemini_api_keys()
        if not resolved_key and not configured_keys:
            logger.debug("Gemini: API key not configured")
            return "not_configured"

        from google import genai

        client = genai.Client(api_key=resolved_key or configured_keys[0])
        client.models.generate_content(
            model=GEMINI_MODEL,
            contents="Reply with exactly: OK",
            config={"max_output_tokens": 5},
        )
        logger.debug("Gemini: Health check passed")
        return "healthy"
    except Exception as e:
        error_msg = str(e).lower()
        logger.info(f"Gemini health check failed: {type(e).__name__}: {e}")
        if "resource_exhausted" in error_msg or "429" in error_msg or "quota" in error_msg:
            return "quota_exceeded"
        if "404" in error_msg or "not_found" in error_msg or "no longer available" in error_msg:
            return "model_unavailable"
        if "api key" in error_msg or "403" in error_msg:
            return "invalid_key"
        if "401" in error_msg:
            return "unauthorized"
        return "unreachable"


def _check_huggingface_health(api_key: str | None = None) -> str:
    """Check if Hugging Face Inference API is accessible via a lightweight call.

    ``api_key``, when passed, is tested in place of the configured env-var token — used
    by the "test my key" flow before a user-submitted token is saved.
    """
    try:
        api_key = api_key or os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_API_TOKEN")
        if not api_key:
            logger.debug("Hugging Face: API key not configured")
            return "not_configured"
        
        from huggingface_hub import InferenceClient
        
        # Use the embedding model configured for RAG
        client = InferenceClient(
            model="BAAI/bge-base-en-v1.5",
            provider="hf-inference",
            token=api_key,
        )
        # Lightweight call to verify connectivity - use feature extraction for embeddings
        result = client.feature_extraction(text="test")
        # Result is a numpy array, check if it has content
        if result is not None:
            logger.debug("Hugging Face: Health check passed")
            return "healthy"
        return "unreachable"
    except Exception as e:
        error_msg = str(e).lower()
        logger.info(f"Hugging Face health check failed: {type(e).__name__}: {e}")
        if "api key" in error_msg or "401" in error_msg or "403" in error_msg or "invalid" in error_msg or "unauthorized" in error_msg:
            return "invalid_key"
        if "rate limit" in error_msg or "quota" in error_msg or "429" in error_msg:
            return "quota_exceeded"
        if "not_configured" in error_msg or "token" in error_msg:
            return "not_configured"
        return "unreachable"


def _check_database_health() -> str:
    """Check if the Postgres database backing RAG dataset-chat is reachable and has pgvector.

    This is intentionally separate from the LLM checks above: Groq/Gemini/HF can all be
    "healthy" while RAG chat is dead in the water because DATABASE_URL isn't set, the
    database is unreachable, or the ``vector`` extension was never installed.
    """
    settings = get_settings()
    dsn = settings.database_url
    if not dsn:
        logger.debug("Database: DATABASE_URL not configured")
        return "not_configured"

    try:
        import psycopg

        with psycopg.connect(dsn, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector';")
                if cur.fetchone() is None:
                    logger.debug("Database: vector extension not installed")
                    return "extension_missing"
        logger.debug("Database: Health check passed")
        return "healthy"
    except Exception as e:
        error_msg = str(e).lower()
        logger.info(f"Database health check failed: {type(e).__name__}: {e}")
        if "password" in error_msg or "authentication" in error_msg:
            return "auth_failed"
        return "unreachable"


@router.get("/health", response_model=HealthResponse)
@router.head("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Liveness probe for the API layer plus LLM connectivity and RAG infra checks.

    Provider checks are cached for _HEALTH_CACHE_TTL_SECONDS — this endpoint is polled
    every 30s by the frontend, and each check is now a real, quota-metered API call.

    Also registered for HEAD (not just GET): uptime monitors (UptimeRobot, etc.) default
    to HEAD requests, which FastAPI does not auto-derive from a GET-only route — without
    this, every such monitor gets a 405 and never actually keeps the service warm.
    """
    groq_status = _cached_check("groq", _check_groq_health)
    gemini_status = _cached_check("gemini", _check_gemini_health)
    hf_status = _cached_check("huggingface", _check_huggingface_health)
    db_status = _cached_check("database", _check_database_health)
    logger.info(
        f"Health check: Groq={groq_status}, Gemini={gemini_status}, "
        f"HuggingFace={hf_status}, Database={db_status}"
    )
    return HealthResponse(
        status="healthy",
        version=settings.version,
        llm=LLMHealthStatus(groq=groq_status, gemini=gemini_status, huggingface=hf_status),
        rag=RAGHealthStatus(database=db_status),
    )


def _saved_user_keys(settings: Settings, user: AuthUser | None) -> dict[str, str]:
    """The signed-in user's saved provider keys, or {} for anon / no DB / error.

    Keyed by the settings store's field names: groq_api_key, gemini_api_key, hf_token.
    """
    if user is None or not settings.database_url:
        return {}
    try:
        from api.routes.settings import get_user_settings_store  # deferred: avoids import cycle

        return {k: v for k, v in (get_user_settings_store(settings).get_keys(user.user_id) or {}).items() if v}
    except Exception:  # noqa: BLE001 — fall back to shared/default keys
        logger.info("test-llm: could not load saved keys for %s; testing shared defaults.", user.user_id)
        return {}


@router.post("/health/test-llm", response_model=HealthResponse)
async def test_llm(
    settings: Settings = Depends(get_settings),
    user: AuthUser | None = Depends(get_optional_user),
) -> HealthResponse:
    """On-demand test of LLM connectivity and RAG infra (the "Test Connections" button).

    Tests the *effective* key per provider: the signed-in caller's saved key when
    they have one, otherwise the shared/default key — so this reflects exactly what
    a real analysis or chat request for that user would use.

    Always bypasses the passive-poll cache. The results are written back into that
    cache only when they reflect the shared defaults (no per-user key was used) —
    otherwise one user's key status would bleed into the public /api/health poll.
    """
    logger.info("Running on-demand health tests (user=%s)...", getattr(user, "user_id", None))
    now = time.monotonic()
    saved = _saved_user_keys(settings, user)

    groq_status = _check_groq_health(saved.get("groq_api_key"))
    gemini_status = _check_gemini_health(saved.get("gemini_api_key"))
    hf_status = _check_huggingface_health(saved.get("hf_token"))
    db_status = _check_database_health()

    if not saved:  # only cache when we tested the shared defaults
        _health_cache["groq"] = (now, groq_status)
        _health_cache["gemini"] = (now, gemini_status)
        _health_cache["huggingface"] = (now, hf_status)
    _health_cache["database"] = (now, db_status)

    logger.info(
        f"Health test results: Groq={groq_status}, Gemini={gemini_status}, "
        f"HuggingFace={hf_status}, Database={db_status}"
    )
    return HealthResponse(
        status="healthy",
        version=settings.version,
        llm=LLMHealthStatus(groq=groq_status, gemini=gemini_status, huggingface=hf_status),
        rag=RAGHealthStatus(database=db_status),
    )
