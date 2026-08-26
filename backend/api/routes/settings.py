"""Per-user LLM API key settings — let a signed-in user supply their own Groq /
Gemini / Hugging Face key when the app's shared/default key is out of quota,
revoked, or otherwise not working. Stored encrypted at rest; never echoed back
in plaintext once saved (only a masked preview) — see ``user_settings_store.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from api.config import Settings, get_settings
from api.models.schemas import (
    ApiKeysStatusResponse,
    ApiKeysUpdateRequest,
    ApiKeyStatus,
    ApiKeyTestRequest,
    ApiKeyTestResponse,
    AuthUser,
)
from api.routes.auth import get_current_user
from api.routes.health import _check_gemini_health, _check_groq_health, _check_huggingface_health
from api.services.user_settings_store import PostgresUserSettingsStore

router = APIRouter(prefix="/api/settings", tags=["settings"])

_FIELD_BY_PROVIDER = {"groq": "groq_api_key", "gemini": "gemini_api_key", "hf_token": "hf_token"}


def get_user_settings_store(settings: Settings = Depends(get_settings)) -> PostgresUserSettingsStore:
    if not settings.database_url:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database is not configured.")
    return PostgresUserSettingsStore(
        settings.database_url,
        schema=settings.postgres_schema,
        table=settings.postgres_user_settings_table,
    )


def _mask(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:4]}…{value[-4:]}"


def _status_response(keys: dict[str, str | None]) -> ApiKeysStatusResponse:
    return ApiKeysStatusResponse(
        groq=ApiKeyStatus(configured=bool(keys.get("groq_api_key")), masked=_mask(keys.get("groq_api_key"))),
        gemini=ApiKeyStatus(configured=bool(keys.get("gemini_api_key")), masked=_mask(keys.get("gemini_api_key"))),
        hf_token=ApiKeyStatus(configured=bool(keys.get("hf_token")), masked=_mask(keys.get("hf_token"))),
    )


@router.get("/api-keys", response_model=ApiKeysStatusResponse)
async def get_api_keys(
    store: PostgresUserSettingsStore = Depends(get_user_settings_store),
    user: AuthUser = Depends(get_current_user),
) -> ApiKeysStatusResponse:
    """Return whether each provider key is configured, and a masked preview only."""
    return _status_response(store.get_keys(user.user_id))


@router.put("/api-keys", response_model=ApiKeysStatusResponse)
async def update_api_keys(
    payload: ApiKeysUpdateRequest,
    store: PostgresUserSettingsStore = Depends(get_user_settings_store),
    user: AuthUser = Depends(get_current_user),
) -> ApiKeysStatusResponse:
    """Save one or more keys. Omitted fields are left unchanged; "" clears a key."""
    store.save_keys(user.user_id, payload.model_dump(exclude_unset=True))
    return _status_response(store.get_keys(user.user_id))


@router.delete("/api-keys/{provider}", response_model=ApiKeysStatusResponse)
async def delete_api_key(
    provider: str,
    store: PostgresUserSettingsStore = Depends(get_user_settings_store),
    user: AuthUser = Depends(get_current_user),
) -> ApiKeysStatusResponse:
    field = _FIELD_BY_PROVIDER.get(provider)
    if field is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown provider: {provider}")
    store.save_keys(user.user_id, {field: ""})
    return _status_response(store.get_keys(user.user_id))


@router.post("/api-keys/test", response_model=ApiKeyTestResponse)
async def test_api_key(
    payload: ApiKeyTestRequest,
    user: AuthUser = Depends(get_current_user),
) -> ApiKeyTestResponse:
    """Try a candidate key against the real provider before saving it.

    Never persists the key — this only validates it. Requires sign-in so the
    validation calls (which spend the submitter's own quota) can't be used as
    an open key-checking proxy by an anonymous caller.
    """
    checkers = {
        "groq": _check_groq_health,
        "gemini": _check_gemini_health,
        "hf_token": _check_huggingface_health,
    }
    checker = checkers[payload.provider]
    result = checker(payload.api_key)
    return ApiKeyTestResponse(provider=payload.provider, status=result)
