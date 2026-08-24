import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from agents import agent_3, agent_4, agent_6
from agents.chart_spec import finalize_specs


class TestSecondPassDataTrust(unittest.TestCase):
    def test_derived_revenue_after_discount_respects_fractional_discount(self):
        df = pd.DataFrame({"Revenue": [100.0], "Discount": [0.25]})
        schema = {
            "Revenue": {"financial_role": "revenue", "semantic_tag": "currency"},
            "Discount": {"financial_role": "discount", "semantic_tag": "percentage"},
        }

        result, _, _ = agent_3._derive_business_metrics(df, schema)

        self.assertEqual(result["derived_revenue_after_discount"].iloc[0], 75.0)
        self.assertEqual(result["derived_discount_pct"].iloc[0], 25.0)

    def test_currency_derived_revenue_is_not_checked_as_percentage(self):
        df = pd.DataFrame({"derived_revenue_after_discount": [83000.0, 92000.0]})
        schema = {"derived_revenue_after_discount": {"semantic_tag": "percentage"}}

        result = agent_4._detect_data_quality_issues(df, schema)

        self.assertNotIn("derived_revenue_after_discount out of [0, 100]", result["issues_by_rule"])

    def test_business_impact_is_bounded_by_total_impact_column(self):
        df = pd.DataFrame({"Revenue": [100.0, 200.0, 300.0, 400.0]})
        schema = {"Revenue": {"semantic_tag": "currency"}}

        _, summary = agent_4._detect_anomalies(df, schema, z_threshold=0.1)

        self.assertLessEqual(summary["business_impact_total"], 1000.0)


class TestSecondPassReportQuality(unittest.TestCase):
    def test_finalize_specs_dedupes_same_chart_identity_with_same_source(self):
        specs = [
            {"id": "planner_one", "section": "direction", "chart_type": "line", "title": "Yearly Growth", "priority": 50},
            {"id": "legacy_two", "section": "direction", "chart_type": "line", "title": "Yearly Growth", "priority": 40},
        ]

        result = finalize_specs(specs)

        self.assertEqual([item["id"] for item in result], ["planner_one"])

    def test_render_does_not_add_legacy_path_already_present_in_chart_specs(self):
        with TemporaryDirectory() as directory:
            chart_path = Path(directory) / "sales.png"
            from PIL import Image
            Image.new("RGB", (20, 20), "white").save(chart_path)
            state = {"chart_specs": [{
                "id": "legacy_sales", "section": "shape", "render": "image",
                "title": "Sales", "png_path": str(chart_path), "annotations": [],
            }]}
            facts = {"dataset": {}, "data_quality": {"overall_quality_score": 100}, "validation": {}, "reliability": {}}
            narrative = {"chart_captions": {}, "key_findings": [], "plain_language_insights": [],
                         "risks_and_caveats": [], "recommendations": [], "executive_summary": ""}

            html = agent_6._render_html(facts, narrative, [str(chart_path)], state)

            self.assertEqual(html.count("alt=\"Sales\""), 1)

    def test_impact_recommendation_is_not_larger_than_total_business_metric(self):
        facts = {
            "dataset": {}, "data_quality": {}, "top_correlations": [], "rankings": {},
            "anomalies": {"prioritized_anomalies": [{"column": "Profit", "business_impact": 663020729.11}],
                          "business_impact_total": 663020729.11, "business_impact_columns": ["Profit"],
                          "business_impact_ceiling": 93900000.0},
            "validation": {}, "significant_trends": [], "charts": [],
        }
        narrative = {"recommendations": ["Review Profit: $663020729.11 impact."]}

        result = agent_6._ground_recommendations(facts, narrative)

        self.assertFalse(any("663020729.11" in item for item in result))

    def test_negative_profit_subcategory_is_prioritized(self):
        facts = {
            "dataset": {}, "data_quality": {}, "top_correlations": [], "anomalies": {},
            "rankings": {},
            "profit_breakdown": {"Subcategory": {"top": [{"Subcategory": "Tables", "total_profit": -20}],
                                                   "bottom": [{"Subcategory": "Tables", "total_profit": -20}],
                                                   "total_categories": 3}},
            "significant_trends": [], "charts": [],
        }

        narrative = agent_6._fallback_narrative(facts)

        self.assertTrue(any("Tables" in item for item in narrative["recommendations"]))


if __name__ == "__main__":
    unittest.main()
