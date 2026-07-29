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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Job:
    """A single background analysis job."""

    job_id: str
    filename: str | None = None
    csv_path: str | None = None
    status: str = "queued"  # queued | processing | completed | failed
    progress: dict[str, str] = field(default_factory=dict)  # agent -> status
    events: list[dict[str, Any]] = field(default_factory=list)  # append-only log
    state: dict[str, Any] | None = None  # final GraphState (post-run)
    errors: list[str] = field(default_factory=list)
    error: str | None = None  # fatal error message, if any
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    finished: bool = False

    # Concurrency primitive shared with subscribers so SSE can wake promptly.
    condition: threading.Condition = field(default_factory=threading.Condition, repr=False)


class JobManager:
    """Thread-safe registry of jobs."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def create_job(self, filename: str | None = None, csv_path: str | None = None) -> Job:
        job_id = uuid.uuid4().hex
        job = Job(job_id=job_id, filename=filename, csv_path=csv_path)
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self) -> list[Job]:
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

    def set_result(self, job_id: str, state: dict[str, Any], errors: list[str]) -> None:
        job = self.get_job(job_id)
        if job is None:
            return
        with job.condition:
            job.state = state
            job.errors = errors or []
            job.status = "completed"
            job.updated_at = _utcnow()
            job.condition.notify_all()

    def fail(self, job_id: str, message: str) -> None:
        job = self.get_job(job_id)
        if job is None:
            return
        with job.condition:
            job.error = message
            job.status = "failed"
            job.updated_at = _utcnow()
            job.condition.notify_all()

    def mark_finished(self, job_id: str) -> None:
        """Signal that no further events will be produced for this job."""
        job = self.get_job(job_id)
        if job is None:
            return
        with job.condition:
            job.finished = True
            job.updated_at = _utcnow()
            job.condition.notify_all()


# Process-wide singleton used via dependency injection.
_job_manager: JobManager | None = None


def get_job_manager() -> JobManager:
    """FastAPI dependency returning the shared JobManager singleton."""
    global _job_manager
    if _job_manager is None:
        _job_manager = JobManager()
    return _job_manager
