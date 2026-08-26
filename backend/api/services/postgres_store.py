"""Optional PostgreSQL persistence for analysis jobs."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from api.utils.serialization import json_safe


class PostgresJobStore:
    def __init__(self, dsn: str, schema: str = "public", table: str = "analysis_jobs") -> None:
        self.dsn = dsn
        self.schema = schema
        self.table = table
        self._initialized = False

    @contextmanager
    def _connect(self) -> Iterator[psycopg.Connection]:
        with psycopg.connect(self.dsn, autocommit=True, row_factory=dict_row) as conn:
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
                            job_id TEXT PRIMARY KEY,
                            filename TEXT,
                            csv_path TEXT,
                            status TEXT NOT NULL,
                            progress JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            events JSONB NOT NULL DEFAULT '[]'::jsonb,
                            state JSONB,
                            result JSONB,
                            chat_history JSONB NOT NULL DEFAULT '[]'::jsonb,
                            rag_status TEXT NOT NULL DEFAULT 'not_built',
                            rag_error TEXT,
                            rag_built_at TIMESTAMPTZ,
                            rag_sample_info JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            rag_progress JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            errors JSONB NOT NULL DEFAULT '[]'::jsonb,
                            error TEXT,
                            created_at TIMESTAMPTZ NOT NULL,
                            updated_at TIMESTAMPTZ NOT NULL,
                            finished BOOLEAN NOT NULL DEFAULT FALSE
                        );
                        """
                    ).format(sql.Identifier(self.schema), sql.Identifier(self.table))
                )
                # Additive columns for installs whose table predates this feature.
                for column_def in (
                    "chat_history JSONB NOT NULL DEFAULT '[]'::jsonb",
                    "rag_status TEXT NOT NULL DEFAULT 'not_built'",
                    "rag_error TEXT",
                    "rag_built_at TIMESTAMPTZ",
                    "rag_sample_info JSONB NOT NULL DEFAULT '{{}}'::jsonb",
                    "rag_progress JSONB NOT NULL DEFAULT '{{}}'::jsonb",
                    "user_id TEXT",
                ):
                    cur.execute(
                        sql.SQL("ALTER TABLE {}.{} ADD COLUMN IF NOT EXISTS " + column_def + ";").format(
                            sql.Identifier(self.schema), sql.Identifier(self.table)
                        )
                    )
                cur.execute(
                    sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {}.{} (user_id);").format(
                        sql.Identifier(f"idx_{self.table}_user_id"),
                        sql.Identifier(self.schema),
                        sql.Identifier(self.table),
                    )
                )
        self._initialized = True

    def save_job(self, record: dict[str, Any]) -> None:
        self._ensure_schema()
        payload = {
            **record,
            "progress": Jsonb(json_safe(record.get("progress") or {})),
            "events": Jsonb(json_safe(record.get("events") or [])),
            "state": Jsonb(json_safe(record.get("state"))) if record.get("state") is not None else None,
            "result": Jsonb(json_safe(record.get("result"))) if record.get("result") is not None else None,
            "chat_history": Jsonb(json_safe(record.get("chat_history") or [])),
            "rag_sample_info": Jsonb(json_safe(record.get("rag_sample_info") or {})),
            "rag_progress": Jsonb(json_safe(record.get("rag_progress") or {})),
            "errors": Jsonb(json_safe(record.get("errors") or [])),
        }

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        """
                        INSERT INTO {}.{}
                        (job_id, user_id, filename, csv_path, status, progress, events, state, result, chat_history,
                         rag_status, rag_error, rag_built_at, rag_sample_info, rag_progress, errors, error, created_at, updated_at, finished)
                        VALUES (%(job_id)s, %(user_id)s, %(filename)s, %(csv_path)s, %(status)s, %(progress)s, %(events)s, %(state)s, %(result)s, %(chat_history)s,
                                %(rag_status)s, %(rag_error)s, %(rag_built_at)s, %(rag_sample_info)s, %(rag_progress)s, %(errors)s, %(error)s, %(created_at)s, %(updated_at)s, %(finished)s)
                        ON CONFLICT (job_id) DO UPDATE SET
                            user_id = EXCLUDED.user_id,
                            filename = EXCLUDED.filename,
                            csv_path = EXCLUDED.csv_path,
                            status = EXCLUDED.status,
                            progress = EXCLUDED.progress,
                            events = EXCLUDED.events,
                            state = EXCLUDED.state,
                            result = EXCLUDED.result,
                            chat_history = EXCLUDED.chat_history,
                            rag_status = EXCLUDED.rag_status,
                            rag_error = EXCLUDED.rag_error,
                            rag_built_at = EXCLUDED.rag_built_at,
                            rag_sample_info = EXCLUDED.rag_sample_info,
                            rag_progress = EXCLUDED.rag_progress,
                            errors = EXCLUDED.errors,
                            error = EXCLUDED.error,
                            created_at = EXCLUDED.created_at,
                            updated_at = EXCLUDED.updated_at,
                            finished = EXCLUDED.finished;
                        """
                    ).format(sql.Identifier(self.schema), sql.Identifier(self.table)),
                    payload,
                )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT * FROM {}.{} WHERE job_id = %s;").format(
                        sql.Identifier(self.schema), sql.Identifier(self.table)
                    ),
                    (job_id,),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def list_jobs(self) -> list[dict[str, Any]]:
        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT * FROM {}.{} ORDER BY created_at DESC;").format(
                        sql.Identifier(self.schema), sql.Identifier(self.table)
                    )
                )
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def delete_job(self, job_id: str) -> bool:
        """Remove a job record. Returns True if it existed."""
        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("DELETE FROM {}.{} WHERE job_id = %s;").format(
                        sql.Identifier(self.schema), sql.Identifier(self.table)
                    ),
                    (job_id,),
                )
                return cur.rowcount > 0

    def claim_rag_build(self, job_id: str) -> dict[str, Any] | None:
        """Atomically claim an eligible RAG build and return the new job record."""
        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        """
                        UPDATE {}.{}
                        SET rag_status = 'building', rag_error = NULL,
                            rag_progress = '{{"phase":"preparing","embedded":0,"total":0}}'::jsonb,
                            updated_at = now()
                        WHERE job_id = %s AND rag_status NOT IN ('building', 'ready')
                        RETURNING *;
                        """
                    ).format(sql.Identifier(self.schema), sql.Identifier(self.table)),
                    (job_id,),
                )
                row = cur.fetchone()
        return dict(row) if row else None