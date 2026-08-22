import unittest

import pandas as pd

from agents import agent_4, agent_6


class TestActionability(unittest.TestCase):
    def test_anomalies_are_ranked_by_business_impact(self):
        df = pd.DataFrame({
            "revenue": [100] * 20 + [1_000_000],
            "cost": [50] * 20 + [500_000],
        })

        anomalies, summary = agent_4._detect_anomalies(df, {
            "revenue": {"semantic_tag": "currency"},
            "cost": {"semantic_tag": "currency"},
        })

        ranked = summary["prioritized_anomalies"]
        self.assertTrue(ranked)
        self.assertEqual(ranked[0]["column"], "revenue")
        self.assertGreaterEqual(
            ranked[0]["business_impact"], ranked[-1]["business_impact"]
        )
        self.assertEqual(summary["business_impact_total"], sum(item["business_impact"] for item in ranked))
        self.assertIn("business_impact", anomalies["revenue"])

    def test_fallback_recommendations_name_report_findings(self):
        facts = {
            "rankings": {
                "region": {
                    "top": [{"region": "North", "revenue_share_pct": 60.0}],
                    "bottom": [{"region": "South", "revenue_share_pct": 4.0}],
                },
            },
            "anomalies": {"prioritized_anomalies": [{"column": "revenue", "business_impact": 9000.0}]},
        }

        narrative = agent_6._fallback_narrative({
            "dataset": {"cleaned_rows": 5, "cleaned_cols": 2},
            "data_quality": {"overall_quality_score": 90},
            "validation": {},
            **facts,
        })

        recommendations = " ".join(narrative["recommendations"])
        self.assertIn("South", recommendations)
        self.assertIn("revenue", recommendations)


class TestKnownBadDatasets(unittest.TestCase):
    def test_wrong_percentage_units_are_flagged_and_rule_manifest_is_logged(self):
        # The column is deliberately expressed as 25 rather than 0.25. The
        # percentage rule must remain visible and versioned for eval output.
        df = pd.DataFrame({"conversion_rate": [0.10, 0.20, 25.0]})
        result = agent_4._detect_data_quality_issues(df, {
            "conversion_rate": {"semantic_tag": "percentage", "unit_scale": "ratio"},
        })

        self.assertEqual(result["data_quality_issue_rows"], 1)
        self.assertIn("rule_manifest", result)
        self.assertTrue(result["rule_manifest"]["version"])
        self.assertIn("conversion_rate out of [0, 1]", result["rules_checked"])


if __name__ == "__main__":
    unittest.main()