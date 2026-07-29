"""Health check route."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.config import Settings, get_settings
from api.models.schemas import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Liveness probe for the API layer."""
    return HealthResponse(status="healthy", version=settings.version)
