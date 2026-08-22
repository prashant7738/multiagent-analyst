"""Bug 4 — Anomaly-rate calibration + Data Quality Score.

Verifies that:
  * the IQR fallback multiplier is the configured Tukey "far out" fence (k=3.0),
  * legitimate statistical outliers are NOT classified as structural defects,
  * structural/domain violations (negative qty, discount > 100%, impossible
    returns) ARE classified as data-quality issues,
  * the Data Quality Score is driven by structural issues, not by the sheer
    volume of statistical outliers.
"""

import unittest

import pandas as pd

from agents import agent_4


class TestIqrMultiplierConfig(unittest.TestCase):
    def test_iqr_multiplier_is_tukey_far_out_fence(self):
        # k=3.0 is Tukey's "far out" fence — deliberately wider than the k=1.5
        # "outer fence" used for clipping, so this branch flags (not clips) and
        # stops the ~24% over-flagging the 1.5x rule produced on skewed columns.
        self.assertEqual(agent_4.ANOMALY_IQR_MULTIPLIER, 3.0)


class TestStructuralIssueClassification(unittest.TestCase):
    def test_dominant_structural_rule_is_reviewed_with_examples(self):
        df = pd.DataFrame({
            "discount_rate": [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 50.0],
            "quantity_range_failed": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
        })
        schema = {
            "discount_rate": {
                "semantic_tag": "percentage",
                "intended_type": "float",
            },
        }

        result = agent_4._detect_data_quality_issues(df, schema)

        self.assertTrue(result["review_required"])
        self.assertNotIn("discount_rate out of [0, 100]", result["issues_by_rule"])
        self.assertIn("quantity_range_failed", result["issues_by_rule"])
        detail = result["rule_details"]["quantity_range_failed"]
        self.assertTrue(detail["review_required"])
        self.assertEqual(len(detail["example_rows"]), 5)

    def test_legitimate_long_tail_outlier_is_not_a_structural_issue(self):
        # One huge but legitimate revenue value: a statistical outlier, not a
        # structural defect.
        df = pd.DataFrame({"revenue": [100, 120, 110, 130, 10_000_000]})
        result = agent_4._detect_data_quality_issues(df, {"revenue": {"semantic_tag": "currency"}})
        self.assertEqual(result["data_quality_issue_rows"], 0)

    def test_negative_quantity_is_structural_issue(self):
        df = pd.DataFrame({"quantity": [5, 3, -2, 8]})
        schema = {"quantity": {"semantic_tag": "count"}}
        result = agent_4._detect_data_quality_issues(df, schema)
        self.assertEqual(result["data_quality_issue_rows"], 1)
        self.assertTrue(any("quantity" in rule for rule in result["rules_checked"]))

    def test_discount_over_100_percent_is_structural_issue(self):
        df = pd.DataFrame({"discount_pct": [10.0, 25.0, 150.0, 0.0]})
        result = agent_4._detect_data_quality_issues(df, {})
        self.assertEqual(result["data_quality_issue_rows"], 1)

    def test_return_quantity_exceeding_order_quantity_is_structural_issue(self):
        df = pd.DataFrame({
            "return_quantity": [1, 5, 0],
            "order_quantity":  [10, 2, 3],
        })
        result = agent_4._detect_data_quality_issues(df, {})
        # Only the middle row (5 > 2) violates the constraint.
        self.assertEqual(result["data_quality_issue_rows"], 1)

    def test_reuses_agent3_structural_validation_flags(self):
        # Agent 3's boolean flag columns are honoured directly.
        df = pd.DataFrame({
            "Units_range_failed": [0, 1, 0, 1],
            "revenue": [1, 2, 3, 4],
        })
        result = agent_4._detect_data_quality_issues(df, {})
        self.assertEqual(result["data_quality_issue_rows"], 2)


class TestDataQualityScorePenalty(unittest.TestCase):
    def test_many_statistical_outliers_do_not_dominate_the_score(self):
        dq = {"overall_quality_score": 90.0}
        anomaly_summary = {"unique_flagged_row_pct": 24.0}
        dq_issues = {"data_quality_issue_row_pct": 0.0, "issues_by_rule": {}}

        adjusted = agent_4._apply_anomaly_quality_penalty(dq, anomaly_summary, dq_issues)

        # 24% statistical outliers must not cause a major penalty.
        self.assertLessEqual(adjusted["anomaly_quality_penalty"], 5.0)
        self.assertGreaterEqual(adjusted["overall_quality_score"], 85.0)
        self.assertEqual(adjusted["data_quality_issue_penalty"], 0.0)

    def test_structural_violations_reduce_the_score_meaningfully(self):
        dq = {"overall_quality_score": 90.0}
        anomaly_summary = {"unique_flagged_row_pct": 0.0}
        dq_issues = {"data_quality_issue_row_pct": 20.0, "issues_by_rule": {"quantity < 0": 20}}

        adjusted = agent_4._apply_anomaly_quality_penalty(dq, anomaly_summary, dq_issues)

        self.assertGreaterEqual(adjusted["data_quality_issue_penalty"], 15.0)
        self.assertLessEqual(adjusted["overall_quality_score"], 75.0)

    def test_structural_penalty_dominates_statistical_penalty(self):
        # Same row-pct for both signals -> structural must weigh far more.
        dq_stat = agent_4._apply_anomaly_quality_penalty(
            {"overall_quality_score": 100.0},
            {"unique_flagged_row_pct": 15.0},
            {"data_quality_issue_row_pct": 0.0},
        )
        dq_struct = agent_4._apply_anomaly_quality_penalty(
            {"overall_quality_score": 100.0},
            {"unique_flagged_row_pct": 0.0},
            {"data_quality_issue_row_pct": 15.0},
        )
        self.assertGreater(
            dq_struct["data_quality_issue_penalty"],
            dq_stat["anomaly_quality_penalty"],
        )


class TestReportDistinguishesOutliersFromIssues(unittest.TestCase):
    def test_anomaly_facts_separate_statistical_from_structural(self):
        from agents import agent_6

        stats = {
            "anomaly_summary": {"unique_flagged_rows": 40, "unique_flagged_row_pct": 24.0,
                                "flagged_columns": 2, "z_threshold": 3.5},
            "data_quality_issues": {"data_quality_issue_rows": 3, "data_quality_issue_row_pct": 1.8,
                                    "issues_by_rule": {"quantity < 0": 3}},
        }
        facts = agent_6._extract_anomaly_facts(stats)

        # Statistical outliers and structural issues are surfaced as distinct
        # numbers so the report never conflates the two.
        self.assertEqual(facts["unique_flagged_rows"], 40)
        self.assertEqual(facts["data_quality_issue_rows"], 3)
        self.assertEqual(facts["issues_by_rule"], {"quantity < 0": 3})


if __name__ == "__main__":
    unittest.main()
