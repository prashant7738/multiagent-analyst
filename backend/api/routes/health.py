"""Health check route."""

from __future__ import annotations

import os
import logging
from fastapi import APIRouter, Depends

from api.config import Settings, get_settings
from api.models.schemas import HealthResponse, LLMHealthStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["health"])


def _check_groq_health() -> str:
    """Check if Groq API is accessible via a lightweight call."""
    try:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            logger.debug("Groq: API key not configured")
            return "not_configured"
        
        from groq import Groq
        client = Groq(api_key=api_key)
        # Lightweight call to verify connectivity
        list(client.models.list())
        logger.debug("Groq: Health check passed")
        return "healthy"
    except Exception as e:
        error_msg = str(e).lower()
        logger.debug(f"Groq health check failed: {e}")
        if "api key" in error_msg or "403" in error_msg:
            return "invalid_key"
        if "401" in error_msg:
            return "unauthorized"
        return "unreachable"


def _check_gemini_health() -> str:
    """Check if Google Gemini API is accessible via a lightweight call."""
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.debug("Gemini: API key not configured")
            return "not_configured"
        
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        list(genai.list_models())
        logger.debug("Gemini: Health check passed")
        return "healthy"
    except Exception as e:
        error_msg = str(e).lower()
        logger.info(f"Gemini health check failed: {type(e).__name__}: {e}")
        if "api key" in error_msg or "403" in error_msg:
            return "invalid_key"
        if "401" in error_msg:
            return "unauthorized"
        return "unreachable"


def _check_huggingface_health() -> str:
    """Check if Hugging Face Inference API is accessible via a lightweight call."""
    try:
        api_key = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_API_TOKEN")
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


@router.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Liveness probe for the API layer plus LLM connectivity checks."""
    groq_status = _check_groq_health()
    gemini_status = _check_gemini_health()
    hf_status = _check_huggingface_health()
    logger.info(f"Health check: Groq={groq_status}, Gemini={gemini_status}, HuggingFace={hf_status}")
    return HealthResponse(
        status="healthy",
        version=settings.version,
        llm=LLMHealthStatus(groq=groq_status, gemini=gemini_status, huggingface=hf_status),
    )


@router.post("/health/test-llm", response_model=LLMHealthStatus)
async def test_llm() -> LLMHealthStatus:
    """On-demand test of LLM connectivity (called manually from frontend button)."""
    logger.info("Running on-demand LLM health tests...")
    groq_status = _check_groq_health()
    gemini_status = _check_gemini_health()
    hf_status = _check_huggingface_health()
    logger.info(f"LLM test results: Groq={groq_status}, Gemini={gemini_status}, HuggingFace={hf_status}")
    return LLMHealthStatus(groq=groq_status, gemini=gemini_status, huggingface=hf_status)
