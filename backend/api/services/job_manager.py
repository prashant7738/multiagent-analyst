"""In-memory job manager.

Stores every analysis job, its lifecycle status, the final ``GraphState``, and
an append-only event log. The event log is the single source of truth for SSE:
subscribers replay past events, then follow new ones by index — this makes the
stream race-free (frontend can connect before or after the pipeline starts) and
safe for multiple concurrent subscribers.

The store is intentionally in-memory (a dict guarded by a lock). Swapping this
for Redis/DB later only requires reimplementing this class.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from api.config import get_settings
from api.utils.serialization import json_safe


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Job:
    """A single background analysis job."""

    job_id: str
    filename: str | None = None
    csv_path: str | None = None
    analysis_config: dict[str, Any] = field(default_factory=dict)
    status: str = "queued"  # queued | processing | completed | failed
    progress: dict[str, str] = field(default_factory=dict)  # agent -> status
    events: list[dict[str, Any]] = field(default_factory=list)  # append-only log
    state: dict[str, Any] | None = None  # final GraphState (post-run)
    result: dict[str, Any] | None = None  # frontend-friendly analysis result
    chat_history: list[dict[str, Any]] = field(default_factory=list)  # dataset Q&A transcript
    errors: list[str] = field(default_factory=list)
    error: str | None = None  # fatal error message, if any
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    finished: bool = False

    # Concurrency primitive shared with subscribers so SSE can wake promptly.
    condition: threading.Condition = field(default_factory=threading.Condition, repr=False)

    def to_record(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "filename": self.filename,
            "csv_path": self.csv_path,
            "analysis_config": json_safe(self.analysis_config),
            "status": self.status,
            "progress": json_safe(self.progress),
            "events": json_safe(self.events),
            "state": json_safe(self.state),
            "result": json_safe(self.result),
            "chat_history": json_safe(self.chat_history),
            "errors": json_safe(self.errors),
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "finished": self.finished,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "Job":
        def _parse_dt(value: Any) -> datetime:
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                return datetime.fromisoformat(value)
            return _utcnow()

        return cls(
            job_id=str(record.get("job_id")),
            filename=record.get("filename"),
            csv_path=record.get("csv_path"),
            analysis_config=dict(record.get("analysis_config") or {}),
            status=str(record.get("status", "queued")),
            progress=dict(record.get("progress") or {}),
            events=list(record.get("events") or []),
            state=record.get("state"),
            result=record.get("result"),
            chat_history=list(record.get("chat_history") or []),
            errors=list(record.get("errors") or []),
            error=record.get("error"),
            created_at=_parse_dt(record.get("created_at")),
            updated_at=_parse_dt(record.get("updated_at")),
            finished=bool(record.get("finished", False)),
        )


class JobManager:
    """Thread-safe registry of jobs."""

    def __init__(self, store: Any | None = None) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._store = store

        if self._store is not None:
            for job_data in self._store.list_jobs():
                job = Job.from_record(job_data)
                self._jobs[job.job_id] = job

    def _persist(self, job: Job) -> None:
        if self._store is not None:
            self._store.save_job(job.to_record())

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def create_job(
        self,
        filename: str | None = None,
        csv_path: str | None = None,
        analysis_config: dict[str, Any] | None = None,
    ) -> Job:
        job_id = uuid.uuid4().hex
        job = Job(
            job_id=job_id,
            filename=filename,
            csv_path=csv_path,
            analysis_config=dict(analysis_config or {}),
        )
        with self._lock:
            self._jobs[job_id] = job
        self._persist(job)
        return job

    def get_job(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None and self._store is not None:
            record = self._store.get_job(job_id)
            if record is not None:
                job = Job.from_record(record)
                with self._lock:
                    self._jobs[job_id] = job
        return job

    def list_jobs(self) -> list[Job]:
        if self._store is not None:
            for job_data in self._store.list_jobs():
                job = Job.from_record(job_data)
                with self._lock:
                    self._jobs[job.job_id] = job
        with self._lock:
            return list(self._jobs.values())

    # ------------------------------------------------------------------
    # Mutations (each notifies SSE subscribers via the job condition)
    # ------------------------------------------------------------------
    def set_status(self, job_id: str, status: str) -> None:
        job = self.get_job(job_id)
        if job is None:
            return
        with job.condition:
            job.status = status
            job.updated_at = _utcnow()
            job.condition.notify_all()
        self._persist(job)

    def append_event(self, job_id: str, event: dict[str, Any]) -> None:
        """Append an event to the job log and wake all SSE subscribers."""
        job = self.get_job(job_id)
        if job is None:
            return
        with job.condition:
            enriched = {"ts": _utcnow().isoformat(), **event}
            job.events.append(enriched)
            # Track per-agent progress for the polling/summary endpoints.
            agent = event.get("agent")
            agent_status = event.get("status")
            if agent and agent_status:
                job.progress[agent] = agent_status
            job.updated_at = _utcnow()
            job.condition.notify_all()
        self._persist(job)

    def set_result(
        self,
        job_id: str,
        state: dict[str, Any],
        errors: list[str],
        result: dict[str, Any] | None = None,
    ) -> None:
        job = self.get_job(job_id)
        if job is None:
            return
        with job.condition:
            job.state = state
            job.result = result
            job.errors = errors or []
            job.status = "completed"
            job.updated_at = _utcnow()
            job.condition.notify_all()
        self._persist(job)

    def fail(self, job_id: str, message: str) -> None:
        job = self.get_job(job_id)
        if job is None:
            return
        with job.condition:
            job.error = message
            job.status = "failed"
            job.updated_at = _utcnow()
            job.condition.notify_all()
        self._persist(job)

    def mark_finished(self, job_id: str) -> None:
        """Signal that no further events will be produced for this job."""
        job = self.get_job(job_id)
        if job is None:
            return
        with job.condition:
            job.finished = True
            job.updated_at = _utcnow()
            job.condition.notify_all()
        self._persist(job)

    def add_chat_messages(self, job_id: str, messages: list[dict[str, Any]]) -> Job | None:
        """Append one or more chat turns (user/assistant) to the job's transcript."""
        job = self.get_job(job_id)
        if job is None:
            return None
        with job.condition:
            for message in messages:
                job.chat_history.append({"ts": _utcnow().isoformat(), **message})
            job.updated_at = _utcnow()
        self._persist(job)
        return job

    def get_chat_history(self, job_id: str) -> list[dict[str, Any]]:
        job = self.get_job(job_id)
        if job is None:
            return []
        return list(job.chat_history)


# Process-wide singleton used via dependency injection.
_job_manager: JobManager | None = None


def get_job_manager() -> JobManager:
    """FastAPI dependency returning the shared JobManager singleton."""
    global _job_manager
    if _job_manager is None:
        settings = get_settings()
        store = None
        if settings.database_url:
            from api.services.postgres_store import PostgresJobStore

            store = PostgresJobStore(
                settings.database_url,
                schema=settings.postgres_schema,
                table=settings.postgres_jobs_table,
            )
        else:
            from api.services.file_store import FileJobStore

            store = FileJobStore(settings.outputs_dir / "analysis_jobs.json")
        _job_manager = JobManager(store)
    return _job_manager
