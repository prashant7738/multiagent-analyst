import unittest

from api.services.job_manager import JobManager
from api.services.result_builder import build_result


class TestAnalysisConfigPropagation(unittest.TestCase):
    def test_job_manager_persists_analysis_config(self):
        manager = JobManager()
        job = manager.create_job(
            filename="sample.csv",
            analysis_config={
                "preprocessing_profile": "strict",
                "preprocessing_config": {"knn_imputer_neighbors": 7},
            },
        )

        stored = manager.get_job(job.job_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.analysis_config["preprocessing_profile"], "strict")
        self.assertEqual(stored.analysis_config["preprocessing_config"]["knn_imputer_neighbors"], 7)

    def test_result_builder_surfaces_analysis_config(self):
        state = {
            "analysis_config": {
                "preprocessing_profile": "balanced",
                "preprocessing_config": {"currency_max_abs_value": 42},
            },
            "preprocessing_profile": "balanced",
            "raw_profile": {"shape": {"rows": 12, "cols": 4}},
            "schema_blueprint": {"amount": {"semantic_tag": "currency"}},
            "data_quality": {"overall_quality_score": 91.5},
            "stats": {},
            "validation_report": {},
            "reliability": {},
            "insight_narrative": {},
            "errors": [],
        }

        result = build_result("job-1", state, "sample.csv")

        self.assertEqual(result["summary"]["preprocessing_profile"], "balanced")
        self.assertEqual(result["summary"]["analysis_config"]["preprocessing_config"]["currency_max_abs_value"], 42)
        self.assertEqual(result["analysis_config"]["preprocessing_profile"], "balanced")


if __name__ == "__main__":
    unittest.main()