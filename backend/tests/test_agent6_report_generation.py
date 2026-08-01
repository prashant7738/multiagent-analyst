import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from agents import agent_6


def _build_state():
    df = pd.DataFrame({"revenue": [100, 200, 300], "cost": [50, 90, 120]})
    stats = {
        "descriptive": {"revenue": {"count": 3, "mean": 200.0}},
        "correlation": {
            "strong_pairs": [
                {"col1": "revenue", "col2": "cost", "pearson_r": 0.97,
                 "direction": "positive", "strength": "strong"},
            ],
        },
        "anomaly_summary": {
            "unique_flagged_rows": 1, "unique_flagged_row_pct": 33.3,
            "flagged_columns": 1, "z_threshold": 3.5,
        },
        "regression": {
            "revenue": {
                "slope": 100.0, "intercept": 0.0, "r_squared": 0.95, "p_value": 0.01,
                "significant": True, "trend": "upward", "x_axis": "row_index",
            },
        },
        "growth_rates": {},
        "seasonality": {},
        "top_bottom": {},
    }
    data_quality = {"overall_quality_score": 90.0, "completeness_pct": 95.0, "duplicates_removed": 0}
    validation_report = {
        "overall_validation_score": 88.0,
        "passed": True,
        "flagged_issues": [],
        "semantic_tagging_agreement": {"cohen_kappa": 0.8},
    }
    reliability = {"overall_confidence": 0.9, "decision_readiness": "ready"}

    return {
        "csv_path": "sample.csv",
        "raw_profile": {"shape": {"rows": 3, "cols": 2}},
        "raw_shape": {"rows": 3, "cols": 2},
        "cleaned_df": df,
        "stats": stats,
        "data_quality": data_quality,
        "validation_report": validation_report,
        "reliability": reliability,
        "chart_paths": [],
        "errors": [],
    }


class TestAgent6ReportGeneration(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_reports_dir = agent_6.REPORTS_DIR
        agent_6.REPORTS_DIR = self._tmpdir.name

    def tearDown(self):
        agent_6.REPORTS_DIR = self._original_reports_dir
        self._tmpdir.cleanup()

    def test_falls_back_to_deterministic_narrative_when_llm_unavailable(self):
        state = _build_state()

        with patch.object(agent_6, "_get_groq_client", side_effect=RuntimeError("no groq key")), \
             patch.object(agent_6, "_get_gemini_client", side_effect=RuntimeError("no gemini key")):
            result = agent_6.agent6_insight_report_generator(state)

        self.assertEqual(result["insight_narrative"]["source"], "fallback")
        self.assertTrue(result["report_path"])
        report_file = Path(result["report_path"])
        self.assertTrue(report_file.exists())
        self.assertGreater(report_file.stat().st_size, 0)
        self.assertEqual(result["errors"], [])

    def test_extracts_deterministic_facts_and_uses_llm_narrative(self):
        state = _build_state()

        fake_narrative = {
            "executive_summary": "Revenue and cost are strongly correlated.",
            "key_findings": ["revenue and cost correlate at r=0.97"],
            "risks_and_caveats": [],
            "recommendations": ["Investigate the revenue-cost relationship."],
        }
        fake_completions = SimpleNamespace(
            create=lambda **kwargs: SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(fake_narrative)))]
            )
        )
        fake_client = SimpleNamespace(chat=SimpleNamespace(completions=fake_completions))

        with patch.object(agent_6, "_get_groq_client", return_value=fake_client):
            result = agent_6.agent6_insight_report_generator(state)

        facts = result["insight_facts"]
        self.assertEqual(facts["top_correlations"][0]["col1"], "revenue")
        self.assertEqual(facts["top_correlations"][0]["col2"], "cost")
        self.assertEqual(facts["data_quality"]["overall_quality_score"], 90.0)
        self.assertEqual(facts["validation"]["passed"], True)

        narrative = result["insight_narrative"]
        self.assertEqual(narrative["source"], "groq")
        self.assertEqual(narrative["executive_summary"], fake_narrative["executive_summary"])

        report_file = Path(result["report_path"])
        self.assertTrue(report_file.exists())

    def test_report_is_overwritten_not_duplicated_on_repeat_runs(self):
        state = _build_state()

        with patch.object(agent_6, "_get_groq_client", side_effect=RuntimeError("no groq key")), \
             patch.object(agent_6, "_get_gemini_client", side_effect=RuntimeError("no gemini key")):
            agent_6.agent6_insight_report_generator(state)
            agent_6.agent6_insight_report_generator(state)

        produced_files = list(Path(self._tmpdir.name).glob("insight_report.*"))
        names = {f.name for f in produced_files}
        self.assertLessEqual(len(produced_files), 2)  # at most insight_report.html + insight_report.pdf
        self.assertIn("insight_report.html", names)

    def test_pdf_conversion_failure_falls_back_to_html_report(self):
        state = _build_state()

        with patch.object(agent_6, "_get_groq_client", side_effect=RuntimeError("no groq key")), \
             patch.object(agent_6, "_get_gemini_client", side_effect=RuntimeError("no gemini key")), \
             patch("weasyprint.HTML", side_effect=RuntimeError("simulated missing system libs")):
            result = agent_6.agent6_insight_report_generator(state)

        self.assertTrue(result["report_path"].endswith(".html"))
        self.assertTrue(any("PDF conversion failed" in e for e in result["errors"]))

    def test_missing_upstream_data_records_error_without_raising(self):
        state = _build_state()
        state["stats"] = {}

        result = agent_6.agent6_insight_report_generator(state)

        self.assertTrue(any("Agent6" in e for e in result["errors"]))
        self.assertNotIn("report_path", result)


class TestRawColumnCountGuard(unittest.TestCase):
    """Guards against the executive summary silently reporting a post-transform
    column count as if it were the raw dataset's shape (Fix 2)."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_reports_dir = agent_6.REPORTS_DIR
        agent_6.REPORTS_DIR = self._tmpdir.name

    def tearDown(self):
        agent_6.REPORTS_DIR = self._original_reports_dir
        self._tmpdir.cleanup()

    def test_dataset_facts_prefer_raw_shape_over_raw_profile(self):
        state = _build_state()
        # Simulate a stale/incorrect raw_profile (e.g. mutated by another step) -
        # raw_shape, captured once by Agent 1, must win.
        state["raw_profile"] = {"shape": {"rows": 999, "cols": 999}}
        state["raw_shape"] = {"rows": 3, "cols": 2}

        facts = agent_6._extract_dataset_facts(state)

        self.assertEqual(facts["raw_rows"], 3)
        self.assertEqual(facts["raw_cols"], 2)

    def test_validate_raw_column_count_passes_when_matching(self):
        insight_facts = {"dataset": {"raw_cols": 29}}
        agent_6._validate_raw_column_count(insight_facts, {"cols": 29})  # should not raise

    def test_validate_raw_column_count_raises_on_mismatch(self):
        insight_facts = {"dataset": {"raw_cols": 112}}
        with self.assertRaises(AssertionError):
            agent_6._validate_raw_column_count(insight_facts, {"cols": 29})

    def test_agent6_records_error_instead_of_hard_failing_on_mismatch(self):
        state = _build_state()
        state["raw_shape"] = {"rows": 3, "cols": 2}

        # Simulate a future regression where dataset fact extraction is changed to
        # (incorrectly) report a post-transform column count as "raw" - this is the
        # exact class of bug Fix 2 guards against.
        stale_facts = agent_6._extract_insight_facts(state)
        stale_facts["dataset"]["raw_cols"] = 112

        with patch.object(agent_6, "_extract_insight_facts", return_value=stale_facts), \
             patch.object(agent_6, "_get_groq_client", side_effect=RuntimeError("no groq key")), \
             patch.object(agent_6, "_get_gemini_client", side_effect=RuntimeError("no gemini key")):
            result = agent_6.agent6_insight_report_generator(state)

        # Never hard-fails - a report is still produced.
        self.assertTrue(result["report_path"])
        self.assertTrue(any("raw column count" in e for e in result["errors"]))


if __name__ == "__main__":
    unittest.main()
