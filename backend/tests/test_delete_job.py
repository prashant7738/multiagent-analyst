import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from api.app import app
from api.routes import jobs as jobs_routes
from api.routes.jobs import _delete_artifacts
from api.services.file_store import FileJobStore
from api.services.job_manager import Job, JobManager


class TestDeleteJob(unittest.TestCase):
    def test_file_store_delete_removes_record(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "analysis_jobs.json"
            store = FileJobStore(store_path)

            record = {"job_id": "job-1", "status": "completed"}
            store.save_job(record)
            self.assertTrue(store.delete_job("job-1"))
            self.assertFalse(store.delete_job("job-1"))
            self.assertIsNone(store.get_job("job-1"))

            reloaded = FileJobStore(store_path)
            self.assertIsNone(reloaded.get_job("job-1"))

    def test_manager_delete_forgets_memory_and_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = JobManager(FileJobStore(Path(tmpdir) / "analysis_jobs.json"))
            job = manager.create_job(filename="sample.csv")
            manager.set_result(job.job_id, state={}, errors=[], result={"ok": True})

            self.assertTrue(manager.delete_job(job.job_id))
            self.assertIsNone(manager.get_job(job.job_id))

            reloaded = JobManager(FileJobStore(Path(tmpdir) / "analysis_jobs.json"))
            self.assertEqual(reloaded.list_jobs(), [])

    def test_manager_delete_unknown_job_returns_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = JobManager(FileJobStore(Path(tmpdir) / "analysis_jobs.json"))
            self.assertFalse(manager.delete_job("does-not-exist"))

    def test_delete_artifacts_removes_upload_charts_reports(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            uploads = root / "uploads"
            charts = root / "outputs" / "charts"
            reports = root / "outputs" / "reports"
            for directory in (uploads, charts, reports):
                directory.mkdir(parents=True)

            upload = uploads / "job-abc.csv"
            upload.write_text("a,b\n1,2\n", encoding="utf-8")
            chart_dir = charts / "job-abc"
            chart_dir.mkdir()
            (chart_dir / "trend.png").write_bytes(b"png")
            chat_chart = charts / "chat_job-abc_1234abcd.png"
            chat_chart.write_bytes(b"png")
            report_dir = reports / "job-abc"
            report_dir.mkdir()
            (report_dir / "report.pdf").write_bytes(b"%PDF")

            settings = SimpleNamespace(uploads_dir=uploads, charts_dir=charts, reports_dir=reports)
            _delete_artifacts(Job(job_id="job-abc"), settings)

            self.assertFalse(upload.exists())
            self.assertFalse(chart_dir.exists())
            self.assertFalse(chat_chart.exists())
            self.assertFalse(report_dir.exists())
            # Unrelated artifacts survive.
            other = charts / "chat_otherjob_deadbeef.png"
            other.write_bytes(b"png")
            self.assertTrue(other.exists())

    def test_delete_all_removes_finished_and_skips_running(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            manager = JobManager(FileJobStore(tmp / "analysis_jobs.json"))

            done = manager.create_job(filename="a.csv")
            manager.set_result(done.job_id, state={}, errors=[], result={})
            failed = manager.create_job(filename="b.csv")
            manager.fail(failed.job_id, "boom")
            running = manager.create_job(filename="c.csv")
            manager.set_status(running.job_id, "processing")

            root = tmp / "fs"
            for sub in ("uploads", "charts", "reports"):
                (root / sub).mkdir(parents=True)
            settings = SimpleNamespace(
                uploads_dir=root / "uploads",
                charts_dir=root / "charts",
                reports_dir=root / "reports",
            )

            app.dependency_overrides[jobs_routes.get_job_manager] = lambda: manager
            app.dependency_overrides[jobs_routes.get_settings] = lambda: settings
            try:
                client = TestClient(app)
                resp = client.delete("/api/jobs")

                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.json(), {"deleted": 2, "skipped": 1})

                remaining = {job.job_id: job.status for job in manager.list_jobs()}
                self.assertEqual(remaining, {running.job_id: "processing"})

                reloaded = JobManager(FileJobStore(tmp / "analysis_jobs.json"))
                self.assertEqual(len(reloaded.list_jobs()), 1)
            finally:
                app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
