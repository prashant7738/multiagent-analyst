"""Dataset chat routes — per-job Q&A grounded in the analysis result."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from api.config import Settings, get_settings
from api.models.schemas import AuthUser, ChatAskRequest, ChatMessage, ChatResponse
from api.routes.auth import get_current_user
from api.routes.settings import get_user_settings_store
from api.services.chat_service import ask_question, build_fallback_chat_response
from api.services.job_manager import JobManager, get_job_manager
from api.services.request_context import set_api_key_overrides

logger = logging.getLogger("api.chat")

router = APIRouter(prefix="/api/analyze/{job_id}/chat", tags=["chat"])


def _get_owned_job(job_id: str, manager: JobManager, user: AuthUser):
    job = manager.get_job(job_id)
    if job is None or job.user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown job_id: {job_id}")
    return job


def _get_ready_job(job_id: str, manager: JobManager, user: AuthUser):
    job = _get_owned_job(job_id, manager, user)
    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job {job_id} is not completed yet (status: {job.status}).",
        )
    return job


@router.get("", response_model=list[ChatMessage])
async def get_chat_history(
    job_id: str,
    manager: JobManager = Depends(get_job_manager),
    user: AuthUser = Depends(get_current_user),
) -> list[ChatMessage]:
    """Return the stored Q&A transcript for this job."""
    job = _get_owned_job(job_id, manager, user)
    return [ChatMessage(**message) for message in job.chat_history]


@router.delete("", response_model=list[ChatMessage])
async def clear_chat_history(
    job_id: str,
    manager: JobManager = Depends(get_job_manager),
    user: AuthUser = Depends(get_current_user),
) -> list[ChatMessage]:
    """Clear the Q&A transcript for this job.

    Only the conversation is removed. The dataset's RAG index (row + fact
    embeddings) stays built, so the next question needs no re-embedding.
    Returns the now-empty history.
    """
    _get_owned_job(job_id, manager, user)
    manager.clear_chat_history(job_id)
    return []


@router.post("", response_model=ChatResponse)
async def ask_dataset_question(
    job_id: str,
    payload: ChatAskRequest,
    manager: JobManager = Depends(get_job_manager),
    user: AuthUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    """Ask a question about the analyzed dataset for ``job_id``."""
    job = _get_ready_job(job_id, manager, user)

    if settings.database_url:
        try:
            keys = get_user_settings_store(settings).get_keys(user.user_id)
            set_api_key_overrides({
                "groq": keys.get("groq_api_key") or "",
                "gemini": keys.get("gemini_api_key") or "",
                "hf_token": keys.get("hf_token") or "",
            })
        except Exception:  # noqa: BLE001 — fall back to the shared/env keys
            logger.exception("Failed to load per-user API keys for %s; using shared keys.", user.user_id)

    try:
        outcome = ask_question(manager, job, payload.question)
    except Exception as exc:  # noqa: BLE001 — surface as a clean 500, never crash the app
        logger.exception("Chat request failed for job %s", job_id)
        outcome = build_fallback_chat_response(job, payload.question)
        outcome["answer"] = (
            f"{outcome['answer']}\n\n(An internal chat error occurred, so I used the fallback answer path instead.)"
        )

    user_message = {"role": "user", "content": payload.question, "chart": None}
    assistant_message = {
        "role": "assistant",
        "content": outcome["answer"],
        "chart": outcome.get("chart"),
        "source": outcome.get("source"),
    }
    manager.add_chat_messages(job_id, [user_message, assistant_message])

    updated_job = manager.get_job(job_id)
    history = [ChatMessage(**message) for message in (updated_job.chat_history if updated_job else [])]

    return ChatResponse(
        answer=outcome["answer"],
        source=outcome["source"],
        chart=outcome.get("chart"),
        chart_generated=outcome.get("chart_generated", False),
        history=history,
        index_status=outcome.get("index_status"),
    )
