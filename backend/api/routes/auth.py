"""Signup, login, logout, and session-verification routes backed by PostgreSQL.

Login/signup issue an opaque bearer token (stored server-side in the sessions
table) that the frontend attaches as ``Authorization: Bearer <token>`` on every
subsequent request. ``get_current_user`` is the shared FastAPI dependency other
routers use to identify the caller and scope data (jobs, chat, reports) to them.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from api.config import Settings, get_settings
from api.models.schemas import AuthLoginRequest, AuthResponse, AuthSignupRequest, AuthUser
from api.services.auth_store import PostgresAuthStore

router = APIRouter(prefix="/api/auth", tags=["auth"])


def get_auth_store(settings: Settings = Depends(get_settings)) -> PostgresAuthStore:
    if not settings.database_url:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database is not configured.")
    return PostgresAuthStore(
        settings.database_url,
        schema=settings.postgres_schema,
        table=settings.postgres_users_table,
        sessions_table=settings.postgres_sessions_table,
    )


def _extract_token(authorization: str | None, token_qs: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization[7:].strip()
        if raw:
            return raw
    if token_qs:
        return token_qs.strip()
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")


async def get_current_user(
    authorization: str | None = Header(default=None),
    # EventSource (SSE) cannot set custom headers, so the stream endpoint falls
    # back to a ?token= query param for that one request. Every other endpoint
    # is called via fetch() and uses the Authorization header.
    token: str | None = Query(default=None),
    store: PostgresAuthStore = Depends(get_auth_store),
) -> AuthUser:
    raw_token = _extract_token(authorization, token)
    user = store.get_user_by_token(raw_token)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session.")
    return AuthUser(**user)


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: AuthSignupRequest, store: PostgresAuthStore = Depends(get_auth_store)) -> AuthResponse:
    try:
        user = store.create_user(payload.name, payload.email, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    token = store.create_session(user["user_id"])
    return AuthResponse(message="Account created.", user=user, token=token)


@router.post("/login", response_model=AuthResponse)
async def login(payload: AuthLoginRequest, store: PostgresAuthStore = Depends(get_auth_store)) -> AuthResponse:
    user = store.authenticate_user(payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    token = store.create_session(user["user_id"])
    return AuthResponse(message="Signed in.", user=user, token=token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    authorization: str | None = Header(default=None),
    store: PostgresAuthStore = Depends(get_auth_store),
) -> None:
    """Invalidate the caller's bearer token server-side. Always succeeds."""
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization[7:].strip()
        if raw:
            store.delete_session(raw)
    return None