import base64
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from agents import agent_3, agent_4, agent_6


class TestStructuralRules(unittest.TestCase):
    def test_clean_count_dataset_has_no_structural_range_failures(self):
        values = np.arange(1, 1001, dtype=int)
        df = pd.DataFrame({"Units Sold": values})
        schema = {"Units Sold": {"semantic_tag": "count", "intended_type": "int"}}

        result = agent_4._detect_data_quality_issues(df, schema)

        self.assertEqual(result["data_quality_issue_rows"], 0)
        self.assertNotIn("Units Sold_range_failed", result["issues_by_rule"])

    def test_unconfigured_percentage_rule_uses_fixed_percent_bounds(self):
        df = pd.DataFrame({"discount_pct": [0.0, 25.0, 100.0, 101.0]})

        result = agent_4._detect_data_quality_issues(df, {})

        self.assertEqual(result["data_quality_issue_rows"], 1)

    def test_clean_count_column_is_not_percentile_clipped_by_tag_alone(self):
        # A uniformly-distributed "count" column has zero genuine outliers (per
        # Agent 1's own IQR-based distribution_analysis below), so outlier
        # clipping must not manufacture a ~5% flag purely because semantic_tag
        # is "count"/"currency"/"percentage" - that would silently mutate real,
        # valid values (e.g. Units Sold 2..10000) on ANY dataset with such a tag.
        series = pd.Series(range(1, 10001))
        meta = {"semantic_tag": "count", "intended_type": "int", "scaling_allowed": True}
        profile = {"distribution_analysis": {"distribution_type": "normal", "has_significant_outliers": False}}
        context = {"risk_assessment": "low"}

        clipped, clipped_count, bounds = agent_3._adaptive_outlier_clipping(
            series, meta, {}, profile=profile, data_quality_context=context
        )

        self.assertEqual(clipped_count, 0)
        self.assertEqual(bounds["method"], "iqr")


class TestDerivedLeadTimeAndCorrelation(unittest.TestCase):
    def test_derived_revenue_per_unit_uses_raw_sources_and_stays_formulaic(self):
        df = pd.DataFrame({
            "Total Revenue": [100.0, 220.0, 360.0, 500.0],
            "Units Sold": [2, 4, 6, 10],
            "Unit Price": [50.0, 55.0, 60.0, 50.0],
        })
        schema = {
            col: {"semantic_tag": "currency" if "Revenue" in col or "Price" in col else "count",
                  "intended_type": "float" if "Revenue" in col or "Price" in col else "int",
                  "scaling_allowed": True}
            for col in df.columns
        }

        result, _, derivation_map = agent_3._derive_business_metrics(df.copy(), schema)
        correlation, _ = agent_4._correlation(
            result,
            {"__metadata__": {"derived_metric_sources": derivation_map}, **schema},
        )

        self.assertEqual(result["derived_revenue_per_unit"].tolist(), result["Unit Price"].tolist())
        self.assertTrue(any(
            {pair["col1"], pair["col2"]} == {"Unit Price", "derived_revenue_per_unit"}
            for pair in correlation["formulaic_pairs"]
        ))
        self.assertFalse(any(
            {pair["col1"], pair["col2"]} == {"Unit Price", "derived_revenue_per_unit"}
            for pair in correlation["strong_pairs"]
        ))

    def test_lead_time_is_derived_with_distribution_and_dimension_breakdowns(self):
        df = pd.DataFrame({
            "Order Date": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-04", "2025-01-05"]),
            "Ship Date": pd.to_datetime(["2025-01-03", "2025-01-05", "2025-01-05", "2025-01-08"]),
            "Total Revenue": [100, 200, 150, 300],
            "Region": ["East", "West", "East", "West"],
            "Item Type": ["A", "A", "B", "B"],
        })
        schema = {
            "Order Date": {"semantic_tag": "datetime", "intended_type": "datetime"},
            "Ship Date": {"semantic_tag": "datetime", "intended_type": "datetime"},
            "Total Revenue": {"semantic_tag": "currency", "intended_type": "float"},
            "Region": {"semantic_tag": "geographic", "intended_type": "string"},
            "Item Type": {"semantic_tag": "categorical_label", "intended_type": "string"},
        }

        result, _, derivation_map = agent_3._derive_business_metrics(df.copy(), schema)
        self.assertEqual(result["derived_days_to_ship"].tolist(), [2, 3, 1, 3])
        self.assertEqual(derivation_map["derived_days_to_ship"], ["Order Date", "Ship Date"])

        analysis = agent_4.agent4_analysis({
            "cleaned_df": result,
            "schema_blueprint": {"__metadata__": {"derived_metric_sources": derivation_map}, **schema},
            "data_quality": {"overall_quality_score": 100.0},
            "errors": [],
        })
        self.assertIn("shipping_lead_time", analysis["stats"])
        self.assertTrue(analysis["stats"]["shipping_lead_time"]["distribution"])
        self.assertIn("Region", analysis["stats"]["shipping_lead_time"]["by_dimension"])
        self.assertIn("Item Type", analysis["stats"]["shipping_lead_time"]["by_dimension"])


class TestReportAuditability(unittest.TestCase):
    def test_plain_language_prioritizes_structural_score_impact(self):
        facts = {
            "data_quality": {"overall_quality_score": 80, "data_quality_issue_penalty": 12,
                             "anomaly_quality_penalty": 1},
            "anomalies": {"data_quality_issue_rows": 4, "data_quality_issue_row_pct": 4.0,
                          "issues_by_rule": {"Units Sold < 0": 4}, "rule_details": {},
                          "unique_flagged_rows": 100, "unique_flagged_row_pct": 10.0},
        }

        bullets, bottom_line = agent_6._plain_language_fallback(facts)

        self.assertIn("structural", bullets[0].lower())
        # The headline "bottom line" sentence must ALSO lead with whichever issue
        # category costs the most quality-score points, not unconditionally with
        # statistical outliers - a fixed template order here would still tell the
        # user to "focus on 100 unusual records" even though the 4-row structural
        # issue is the one actually costing more points (12 vs 1).
        self.assertIn("structural", bottom_line.lower())

    def test_bottom_line_falls_back_to_statistical_outliers_when_larger(self):
        facts = {
            "data_quality": {"overall_quality_score": 95, "data_quality_issue_penalty": 0.5,
                             "anomaly_quality_penalty": 4},
            "anomalies": {"data_quality_issue_rows": 2, "data_quality_issue_row_pct": 0.2,
                          "issues_by_rule": {}, "rule_details": {},
                          "unique_flagged_rows": 63, "unique_flagged_row_pct": 0.63},
        }

        _, bottom_line = agent_6._plain_language_fallback(facts)

        self.assertIn("63 unusual records", bottom_line)

    def test_recommendation_business_impact_is_present_in_anomaly_facts(self):
        facts = {
            "anomalies": {"prioritized_anomalies": [{"column": "Total Revenue", "business_impact": 1234.56}]},
            "rankings": {}, "top_correlations": [],
        }
        narrative = {"recommendations": ["Review Total Revenue: impact about $999.00."]}

        grounded = agent_6._ground_recommendations(facts, narrative)

        self.assertTrue(all("999.00" not in recommendation for recommendation in grounded))


class TestChartEmbedding(unittest.TestCase):
    def test_render_html_resizes_and_compresses_embedded_chart(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            chart = Path(temp_dir) / "chart.png"
            chart.write_bytes(b"not-a-real-png")
            # The renderer must enforce its byte/pixel policy before embedding;
            # use a real image for the behavior check.
            from PIL import Image
            Image.new("RGB", (2400, 1600), "white").save(chart)
            state = {"csv_path": "data.csv", "data_quality": {"overall_quality_score": 100}, "errors": []}
            facts = agent_6._extract_insight_facts(state)
            narrative = {
                "executive_summary": "",
                "key_findings": [],
                "plain_language_insights": [],
                "bottom_line": "",
                "risks_and_caveats": [],
                "recommendations": [],
            }
            html = agent_6._render_html(facts, narrative, [str(chart)], state)
            encoded = html.split("data:image/png;base64,", 1)[1].split('"', 1)[0]
            self.assertLess(len(base64.b64decode(encoded)), chart.stat().st_size)

    def test_render_html_accepts_legacy_facts_without_lead_time(self):
        state = {"csv_path": "data.csv", "data_quality": {"overall_quality_score": 100}, "errors": []}
        facts = agent_6._extract_insight_facts(state)
        facts["cross_dimensional"].pop("shipping_lead_time", None)
        narrative = {
            "executive_summary": "",
            "key_findings": [],
            "plain_language_insights": [],
            "bottom_line": "",
            "risks_and_caveats": [],
            "recommendations": [],
        }

        agent_6._render_html(facts, narrative, [], state)


if __name__ == "__main__":
    unittest.main()