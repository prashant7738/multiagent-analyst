"""Uniform JSON response and error helpers."""

from __future__ import annotations

from typing import Any

from fastapi import status
from fastapi.responses import JSONResponse

from api.utils.serialization import json_safe


def success(data: Any, status_code: int = status.HTTP_200_OK) -> JSONResponse:
    """Return a JSON response with all values coerced to JSON-safe primitives."""
    return JSONResponse(content=json_safe(data), status_code=status_code)


def error(
    message: str,
    detail: str | None = None,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> JSONResponse:
    """Return a uniform error envelope."""
    return JSONResponse(
        content={"status": "error", "message": message, "detail": detail},
        status_code=status_code,
    )
