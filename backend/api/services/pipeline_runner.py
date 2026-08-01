"""Background pipeline runner.

Drives the *existing* compiled LangGraph pipeline via ``.stream()`` and turns
each observed state transition into a Server-Sent-Event on the job's event log.
It does not modify any agent or the pipeline graph — it only observes progress
and stores the final state.

The pipeline is CPU/IO heavy and fully synchronous, so it runs in a dedicated
daemon thread. All cross-thread communication goes through the thread-safe
``JobManager`` (event log + condition variable), keeping the asyncio event loop
free to serve SSE and other requests.
"""

from __future__ import annotations

import logging
import threading
import traceback
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

# Importing config first bootstraps sys.path + cwd so the pipeline/agents import.
from api.config import get_settings
from api.services.job_manager import JobManager
from api.services.result_builder import build_result

logger = logging.getLogger("api.pipeline_runner")

# Friendly agent labels streamed to the frontend.
_AGENT_LABELS = {
    "agent1": "Agent 1",
    "agent2": "Agent 2",
    "agent3": "Agent 3",
    "agent4": "Agent 4",
    "agent5": "Agent 5",
    "agent6": "Agent 6",
}


@lru_cache(maxsize=1)
def _get_pipeline():
    """Build & cache the compiled LangGraph pipeline once per process."""
    # Imported lazily so api.config path bootstrap runs beforehand.
    from pipeline import build_pipeline  # type: ignore

    logger.info("Compiling LangGraph pipeline (one-time).")
    return build_pipeline()


def _initial_state(csv_path: str) -> dict[str, Any]:
    """Construct the GraphState seed exactly as pipeline.py does."""
    return {
        "csv_path": csv_path,
        "raw_profile": {},
        "schema_blueprint": {},
        "_df_cache": None,
        "cleaned_df": None,
        "cleaned_csv_path": "",
        "scaling_params": {},
        "preprocessing_log": [],
        "preprocessing_config": {},
        "preprocessing_profile": "",
        "dataset_domain": "",
        "data_quality": {},
        "column_ledger": {},
        "stats": {},
        "chart_paths": [],
        "validation_report": {},
        "insight_facts": {},
        "insight_narrative": {},
        "report_path": "",
        "errors": [],
        "reliability": {},
    }


class _MilestoneEmitter:
    """Translate observed GraphState transitions into ordered SSE events.

    Because ``pipeline.stream(stream_mode="values")`` yields the full state after
    each node, milestones are detected by field-presence. Each milestone is
    emitted at most once, and the *next* agent's "running" event is emitted right
    after the previous agent completes.
    """

    def __init__(self, manager: JobManager, job_id: str) -> None:
        self.manager = manager
        self.job_id = job_id
        self._done: set[str] = set()

    def _emit(self, event: str, **payload: Any) -> None:
        self.manager.append_event(self.job_id, {"event": event, **payload})

    def _once(self, key: str) -> bool:
        if key in self._done:
            return False
        self._done.add(key)
        return True

    def agent_running(self, node: str) -> None:
        if self._once(f"{node}:running"):
            self._emit("progress", agent=_AGENT_LABELS[node], status="running",
                       message=f"{_AGENT_LABELS[node]} started")

    def agent_completed(self, node: str) -> None:
        if self._once(f"{node}:completed"):
            self._emit("progress", agent=_AGENT_LABELS[node], status="completed",
                       message=f"{_AGENT_LABELS[node]} completed")

    def observe(self, state: dict[str, Any]) -> None:
        """Inspect a state snapshot and emit any newly-reached milestones."""
        # Agent 1 — structural profiling
        if state.get("raw_profile"):
            self.agent_completed("agent1")
            self.agent_running("agent2")
        # Agent 2 — semantic understanding
        if state.get("schema_blueprint") and len(state.get("schema_blueprint")):
            self.agent_completed("agent2")
            self.agent_running("agent3")
        # Agent 3 — preprocessing
        if state.get("cleaned_df") is not None:
            self.agent_completed("agent3")
            self.agent_running("agent4")
        # Agent 4 — statistics & visualization
        if state.get("stats"):
            self.agent_completed("agent4")
            if self._once("charts_generated"):
                self._emit("charts_generated", message="Charts generated",
                           detail={"count": len(state.get("chart_paths", []) or [])})
            self.agent_running("agent5")
        # Agent 5 — validation guardrail
        if state.get("validation_report"):
            self.agent_completed("agent5")
            report = state.get("validation_report", {}) or {}
            if self._once("validation_result"):
                if report.get("passed"):
                    self._emit("validation_passed", message="Validation passed",
                               detail={"score": report.get("overall_validation_score")})
                    self.agent_running("agent6")
                else:
                    self._emit("validation_failed", message="Validation failed",
                               detail={"score": report.get("overall_validation_score"),
                                       "issues": report.get("flagged_issues", [])})
        # Agent 6 — report generation
        if state.get("report_path"):
            self.agent_completed("agent6")
            if self._once("report_generated"):
                self._emit("report_generated", message="Report generated",
                           detail={"report_path": state.get("report_path")})


def _run(manager: JobManager, job_id: str, csv_path: str) -> None:
    """Blocking pipeline execution — intended to run inside a daemon thread."""
    emitter = _MilestoneEmitter(manager, job_id)
    try:
        manager.set_status(job_id, "processing")
        manager.append_event(job_id, {"event": "pipeline_started", "message": "Pipeline started"})
        manager.append_event(job_id, {"event": "csv_loaded", "message": "CSV loaded",
                                      "detail": {"csv_path": csv_path}})

        pipeline = _get_pipeline()
        emitter.agent_running("agent1")

        final_state: dict[str, Any] = _initial_state(csv_path)
        for snapshot in pipeline.stream(final_state, stream_mode="values"):
            final_state = snapshot
            emitter.observe(snapshot)

        # Stamp a report-generation timestamp for the frontend (non-mutating).
        if final_state.get("report_path"):
            final_state = {**final_state, "report_generated_at": datetime.now(timezone.utc).isoformat()}

        result = build_result(job_id, final_state, manager.get_job(job_id).filename if manager.get_job(job_id) else None)
        manager.set_result(job_id, final_state, final_state.get("errors", []) or [], result=result)

        pipeline_errors = final_state.get("errors", []) or []
        manager.append_event(job_id, {
            "event": "pipeline_finished",
            "message": "Pipeline finished",
            "detail": {
                "errors": pipeline_errors,
                "has_report": bool(final_state.get("report_path")),
                "result_ready": True,
            },
        })
        manager.append_event(job_id, {"event": "completed", "status": "done"})
        # Attach the built result to the job for the /result endpoint reuse.
        job = manager.get_job(job_id)
        if job is not None:
            job.state = final_state  # already set; keep for clarity
            job.result = result
        logger.info("Job %s completed (report=%s, errors=%d).",
                    job_id, bool(final_state.get("report_path")), len(pipeline_errors))

    except Exception as exc:  # noqa: BLE001 — never let a job crash the server
        tb = traceback.format_exc()
        logger.error("Job %s failed: %s\n%s", job_id, exc, tb)
        manager.fail(job_id, str(exc))
        manager.append_event(job_id, {
            "event": "pipeline_failed",
            "status": "failed",
            "message": str(exc),
            "detail": {"traceback": tb},
        })
    finally:
        manager.mark_finished(job_id)


def start_pipeline_job(manager: JobManager, job_id: str, csv_path: str) -> threading.Thread:
    """Launch the pipeline for ``job_id`` in a background daemon thread."""
    get_settings()  # ensure config/dirs are ready
    thread = threading.Thread(
        target=_run,
        args=(manager, job_id, csv_path),
        name=f"pipeline-{job_id[:8]}",
        daemon=True,
    )
    thread.start()
    return thread
