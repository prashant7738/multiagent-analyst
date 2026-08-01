"""Signup and login routes backed by PostgreSQL."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from api.config import Settings, get_settings
from api.models.schemas import AuthLoginRequest, AuthResponse, AuthSignupRequest
from api.services.auth_store import PostgresAuthStore

router = APIRouter(prefix="/api/auth", tags=["auth"])


def get_auth_store(settings: Settings = Depends(get_settings)) -> PostgresAuthStore:
    if not settings.database_url:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database is not configured.")
    return PostgresAuthStore(
        settings.database_url,
        schema=settings.postgres_schema,
        table=settings.postgres_users_table,
    )


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: AuthSignupRequest, store: PostgresAuthStore = Depends(get_auth_store)) -> AuthResponse:
    try:
        user = store.create_user(payload.name, payload.email, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return AuthResponse(message="Account created.", user=user)


@router.post("/login", response_model=AuthResponse)
async def login(payload: AuthLoginRequest, store: PostgresAuthStore = Depends(get_auth_store)) -> AuthResponse:
    user = store.authenticate_user(payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    return AuthResponse(message="Signed in.", user=user)