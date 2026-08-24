import unittest
from unittest.mock import patch

import pandas as pd

from api.services import chat_service
from api.services import rag_service
from api.services.job_manager import Job, JobManager


class TestChatServiceFacts(unittest.TestCase):
    def test_retrieve_always_includes_dataset_wide_insight_facts(self):
        class FakeCursor:
            def __init__(self):
                self.executed = []

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, query, params):
                self.executed.append(str(query))

            def fetchall(self):
                query = self.executed[-1]
                if "doc_type = 'row'" in query:
                    return []
                if "doc_type != 'row'" in query:
                    return [{
                        "doc_type": "descriptive_stat",
                        "doc_text": "revenue mean=10",
                        "metadata": {},
                        "row_index": None,
                    }]
                return [{
                    "doc_type": "correlation",
                    "doc_text": "revenue and returns are strongly negatively correlated",
                    "metadata": {},
                    "row_index": None,
                }]

            def fetchone(self):
                return None

        class FakeConnection:
            def __init__(self, cursor):
                self.cursor_value = cursor

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def cursor(self):
                return self.cursor_value

        cursor = FakeCursor()
        connection = FakeConnection(cursor)
        settings = type("Settings", (), {
            "rag_embeddings_table": "dataset_embeddings",
            "rag_top_k_rows": 8,
            "rag_top_k_facts": 1,
        })()

        with patch.object(rag_service, "_ensure_schema"), \
                patch.object(rag_service, "_connect", return_value=connection), \
                patch.object(rag_service, "embed_texts", return_value=[[0.1, 0.2]]), \
                patch.object(rag_service, "get_settings", return_value=settings):
            retrieved = rag_service.retrieve("job-1", "Give me a meaningful insight")

        self.assertIn("correlation", [doc["doc_type"] for doc in retrieved["facts"]])

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

    def test_build_dataset_context_caps_significant_trends(self):
        regression = {
            f"column_{index}": {"significant": True, "r_squared": index / 10}
            for index in range(10)
        }

        context = chat_service.build_dataset_context({"stats": {"regression": regression}})

        self.assertEqual(len(context["significant_trends"]), 8)
        self.assertNotIn("column_0", context["significant_trends"])
        self.assertIn("column_9", context["significant_trends"])

    def test_build_rag_user_content_is_compacted_for_large_contexts(self):
        facts = [
            {"doc_type": "descriptive_stat", "text": "A" * 2000}
            for _ in range(20)
        ]
        rows = [
            {"row_index": index, "text": f"Row {index}: value={index}"}
            for index in range(50)
        ]
        retrieved = {"facts": facts, "rows": rows}

        user_content = chat_service._build_rag_user_content(retrieved, "What is the biggest trend?", [
            {"role": "user", "content": "x" * 3000},
            {"role": "assistant", "content": "y" * 3000},
            {"role": "user", "content": "z" * 3000},
        ])

        self.assertLessEqual(len(user_content), chat_service.MAX_LLM_USER_CONTENT_CHARS)
        self.assertIn("What is the biggest trend?", user_content)

    def test_gemini_is_skipped_during_quota_cooldown(self):
        job = Job(job_id="job-quota", result={"summary": {}, "stats": {}}, chat_history=[], rag_status="ready")
        manager = JobManager()

        original_retry_at = chat_service._GEMINI_RETRY_AT
        original_disabled = chat_service._GEMINI_DISABLED_BY_QUOTA

        try:
            chat_service._GEMINI_DISABLED_BY_QUOTA = True
            with patch.object(chat_service, "get_settings", return_value=type("S", (), {"database_url": "postgresql://x"})()), \
                 patch.object(chat_service.rag_service, "retrieve", return_value={"facts": [], "rows": []}), \
                 patch.object(chat_service, "_get_groq_client", side_effect=RuntimeError("groq down")), \
                 patch.object(chat_service, "_call_gemini_json_with_failover") as gemini_call, \
                 patch.object(chat_service, "_fallback_answer", return_value={"answer": "fallback", "needs_new_chart": False, "chart_request": None, "source": "fallback"}) as fallback_answer:
                outcome = chat_service.ask_question(manager, job, "What is the trend?")

            gemini_call.assert_not_called()
            fallback_answer.assert_called_once()
            self.assertEqual(outcome["answer"], "fallback")
        finally:
            chat_service._GEMINI_RETRY_AT = original_retry_at
            chat_service._GEMINI_DISABLED_BY_QUOTA = original_disabled

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


class TestAskQuestionRagStatusBranches(unittest.TestCase):
    def setUp(self):
        self.manager = JobManager()
        self.db_settings = type("S", (), {"database_url": "postgresql://x"})()
        self.no_db_settings = type("S", (), {"database_url": ""})()

    def test_no_database_configured_uses_fallback(self):
        job = Job(job_id="job-no-db", result={"summary": {}, "stats": {}})
        with patch.object(chat_service, "get_settings", return_value=self.no_db_settings):
            outcome = chat_service.ask_question(self.manager, job, "Tell me about this data")

        self.assertEqual(outcome["source"], "fallback")
        self.assertEqual(outcome["index_status"], "unavailable")

    def test_not_built_triggers_build_and_returns_indexing_message(self):
        job = Job(job_id="job-not-built", result={"summary": {}, "stats": {}}, rag_status="not_built")
        with patch.object(chat_service, "get_settings", return_value=self.db_settings), \
             patch.object(chat_service.rag_service, "start_rag_build", return_value=True) as start_build:
            outcome = chat_service.ask_question(self.manager, job, "What's the trend?")

        start_build.assert_called_once_with(self.manager, job)
        self.assertEqual(outcome["index_status"], "building")

    def test_building_status_returns_still_indexing_message(self):
        job = Job(job_id="job-building", result={"summary": {}, "stats": {}}, rag_status="building")
        with patch.object(chat_service, "get_settings", return_value=self.db_settings), \
             patch.object(chat_service.rag_service, "start_rag_build") as start_build:
            outcome = chat_service.ask_question(self.manager, job, "What's the trend?")

        start_build.assert_not_called()
        self.assertEqual(outcome["index_status"], "building")

    def test_failed_status_uses_fallback_with_reason(self):
        job = Job(job_id="job-failed", result={"summary": {}, "stats": {}}, rag_status="failed", rag_error="boom")
        with patch.object(chat_service, "get_settings", return_value=self.db_settings):
            outcome = chat_service.ask_question(self.manager, job, "Tell me about this data")

        self.assertEqual(outcome["index_status"], "failed")
        self.assertIn("boom", outcome["answer"])

    def test_ready_status_retrieves_and_calls_llm(self):
        job = Job(job_id="job-ready", result={"summary": {}, "stats": {}}, rag_status="ready")
        retrieved = {"facts": [{"doc_type": "dataset_summary", "doc_text": "10 rows"}], "rows": []}
        llm_response = {"answer": "Here you go.", "needs_new_chart": False, "chart_request": None, "source": "groq"}

        with patch.object(chat_service, "get_settings", return_value=self.db_settings), \
             patch.object(chat_service.rag_service, "retrieve", return_value=retrieved) as retrieve_mock, \
             patch.object(chat_service, "_call_llm_for_rag_chat", return_value=llm_response) as llm_mock:
            outcome = chat_service.ask_question(self.manager, job, "What's the trend?")

        retrieve_mock.assert_called_once_with(job.job_id, "What's the trend?")
        llm_mock.assert_called_once()
        self.assertEqual(outcome["answer"], "Here you go.")
        self.assertEqual(outcome["source"], "groq")
        self.assertEqual(outcome["index_status"], "ready")

    def test_ready_status_retrieval_error_falls_back(self):
        job = Job(job_id="job-ready-err", result={"summary": {}, "stats": {}}, rag_status="ready")

        with patch.object(chat_service, "get_settings", return_value=self.db_settings), \
             patch.object(chat_service.rag_service, "retrieve", side_effect=RuntimeError("db down")):
            outcome = chat_service.ask_question(self.manager, job, "Tell me about this data")

        self.assertEqual(outcome["index_status"], "ready")
        self.assertEqual(outcome["source"], "fallback")


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
