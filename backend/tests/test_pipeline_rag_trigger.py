import unittest
from types import SimpleNamespace
from unittest.mock import patch

from api.services.job_manager import Job, JobManager
from api.services.pipeline_runner import maybe_start_rag_build


class TestPipelineRagTrigger(unittest.TestCase):
    def test_completed_job_starts_rag_build_once(self):
        manager = JobManager()
        job = manager.create_job(filename="sample.csv", csv_path="/tmp/sample.csv")
        manager.set_result(job.job_id, state={}, errors=[], result={"summary": {}})

        settings = SimpleNamespace(database_url="postgres", hf_token="token")
        with patch("api.services.pipeline_runner.get_settings", return_value=settings), \
             patch("api.services.rag_service.start_rag_build", return_value=True) as start_build:
            started = maybe_start_rag_build(manager, job.job_id)

        self.assertTrue(started)
        start_build.assert_called_once()
        self.assertEqual(start_build.call_args.args[1].job_id, job.job_id)

    def test_ready_job_is_not_rebuilt(self):
        manager = JobManager()
        job = Job(job_id="ready-job", status="completed", result={"summary": {}}, rag_status="ready")
        manager._jobs[job.job_id] = job

        settings = SimpleNamespace(database_url="postgres", hf_token="token")
        with patch("api.services.pipeline_runner.get_settings", return_value=settings), \
             patch("api.services.rag_service.start_rag_build") as start_build:
            started = maybe_start_rag_build(manager, job.job_id)

        self.assertFalse(started)
        start_build.assert_not_called()


if __name__ == "__main__":
    unittest.main()
