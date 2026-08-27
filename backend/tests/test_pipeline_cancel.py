"""Cooperative cancellation of a running analysis job."""

import unittest
from unittest.mock import patch

from api.services import pipeline_runner
from api.services.job_manager import Job, JobManager


class TestJobManagerCancel(unittest.TestCase):
    def setUp(self):
        self.manager = JobManager()

    def _job(self, status="processing", finished=False):
        job = Job(job_id="j1", user_id="u1", status=status, finished=finished)
        self.manager._jobs[job.job_id] = job
        return job

    def test_request_cancel_sets_flag_on_running_job(self):
        self._job(status="processing")
        self.assertTrue(self.manager.request_cancel("j1"))
        self.assertTrue(self.manager.is_cancel_requested("j1"))

    def test_request_cancel_rejected_when_finished(self):
        self._job(status="completed", finished=True)
        self.assertFalse(self.manager.request_cancel("j1"))
        self.assertFalse(self.manager.is_cancel_requested("j1"))

    def test_request_cancel_rejected_for_unknown_job(self):
        self.assertFalse(self.manager.request_cancel("nope"))

    def test_set_cancelled_is_terminal(self):
        self._job()
        self.manager.set_cancelled("j1")
        self.assertEqual(self.manager.get_job("j1").status, "cancelled")

    def test_cancel_flag_round_trips_through_record(self):
        job = Job(job_id="rt", cancel_requested=True)
        restored = Job.from_record(job.to_record())
        self.assertTrue(restored.cancel_requested)


class _FakePipeline:
    """Yields one state snapshot per agent; the runner checks cancel between them."""

    def __init__(self, snapshots):
        self._snapshots = snapshots

    def stream(self, _state, stream_mode="values"):
        yield from self._snapshots


class TestRunnerStopsOnCancel(unittest.TestCase):
    def test_pipeline_halts_and_marks_cancelled_after_current_agent(self):
        manager = JobManager()
        job = Job(job_id="run1", user_id="u1", filename="x.csv", status="processing")
        manager._jobs[job.job_id] = job

        seen = []
        snapshots = [
            {"raw_profile": {"shape": {}}},                       # agent 1 done
            {"raw_profile": {"shape": {}}, "schema_blueprint": {"c": {}}},  # agent 2 done -> cancel here
            {"cleaned_df": object()},                             # agent 3 (should NOT be reached)
        ]

        real_is_cancel = manager.is_cancel_requested

        def spy(job_id):
            seen.append(job_id)
            # request cancel right after the 2nd snapshot has been observed
            if len(seen) == 2:
                manager.request_cancel("run1")
            return real_is_cancel(job_id)

        with patch.object(pipeline_runner, "_get_pipeline", return_value=_FakePipeline(snapshots)), \
             patch.object(manager, "is_cancel_requested", side_effect=spy):
            pipeline_runner._run(manager, "run1", "x.csv")

        final = manager.get_job("run1")
        self.assertEqual(final.status, "cancelled")
        self.assertTrue(final.finished)
        events = [e.get("event") for e in final.events]
        self.assertIn("pipeline_cancelled", events)
        self.assertNotIn("completed", events)
        # Agent 3's "running" milestone must never have been emitted.
        self.assertNotIn("Agent 3", [e.get("agent") for e in final.events if e.get("status") == "running"])


if __name__ == "__main__":
    unittest.main()
