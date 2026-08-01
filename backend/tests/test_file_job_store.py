import tempfile
import unittest
from pathlib import Path

from api.services.file_store import FileJobStore
from api.services.job_manager import JobManager


class TestFileJobStore(unittest.TestCase):
    def test_job_manager_reloads_persisted_job(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "analysis_jobs.json"

            manager = JobManager(FileJobStore(store_path))
            job = manager.create_job(filename="sample.csv")
            manager.set_result(job.job_id, state={"foo": "bar"}, errors=[], result={"answer": "ok"})
            manager.add_chat_messages(job.job_id, [{"role": "user", "content": "hello"}])

            reloaded = JobManager(FileJobStore(store_path))
            stored = reloaded.get_job(job.job_id)

            self.assertIsNotNone(stored)
            self.assertEqual(stored.result["answer"], "ok")
            self.assertEqual(stored.chat_history[0]["content"], "hello")


if __name__ == "__main__":
    unittest.main()