import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from api.routes import reports as reports_routes
from api.services.job_manager import Job


class TestReportDownload(unittest.IsolatedAsyncioTestCase):
    async def test_html_request_uses_html_sibling_when_job_stores_pdf(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            pdf_path = report_dir / "insight_report.pdf"
            html_path = report_dir / "insight_report.html"
            pdf_path.write_bytes(b"%PDF-1.7 binary content")
            html_path.write_text("<html><body>report</body></html>", encoding="utf-8")

            job = Job(job_id="job-123456", state={"report_path": str(pdf_path)})
            settings = SimpleNamespace(backend_dir=report_dir)
            manager = SimpleNamespace(get_job=lambda job_id: job if job_id == job.job_id else None)

            response = await reports_routes.download_report(
                job.job_id,
                format="html",
                settings=settings,
                manager=manager,
            )

            self.assertEqual(response.media_type, "text/html")
            self.assertEqual(Path(response.path), html_path)


if __name__ == "__main__":
    unittest.main()
