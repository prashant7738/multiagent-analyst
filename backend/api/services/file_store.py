"""Simple JSON-file persistence for analysis jobs.

This is the default fallback when PostgreSQL is not configured. It keeps the
job registry durable across backend restarts so completed analyses can still be
looked up by the chat endpoint.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from threading import Lock
from typing import Any


class FileJobStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._jobs = {}
            return

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self._jobs = {}
            return

        if isinstance(raw, list):
            self._jobs = {
                str(record.get("job_id")): record
                for record in raw
                if isinstance(record, dict) and record.get("job_id")
            }
        elif isinstance(raw, dict):
            self._jobs = {
                str(job_id): record
                for job_id, record in raw.items()
                if isinstance(record, dict)
            }
        else:
            self._jobs = {}

    def _flush(self) -> None:
        payload = list(self._jobs.values())
        tmp_fd, tmp_name = tempfile.mkstemp(prefix=self.path.stem + "_", suffix=".tmp", dir=str(self.path.parent))
        try:
            with open(tmp_fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
            Path(tmp_name).replace(self.path)
        finally:
            Path(tmp_name).unlink(missing_ok=True)

    def save_job(self, record: dict[str, Any]) -> None:
        job_id = str(record.get("job_id") or "")
        if not job_id:
            return
        with self._lock:
            self._jobs[job_id] = dict(record)
            self._flush()

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._jobs.get(job_id)
            return dict(record) if record is not None else None

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(record) for record in self._jobs.values()]

    def delete_job(self, job_id: str) -> bool:
        """Remove a job record. Returns True if it existed."""
        with self._lock:
            if self._jobs.pop(job_id, None) is None:
                return False
            self._flush()
        return True