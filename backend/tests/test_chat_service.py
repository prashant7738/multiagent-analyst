import unittest

import pandas as pd

from api.services import chat_service
from api.services.job_manager import Job, JobManager


class TestChatServiceFacts(unittest.TestCase):
    def test_build_dataset_context_condenses_result(self):
        result = {
            "summary": {"filename": "sample.csv", "rows": 100, "columns": 5, "quality_score": 88.0},
            "schema_blueprint": {"revenue": {"semantic_tag": "currency", "intended_type": "float"}},
            "stats": {
                "chart_plan": {"dataset_type": "sales"},
                "correlation": {"strong_pairs": [{"col1": "a", "col2": "b", "pearson_r": 0.9,
                                                    "direction": "positive", "strength": "strong"}]},
                "regression": {"revenue": {"significant": True, "trend": "increasing", "r_squared": 0.8}},
            },
            "insight_narrative": {"executive_summary": "Solid dataset.", "key_findings": ["finding 1"]},
            "charts": [{"name": "chart1.png", "url": "/plots/chart1.png"}],
            "validation": {"passed": True},
            "reliability": {"overall_confidence": 0.9},
        }

        context = chat_service.build_dataset_context(result)

        self.assertEqual(context["dataset"]["rows"], 100)
        self.assertIn("revenue", context["available_columns"])
        self.assertEqual(len(context["strong_correlations"]), 1)
        self.assertIn("revenue", context["significant_trends"])
        self.assertEqual(context["existing_charts"], ["chart1.png"])
        self.assertEqual(context["executive_summary"], "Solid dataset.")

    def test_fallback_answer_uses_correlation_facts(self):
        context = {
            "dataset": {"rows": 10, "columns": 3, "quality_score": 90},
            "strong_correlations": [
                {"col1": "price", "col2": "sales", "pearson_r": 0.87, "direction": "positive", "strength": "strong"}
            ],
        }
        outcome = chat_service._fallback_answer(context, "What columns are correlated?")

        self.assertIn("price", outcome["answer"])
        self.assertFalse(outcome["needs_new_chart"])
        self.assertEqual(outcome["source"], "fallback")

    def test_fallback_answer_default_uses_executive_summary(self):
        context = {"dataset": {"rows": 5, "columns": 2}, "executive_summary": "It's fine."}
        outcome = chat_service._fallback_answer(context, "Tell me something interesting")
        self.assertEqual(outcome["answer"], "It's fine.")

    def test_anomaly_question_uses_anomaly_facts(self):
        context = {
            "dataset": {"rows": 10, "columns": 3, "quality_score": 90},
            "anomaly_summary": {"unique_flagged_rows": 4, "unique_flagged_row_pct": 40.0, "flagged_columns": 2},
        }
        outcome = chat_service._answer_anomaly_question(context, "is there any anomaly that i should worry about?")

        self.assertIsNotNone(outcome)
        self.assertIn("4 unusual rows", outcome["answer"])

    def test_highest_revenue_question_uses_rankings(self):
        context = {
            "dataset": {"rows": 10, "columns": 3, "quality_score": 90},
            "top_bottom_rankings": {
                "region": {
                    "top": [{"region": "North", "revenue_share_pct": 52.3}],
                    "bottom": [{"region": "West", "revenue_share_pct": 4.1}],
                }
            },
        }
        outcome = chat_service._answer_ranking_question(context, "what do i do for highest revenue?")

        self.assertIsNotNone(outcome)
        self.assertIn("North", outcome["answer"])
        self.assertIn("52.3%", outcome["answer"])


class TestChartRequestRendering(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame({
            "region": ["North", "South", "North", "East", "South", "West"],
            "revenue": [100.0, 200.0, 150.0, 80.0, 220.0, 90.0],
        })
        self.schema = {
            "region": {"analysis_allowed": True},
            "revenue": {"analysis_allowed": True},
        }

    def test_bar_chart_renders_successfully(self):
        ok, path = chat_service.render_chart_request(
            self.df, self.schema,
            {"chart_type": "bar", "x_column": "region", "y_column": "revenue",
             "aggregation": "sum", "title": "Revenue by Region"},
            job_id="testjob123",
        )
        self.assertTrue(ok)
        self.assertTrue(path.endswith(".png"))

    def test_invalid_column_is_rejected(self):
        ok, reason = chat_service.render_chart_request(
            self.df, self.schema,
            {"chart_type": "bar", "x_column": "nonexistent", "y_column": "revenue"},
            job_id="testjob123",
        )
        self.assertFalse(ok)
        self.assertIn("nonexistent", reason)

    def test_disallowed_column_is_rejected(self):
        schema = {"region": {"analysis_allowed": False}, "revenue": {"analysis_allowed": True}}
        ok, reason = chat_service.render_chart_request(
            self.df, schema,
            {"chart_type": "bar", "x_column": "region", "y_column": "revenue"},
            job_id="testjob123",
        )
        self.assertFalse(ok)

    def test_unsupported_chart_type_is_rejected(self):
        ok, reason = chat_service.render_chart_request(
            self.df, self.schema,
            {"chart_type": "pie", "x_column": "region", "y_column": "revenue"},
            job_id="testjob123",
        )
        self.assertFalse(ok)
        self.assertIn("unsupported", reason)

    def test_histogram_requires_numeric_column(self):
        ok, reason = chat_service.render_chart_request(
            self.df, self.schema,
            {"chart_type": "histogram", "x_column": "region"},
            job_id="testjob123",
        )
        self.assertFalse(ok)


class TestJobManagerChatHistory(unittest.TestCase):
    def test_add_and_get_chat_messages(self):
        manager = JobManager()
        job = manager.create_job(filename="sample.csv")

        manager.add_chat_messages(job.job_id, [
            {"role": "user", "content": "What's the top region?"},
            {"role": "assistant", "content": "North leads with 40% share.", "chart": None},
        ])

        history = manager.get_chat_history(job.job_id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[1]["content"], "North leads with 40% share.")
        self.assertIn("ts", history[0])

    def test_chat_history_round_trips_through_record(self):
        job = Job(job_id="abc", chat_history=[{"role": "user", "content": "hi"}])
        record = job.to_record()
        restored = Job.from_record(record)
        self.assertEqual(restored.chat_history, [{"role": "user", "content": "hi"}])


if __name__ == "__main__":
    unittest.main()
