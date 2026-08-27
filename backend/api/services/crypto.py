"""Symmetric encryption for secrets stored at rest (user-submitted LLM API keys).

Key material comes from ``APP_ENCRYPTION_KEY`` if set; otherwise a key is
generated once and cached in ``backend/.encryption_key`` (gitignored) so it
survives process restarts. This is a single-instance-deployment convenience —
a real multi-instance deployment should set ``APP_ENCRYPTION_KEY`` explicitly
so every instance decrypts with the same key.
"""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_KEY_FILE = _BACKEND_DIR / ".encryption_key"

_fernet: Fernet | None = None


def _load_or_create_key() -> bytes:
    env_key = os.getenv("APP_ENCRYPTION_KEY")
    if env_key:
        return env_key.encode("utf-8")

    if _KEY_FILE.exists():
        return _KEY_FILE.read_bytes().strip()

    key = Fernet.generate_key()
    _KEY_FILE.write_bytes(key)
    return key


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_or_create_key())
    return _fernet


def encrypt(value: str) -> str:
    return _get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str | None:
    """Decrypt ``token``, or return None if it was encrypted under a different key."""
    try:
        return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None
