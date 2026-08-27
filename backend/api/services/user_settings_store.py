"""Per-user LLM API key storage (Groq / Gemini / Hugging Face), encrypted at rest.

Lets a signed-in user supply their own key when the app's shared/default key
is out of quota, revoked, or otherwise not working — used to override the
process-wide keys in ``api/config.py`` for that user's own jobs/chat/RAG only.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg import sql

from api.services.crypto import decrypt, encrypt
from api.services.db_pool import get_pool

_FIELDS = ("groq_api_key", "gemini_api_key", "hf_token")


class PostgresUserSettingsStore:
    def __init__(self, dsn: str, schema: str = "public", table: str = "user_api_keys") -> None:
        self.dsn = dsn
        self.schema = schema
        self.table = table
        self._initialized = False

    @contextmanager
    def _connect(self) -> Iterator[psycopg.Connection]:
        with get_pool(self.dsn).connection() as conn:
            yield conn

    def _ensure_schema(self) -> None:
        if self._initialized:
            return
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {};").format(sql.Identifier(self.schema)))
                cur.execute(
                    sql.SQL(
                        """
                        CREATE TABLE IF NOT EXISTS {}.{} (
                            user_id TEXT PRIMARY KEY,
                            groq_api_key TEXT,
                            gemini_api_key TEXT,
                            hf_token TEXT,
                            updated_at TIMESTAMPTZ NOT NULL
                        );
                        """
                    ).format(sql.Identifier(self.schema), sql.Identifier(self.table))
                )
        self._initialized = True

    def get_keys(self, user_id: str) -> dict[str, str | None]:
        """Return this user's decrypted keys, e.g. {"groq_api_key": "gsk_...", ...}.

        A field is None if never set. Internal use only (pipeline/chat/RAG) —
        never return this dict's values directly to the frontend.
        """
        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT * FROM {}.{} WHERE user_id = %s;").format(
                        sql.Identifier(self.schema), sql.Identifier(self.table)
                    ),
                    (user_id,),
                )
                row = cur.fetchone()
        if row is None:
            return {field: None for field in _FIELDS}
        return {
            field: (decrypt(row[field]) if row.get(field) else None)
            for field in _FIELDS
        }

    def save_keys(self, user_id: str, updates: dict[str, str | None]) -> None:
        """Upsert ``updates`` onto this user's stored keys.

        Only keys present in ``updates`` are touched. A value of "" clears that
        field; any other non-empty string replaces it (encrypted); a key absent
        from ``updates`` is left as-is.
        """
        self._ensure_schema()
        current = self.get_keys(user_id)
        merged: dict[str, str | None] = dict(current)
        for field, value in updates.items():
            if field not in _FIELDS:
                continue
            if value == "":
                merged[field] = None
            elif value is not None:
                merged[field] = value

        payload = {
            "user_id": user_id,
            **{field: (encrypt(merged[field]) if merged.get(field) else None) for field in _FIELDS},
        }

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        """
                        INSERT INTO {}.{} (user_id, groq_api_key, gemini_api_key, hf_token, updated_at)
                        VALUES (%(user_id)s, %(groq_api_key)s, %(gemini_api_key)s, %(hf_token)s, NOW())
                        ON CONFLICT (user_id) DO UPDATE SET
                            groq_api_key = EXCLUDED.groq_api_key,
                            gemini_api_key = EXCLUDED.gemini_api_key,
                            hf_token = EXCLUDED.hf_token,
                            updated_at = NOW();
                        """
                    ).format(sql.Identifier(self.schema), sql.Identifier(self.table)),
                    payload,
                )
