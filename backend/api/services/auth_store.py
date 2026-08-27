"""Optional PostgreSQL persistence for application users and their login sessions."""

from __future__ import annotations

import secrets
from contextlib import contextmanager
from typing import Any, Iterator
from uuid import uuid4

import psycopg
from passlib.context import CryptContext
from psycopg import errors, sql

from api.services.db_pool import get_pool


_PWD_CONTEXT = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


class PostgresAuthStore:
    def __init__(
        self,
        dsn: str,
        schema: str = "public",
        table: str = "app_users",
        sessions_table: str = "app_sessions",
    ) -> None:
        self.dsn = dsn
        self.schema = schema
        self.table = table
        self.sessions_table = sessions_table
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
                            name TEXT NOT NULL,
                            email TEXT NOT NULL,
                            email_lower TEXT NOT NULL UNIQUE,
                            password_hash TEXT NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL,
                            updated_at TIMESTAMPTZ NOT NULL
                        );
                        """
                    ).format(sql.Identifier(self.schema), sql.Identifier(self.table))
                )
                cur.execute(
                    sql.SQL(
                        """
                        CREATE TABLE IF NOT EXISTS {}.{} (
                            token TEXT PRIMARY KEY,
                            user_id TEXT NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL
                        );
                        """
                    ).format(sql.Identifier(self.schema), sql.Identifier(self.sessions_table))
                )
                cur.execute(
                    sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {}.{} (user_id);").format(
                        sql.Identifier(f"idx_{self.sessions_table}_user_id"),
                        sql.Identifier(self.schema),
                        sql.Identifier(self.sessions_table),
                    )
                )
        self._initialized = True

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def _public_user(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "user_id": row["user_id"],
            "name": row["name"],
            "email": row["email"],
            "created_at": row["created_at"],
        }

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        self._ensure_schema()
        normalized = self._normalize_email(email)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT * FROM {}.{} WHERE email_lower = %s;").format(
                        sql.Identifier(self.schema), sql.Identifier(self.table)
                    ),
                    (normalized,),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def create_user(self, name: str, email: str, password: str) -> dict[str, Any]:
        self._ensure_schema()
        normalized_email = self._normalize_email(email)
        existing = self.get_user_by_email(normalized_email)
        if existing is not None:
            raise ValueError("An account with that email already exists.")

        record = {
            "user_id": uuid4().hex,
            "name": name.strip(),
            "email": email.strip(),
            "email_lower": normalized_email,
            "password_hash": _PWD_CONTEXT.hash(password),
        }

        with self._connect() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        sql.SQL(
                            """
                            INSERT INTO {}.{}
                            (user_id, name, email, email_lower, password_hash, created_at, updated_at)
                            VALUES (%(user_id)s, %(name)s, %(email)s, %(email_lower)s, %(password_hash)s, NOW(), NOW());
                            """
                        ).format(sql.Identifier(self.schema), sql.Identifier(self.table)),
                        record,
                    )
                except errors.UniqueViolation as exc:
                    raise ValueError("An account with that email already exists.") from exc

        saved = self.get_user_by_email(normalized_email)
        if saved is None:
            raise RuntimeError("Failed to create user.")
        return self._public_user(saved)

    def authenticate_user(self, email: str, password: str) -> dict[str, Any] | None:
        user = self.get_user_by_email(email)
        if user is None:
            return None
        if not _PWD_CONTEXT.verify(password, user["password_hash"]):
            return None
        return self._public_user(user)

    def create_session(self, user_id: str) -> str:
        """Issue a new opaque bearer token for ``user_id`` and persist it."""
        self._ensure_schema()
        token = secrets.token_urlsafe(32)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "INSERT INTO {}.{} (token, user_id, created_at) VALUES (%s, %s, NOW());"
                    ).format(sql.Identifier(self.schema), sql.Identifier(self.sessions_table)),
                    (token, user_id),
                )
        return token

    def get_user_by_token(self, token: str) -> dict[str, Any] | None:
        """Resolve a bearer token to the public user record it belongs to, if valid."""
        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        """
                        SELECT u.* FROM {schema}.{users} u
                        JOIN {schema}.{sessions} s ON s.user_id = u.user_id
                        WHERE s.token = %s;
                        """
                    ).format(
                        schema=sql.Identifier(self.schema),
                        users=sql.Identifier(self.table),
                        sessions=sql.Identifier(self.sessions_table),
                    ),
                    (token,),
                )
                row = cur.fetchone()
        return self._public_user(row) if row else None

    def delete_session(self, token: str) -> None:
        """Invalidate a bearer token (logout). No-op if it doesn't exist."""
        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("DELETE FROM {}.{} WHERE token = %s;").format(
                        sql.Identifier(self.schema), sql.Identifier(self.sessions_table)
                    ),
                    (token,),
                )