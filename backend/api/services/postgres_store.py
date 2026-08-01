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
                            errors JSONB NOT NULL DEFAULT '[]'::jsonb,
                            error TEXT,
                            created_at TIMESTAMPTZ NOT NULL,
                            updated_at TIMESTAMPTZ NOT NULL,
                            finished BOOLEAN NOT NULL DEFAULT FALSE
                        );
                        """
                    ).format(sql.Identifier(self.schema), sql.Identifier(self.table))
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
            "errors": Jsonb(json_safe(record.get("errors") or [])),
        }

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        """
                        INSERT INTO {}.{}
                        (job_id, filename, csv_path, status, progress, events, state, result, errors, error, created_at, updated_at, finished)
                        VALUES (%(job_id)s, %(filename)s, %(csv_path)s, %(status)s, %(progress)s, %(events)s, %(state)s, %(result)s, %(errors)s, %(error)s, %(created_at)s, %(updated_at)s, %(finished)s)
                        ON CONFLICT (job_id) DO UPDATE SET
                            filename = EXCLUDED.filename,
                            csv_path = EXCLUDED.csv_path,
                            status = EXCLUDED.status,
                            progress = EXCLUDED.progress,
                            events = EXCLUDED.events,
                            state = EXCLUDED.state,
                            result = EXCLUDED.result,
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