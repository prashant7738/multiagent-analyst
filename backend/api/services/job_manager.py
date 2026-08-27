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
    user_id: str | None = None  # owner — None for jobs created before per-user scoping
    filename: str | None = None
    csv_path: str | None = None
    analysis_config: dict[str, Any] = field(default_factory=dict)
    status: str = "queued"  # queued | processing | completed | failed
    progress: dict[str, str] = field(default_factory=dict)  # agent -> status
    events: list[dict[str, Any]] = field(default_factory=list)  # append-only log
    state: dict[str, Any] | None = None  # final GraphState (post-run)
    result: dict[str, Any] | None = None  # frontend-friendly analysis result
    chat_history: list[dict[str, Any]] = field(default_factory=list)  # dataset Q&A transcript
    rag_status: str = "not_built"  # not_built | building | ready | failed — RAG embedding index for chat
    rag_error: str | None = None
    rag_built_at: datetime | None = None
    rag_sample_info: dict[str, Any] = field(default_factory=dict)  # {total_rows, sampled_rows} for the row index
    rag_progress: dict[str, Any] = field(default_factory=dict)  # {phase, embedded, total} live build progress
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
            "user_id": self.user_id,
            "filename": self.filename,
            "csv_path": self.csv_path,
            "analysis_config": json_safe(self.analysis_config),
            "status": self.status,
            "progress": json_safe(self.progress),
            "events": json_safe(self.events),
            "state": json_safe(self.state),
            "result": json_safe(self.result),
            "chat_history": json_safe(self.chat_history),
            "rag_status": self.rag_status,
            "rag_error": self.rag_error,
            "rag_built_at": self.rag_built_at,
            "rag_sample_info": json_safe(self.rag_sample_info),
            "rag_progress": json_safe(self.rag_progress),
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
            user_id=record.get("user_id"),
            filename=record.get("filename"),
            csv_path=record.get("csv_path"),
            analysis_config=dict(record.get("analysis_config") or {}),
            status=str(record.get("status", "queued")),
            progress=dict(record.get("progress") or {}),
            events=list(record.get("events") or []),
            state=record.get("state"),
            result=record.get("result"),
            chat_history=list(record.get("chat_history") or []),
            rag_status=str(record.get("rag_status") or "not_built"),
            rag_error=record.get("rag_error"),
            rag_built_at=_parse_dt(record["rag_built_at"]) if record.get("rag_built_at") else None,
            rag_sample_info=dict(record.get("rag_sample_info") or {}),
            rag_progress=dict(record.get("rag_progress") or {}),
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
        user_id: str | None = None,
    ) -> Job:
        job_id = uuid.uuid4().hex
        job = Job(
            job_id=job_id,
            user_id=user_id,
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

    def list_jobs(self, user_id: str | None = None) -> list[Job]:
        """List jobs, optionally scoped to one owner.

        ``user_id=None`` returns every job (used internally, e.g. cache warmup);
        route handlers should always pass the authenticated caller's id.
        """
        if self._store is not None:
            for job_data in self._store.list_jobs():
                job = Job.from_record(job_data)
                with self._lock:
                    self._jobs[job.job_id] = job
        with self._lock:
            jobs = list(self._jobs.values())
        if user_id is not None:
            jobs = [job for job in jobs if job.user_id == user_id]
        return jobs

    def delete_job(self, job_id: str) -> bool:
        """Forget a job entirely — memory and persistent store.

        Returns True if the job was known. On-disk artifacts (uploads, charts,
        reports) are cleaned up separately by the route layer.
        """
        with self._lock:
            existed = self._jobs.pop(job_id, None) is not None
        if self._store is not None and self._store.delete_job(job_id):
            existed = True
        return existed

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

    def try_begin_rag_build(self, job_id: str) -> bool:
        """Atomically claim the "building" state. Returns False if a build is already in flight."""
        job = self.get_job(job_id)
        if job is None:
            return False
        if self._store is not None and hasattr(self._store, "claim_rag_build"):
            record = self._store.claim_rag_build(job_id)
            if record is None:
                return False
            claimed_job = Job.from_record(record)
            with self._lock:
                self._jobs[job_id] = claimed_job
            return True
        with job.condition:
            if job.rag_status in {"building", "ready"}:
                return False
            job.rag_status = "building"
            job.rag_error = None
            job.rag_progress = {"phase": "preparing", "embedded": 0, "total": 0}
            job.updated_at = _utcnow()
            job.condition.notify_all()
        self._persist(job)
        return True

    def maybe_expire_rag_build(self, job_id: str, timeout_seconds: int | None = None) -> bool:
        """Reset a RAG build that's been stuck in "building" with no progress.

        ``try_begin_rag_build`` only lets one build run at a time, so a build
        whose thread died (host spun down mid-run, process killed) would leave
        ``rag_status="building"`` forever and block every retry. Every progress
        update bumps ``updated_at``; if it hasn't moved for ``timeout_seconds``
        the build is presumed dead and flipped to "failed" so the next
        ``start_rag_build`` can claim it. Returns True when a build was reaped.
        """
        if timeout_seconds is None:
            timeout_seconds = get_settings().rag_build_timeout_seconds
        job = self.get_job(job_id)
        if job is None or job.rag_status != "building":
            return False
        age = (_utcnow() - job.updated_at).total_seconds()
        if age < timeout_seconds:
            return False
        self.set_rag_status(
            job_id, "failed",
            error=f"index build timed out after {int(age)}s with no progress",
        )
        return True

    def set_rag_progress(
        self,
        job_id: str,
        phase: str,
        embedded: int | None = None,
        total: int | None = None,
    ) -> None:
        """Publish live RAG build progress (counter updates only — never partial inserts)."""
        job = self.get_job(job_id)
        if job is None:
            return
        with job.condition:
            current = job.rag_progress or {}
            job.rag_progress = {
                "phase": phase,
                "embedded": current.get("embedded", 0) if embedded is None else embedded,
                "total": current.get("total", 0) if total is None else total,
            }
            job.updated_at = _utcnow()
            job.condition.notify_all()
        self._persist(job)

    def set_rag_status(
        self,
        job_id: str,
        status: str,
        error: str | None = None,
        sample_info: dict[str, Any] | None = None,
    ) -> None:
        job = self.get_job(job_id)
        if job is None:
            return
        with job.condition:
            job.rag_status = status
            job.rag_error = error
            if sample_info is not None:
                job.rag_sample_info = sample_info
            if status == "ready":
                job.rag_built_at = _utcnow()
                progress = dict(job.rag_progress or {})
                job.rag_progress = {
                    "phase": "complete",
                    "embedded": progress.get("total", 0),
                    "total": progress.get("total", 0),
                }
            elif status == "failed":
                progress = dict(job.rag_progress or {})
                job.rag_progress = {
                    "phase": "failed",
                    "embedded": progress.get("embedded", 0),
                    "total": progress.get("total", 0),
                }
            job.updated_at = _utcnow()
            job.condition.notify_all()
        self._persist(job)


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
