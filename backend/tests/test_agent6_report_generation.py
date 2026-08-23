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
             patch.object(agent_6, "_call_gemini_json_with_failover", side_effect=RuntimeError("no gemini key")):
            result = agent_6.agent6_insight_report_generator(state)

        self.assertEqual(result["insight_narrative"]["source"], "fallback")
        self.assertTrue(result["report_path"])
        report_file = Path(result["report_path"])
        self.assertTrue(report_file.exists())
        self.assertGreater(report_file.stat().st_size, 0)
        self.assertEqual(result["errors"], [])

    def test_uses_groq_for_narrative_when_available(self):
        state = _build_state()
        fake_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({
                "executive_summary": "Revenue and cost are strongly correlated.",
                "key_findings": [],
                "risks_and_caveats": [],
                "recommendations": [],
            })))]
        )
        fake_groq_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: fake_response))
        )

        with patch.object(agent_6, "_get_groq_client", return_value=fake_groq_client), \
             patch.object(agent_6, "_call_gemini_json_with_failover") as gemini_call:
            result = agent_6.agent6_insight_report_generator(state)

        self.assertEqual(result["insight_narrative"]["source"], "groq")
        gemini_call.assert_not_called()

    def test_falls_back_to_gemini_when_groq_unavailable(self):
        state = _build_state()
        fake_narrative = {
            "executive_summary": "Revenue and cost are strongly correlated.",
            "key_findings": [],
            "risks_and_caveats": [],
            "recommendations": [],
        }

        with patch.object(agent_6, "_get_groq_client", side_effect=RuntimeError("no groq key")), \
             patch.object(agent_6, "_call_gemini_json_with_failover", return_value=fake_narrative) as gemini_call:
            result = agent_6.agent6_insight_report_generator(state)

        self.assertEqual(result["insight_narrative"]["source"], "gemini")
        gemini_call.assert_called_once()

    def test_extracts_deterministic_facts_and_uses_llm_narrative(self):
        state = _build_state()

        fake_narrative = {
            "executive_summary": "Revenue and cost are strongly correlated.",
            "key_findings": ["revenue and cost correlate at r=0.97"],
            "risks_and_caveats": [],
            "recommendations": ["Investigate the revenue-cost relationship."],
        }
        with patch.object(agent_6, "_get_groq_client", side_effect=RuntimeError("no groq key")), \
             patch.object(agent_6, "_call_gemini_json_with_failover", return_value=fake_narrative):
            result = agent_6.agent6_insight_report_generator(state)

        facts = result["insight_facts"]
        self.assertEqual(facts["top_correlations"][0]["col1"], "revenue")
        self.assertEqual(facts["top_correlations"][0]["col2"], "cost")
        self.assertEqual(facts["data_quality"]["overall_quality_score"], 90.0)
        self.assertEqual(facts["validation"]["passed"], True)

        narrative = result["insight_narrative"]
        self.assertEqual(narrative["source"], "gemini")
        self.assertEqual(narrative["executive_summary"], fake_narrative["executive_summary"])

        report_file = Path(result["report_path"])
        self.assertTrue(report_file.exists())

    def test_report_is_overwritten_not_duplicated_on_repeat_runs(self):
        state = _build_state()

        with patch.object(agent_6, "_get_groq_client", side_effect=RuntimeError("no groq key")), \
             patch.object(agent_6, "_call_gemini_json_with_failover", side_effect=RuntimeError("no gemini key")):
            agent_6.agent6_insight_report_generator(state)
            agent_6.agent6_insight_report_generator(state)

        produced_files = list(Path(self._tmpdir.name).glob("insight_report.*"))
        names = {f.name for f in produced_files}
        self.assertLessEqual(len(produced_files), 2)  # at most insight_report.html + insight_report.pdf
        self.assertIn("insight_report.html", names)

    def test_report_renders_one_data_quality_detail_section(self):
        state = _build_state()

        with patch.object(agent_6, "_get_groq_client", side_effect=RuntimeError("no groq key")), \
             patch.object(agent_6, "_call_gemini_json_with_failover", side_effect=RuntimeError("no gemini key")):
            result = agent_6.agent6_insight_report_generator(state)

        report_html = Path(result["report_path"]).read_text(encoding="utf-8")
        self.assertEqual(report_html.count("<h2>Data Quality Detail</h2>"), 1)

    def test_print_styles_show_scroll_reveal_content(self):
        template = (Path(agent_6.TEMPLATE_DIR) / agent_6.TEMPLATE_NAME).read_text(encoding="utf-8")
        print_styles = template.split("@media print", 1)[1]
        self.assertIn("[data-reveal] { opacity: 1; transform: none; transition: none; }", print_styles)

    def test_report_renders_business_impact_without_structural_issues(self):
        state = _build_state()
        state["stats"]["anomaly_summary"].update({
            "unique_flagged_rows": 1,
            "prioritized_anomalies": [{
                "column": "revenue",
                "flagged_count": 1,
                "business_impact": 275955.42,
            }],
        })

        with patch.object(agent_6, "_get_groq_client", side_effect=RuntimeError("no groq key")), \
             patch.object(agent_6, "_call_gemini_json_with_failover", side_effect=RuntimeError("no gemini key")):
            result = agent_6.agent6_insight_report_generator(state)

        report_html = Path(result["report_path"]).read_text(encoding="utf-8")
        self.assertIn("Business Impact of Unusual Entries", report_html)
        self.assertIn("275955.42", report_html)

    def test_pdf_conversion_failure_falls_back_to_html_report(self):
        state = _build_state()

        with patch.object(agent_6, "_get_groq_client", side_effect=RuntimeError("no groq key")), \
             patch.object(agent_6, "_call_gemini_json_with_failover", side_effect=RuntimeError("no gemini key")), \
             patch("weasyprint.HTML", side_effect=RuntimeError("simulated missing system libs")):
            result = agent_6.agent6_insight_report_generator(state)

        self.assertTrue(result["report_path"].endswith(".html"))
        self.assertTrue(any("PDF conversion failed" in e for e in result["errors"]))

    def test_missing_weasyprint_exception_class_falls_back_to_html_report(self):
        errors = []
        fake_weasyprint = SimpleNamespace(
            HTML=SimpleNamespace(
                __call__=lambda *_args, **_kwargs: None,
            ),
        )

        with patch.dict("sys.modules", {"weasyprint": fake_weasyprint}):
            report_path, pdf_written = agent_6._write_report(
                "<html></html>", self._tmpdir.name, errors
            )

        self.assertTrue(report_path.endswith(".html"))
        self.assertFalse(pdf_written)
        self.assertTrue(any("PDF conversion failed" in error for error in errors))

    def test_missing_upstream_data_records_error_without_raising(self):
        state = _build_state()
        state["stats"] = {}

        result = agent_6.agent6_insight_report_generator(state)

        self.assertTrue(any("Agent6" in e for e in result["errors"]))
        self.assertNotIn("report_path", result)


class TestTruncateListsForPrompt(unittest.TestCase):
    """example_rows (agent_4._detect_data_quality_issues) holds full raw-dataframe
    rows - on a wide one-hot-encoded dataset these blow the narrative prompt past
    Groq's TPM cap even after list-length truncation, since they're nested inside
    a dict (rule_details), not a bare list. The narrative never cites individual
    example rows, so they must be dropped from the prompt copy entirely."""

    def test_example_rows_are_dropped_from_prompt_copy(self):
        wide_row = {f"col_{i}": i for i in range(80)}
        insight_facts = {
            "anomalies": {
                "rule_details": {
                    "Quantity < 0": {
                        "count": 5,
                        "pct": 1.2,
                        "review_required": False,
                        "example_rows": [wide_row, wide_row],
                    },
                },
            },
        }

        prompt_facts = agent_6._truncate_lists_for_prompt(insight_facts)

        rule_detail = prompt_facts["anomalies"]["rule_details"]["Quantity < 0"]
        self.assertNotIn("example_rows", rule_detail)
        self.assertEqual(rule_detail["count"], 5)
        self.assertEqual(rule_detail["pct"], 1.2)
        # original facts (used for HTML rendering/grounding) must stay untouched
        self.assertIn("example_rows", insight_facts["anomalies"]["rule_details"]["Quantity < 0"])

    def test_other_lists_still_truncated_to_max_items(self):
        insight_facts = {"top_correlations": [{"col1": f"a{i}", "col2": "b"} for i in range(20)]}

        prompt_facts = agent_6._truncate_lists_for_prompt(insight_facts)

        self.assertEqual(len(prompt_facts["top_correlations"]), agent_6._MAX_LIST_ITEMS_FOR_PROMPT + 1)
        self.assertTrue(str(prompt_facts["top_correlations"][-1]).endswith("omitted for brevity"))

    def test_narrative_prompt_payload_keeps_signals_without_report_details(self):
        insight_facts = {
            "dataset": {"raw_rows": 10000, "raw_cols": 14, "cleaned_rows": 10000, "cleaned_cols": 60},
            "shape_explanation": {"column_explanations": ["expanded features"]},
            "data_quality": {"overall_quality_score": 100, "remaining_null_pct": 0},
            "data_quality_detail": {
                "duplicates": {"exact_duplicates_removed": 4},
                "missing_values": [{"column": f"c{i}", "missing_count": i} for i in range(20)],
            },
            "top_correlations": [{"col1": f"a{i}", "col2": "revenue", "pearson_r": 0.9} for i in range(20)],
            "cross_dimensional": {
                "category_margin_trend": {
                    "series": [{"category": f"c{i}", "month": i, "margin": 0.2} for i in range(20)]
                },
            },
            "anomalies": {
                "data_quality_issue_rows": 5,
                "data_quality_issue_row_pct": 0.05,
                "rule_details": {"bad rule": {
                    "count": 5,
                    "pct": 0.05,
                    "example_rows": [{f"feature_{i}": i for i in range(100)}],
                }},
            },
            "charts": [{"id": f"chart-{i}", "title": "Revenue", "what_it_shows": "Trend"} for i in range(20)],
        }

        prompt_facts = agent_6._build_narrative_prompt_facts(insight_facts)
        serialized = json.dumps(prompt_facts, separators=(",", ":"), default=str)

        self.assertEqual(prompt_facts["dataset"]["raw_rows"], 10000)
        self.assertEqual(prompt_facts["data_quality"]["overall_quality_score"], 100)
        self.assertEqual(prompt_facts["anomalies"]["data_quality_issue_rows"], 5)
        self.assertNotIn("example_rows", prompt_facts["anomalies"]["rule_details"]["bad rule"])
        self.assertLess(len(serialized), 10000)
        self.assertEqual(len(insight_facts["data_quality_detail"]["missing_values"]), 20)

    def test_narrative_prompt_payload_has_hard_size_budget_for_many_dimensions(self):
        insight_facts = {
            "dataset": {"raw_rows": 10000, "raw_cols": 14, "cleaned_rows": 10000, "cleaned_cols": 60},
            "data_quality": {"overall_quality_score": 100},
            "rankings": {
                f"dimension_{i}": {
                    "top": [{"label": f"top-{j}", "total_revenue": j * 1000} for j in range(8)],
                    "bottom": [{"label": f"bottom-{j}", "total_revenue": j * 100} for j in range(8)],
                    "total_categories": 30,
                }
                for i in range(12)
            },
            "profit_breakdown": {
                f"dimension_{i}": {
                    "top": [{"label": f"top-{j}", "total_profit": j * 100} for j in range(8)],
                    "bottom": [{"label": f"bottom-{j}", "total_profit": j * 10} for j in range(8)],
                    "total_categories": 30,
                }
                for i in range(12)
            },
            "cross_dimensional": {
                f"analysis_{i}": {
                    "records": [{"group": f"group-{j}", "value": j} for j in range(20)]
                }
                for i in range(8)
            },
            "charts": [{"id": f"chart-{i}", "title": "Revenue", "what_it_shows": "Trend"} for i in range(20)],
        }

        prompt_facts = agent_6._build_narrative_prompt_facts(insight_facts)
        serialized = json.dumps(prompt_facts, separators=(",", ":"), default=str)

        self.assertLessEqual(len(serialized), agent_6.MAX_NARRATIVE_PROMPT_CHARS)
        self.assertIn("dataset", prompt_facts)
        self.assertIn("rankings", prompt_facts)
        self.assertIn("cross_dimensional", prompt_facts)


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
             patch.object(agent_6, "_call_gemini_json_with_failover", side_effect=RuntimeError("no gemini key")):
            result = agent_6.agent6_insight_report_generator(state)

        # Never hard-fails - a report is still produced.
        self.assertTrue(result["report_path"])
        self.assertTrue(any("raw column count" in e for e in result["errors"]))


if __name__ == "__main__":
    unittest.main()
