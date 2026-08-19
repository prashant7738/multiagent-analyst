import unittest

import numpy as np
import pandas as pd

from agents import agent_4, agent_6


class TestDataQualityDetailFacts(unittest.TestCase):
    def test_extracts_duplicate_actions_and_missing_value_details(self):
        state = {
            "raw_profile": {
                "columns": {
                    "quantity": {"missing_count": 2, "missing_pct": 20.0},
                    "status": {"missing_count": 1, "missing_pct": 10.0},
                    "complete": {"missing_count": 0, "missing_pct": 0.0},
                }
            },
            "schema_blueprint": {
                "quantity": {"null_policy": {"action": "impute_median"}},
                "status": {"null_policy": {"action": "flag_only"}},
            },
            "data_quality": {
                "overall_quality_score": 91.0,
                "raw_completeness_pct": 90.0,
                "raw_missing_pct": 10.0,
                "remaining_null_pct": 2.0,
            },
            "column_ledger": {
                "row_accounting": {
                    "exact_duplicates_removed": 3,
                    "rows_dropped_by_canonical_dedup": 2,
                    "rows_dropped_by_imputation": 1,
                }
            },
        }

        facts = agent_6._extract_quality_facts(state)

        self.assertEqual(facts["duplicates"]["exact_count"], 3)
        self.assertEqual(facts["duplicates"]["near_duplicate_count"], 2)
        self.assertEqual(facts["duplicates"]["rows_dropped_for_missing_values"], 1)
        details = {item["column"]: item for item in facts["missing_values"]}
        self.assertEqual(details["quantity"]["count"], 2)
        self.assertEqual(details["quantity"]["action"], "impute_median")
        self.assertEqual(details["status"]["action"], "flag_only")
        self.assertEqual(details["complete"]["action"], "left as null")


class TestStructuralQualityIssues(unittest.TestCase):
    SCHEMA = {
        "Quantity": {"intended_type": "int"},
        "Discount_Percentage": {"intended_type": "float"},
        "Return_Quantity": {"intended_type": "int"},
    }

    def test_flags_structural_rules_separately_from_outliers(self):
        df = pd.DataFrame({
            "Quantity": [1, -1, 2.5, 3],
            "Discount_Percentage": [0.1, 0.2, 1.2, 0.3],
            "Return_Quantity": [0, 3, 0, 1],
        })

        issues = agent_4._detect_structural_quality_issues(df, self.SCHEMA)

        self.assertIn("Quantity", issues)
        self.assertIn("Discount_Percentage", issues)
        self.assertIn("Return_Quantity_vs_Quantity", issues)
        self.assertIn("return quantity must not exceed order quantity", issues["Return_Quantity_vs_Quantity"]["rule"])

    def test_statistical_outliers_do_not_drive_quality_penalty(self):
        data_quality = {"overall_quality_score": 90.0}
        summary = {
            "unique_flagged_row_pct": 40.0,
            "structural_issue_row_pct": 0.0,
        }

        adjusted = agent_4._apply_anomaly_quality_penalty(data_quality, summary)

        self.assertEqual(adjusted["overall_quality_score"], 90.0)
        self.assertEqual(adjusted["anomaly_quality_penalty"], 0.0)
        self.assertEqual(adjusted["anomaly_flagged_row_pct"], 40.0)

    def test_structural_issues_drive_quality_penalty(self):
        data_quality = {"overall_quality_score": 90.0}
        summary = {
            "unique_flagged_row_pct": 40.0,
            "structural_issue_row_pct": 5.0,
        }

        adjusted = agent_4._apply_anomaly_quality_penalty(data_quality, summary)

        self.assertEqual(adjusted["overall_quality_score"], 88.4)
        self.assertEqual(adjusted["structural_issue_row_pct"], 5.0)

    def test_anomaly_results_are_classified_as_statistical_outliers(self):
        values = [1.0] * 39 + [1000.0]
        df = pd.DataFrame({"amount": values})
        schema = {"amount": {"intended_type": "float"}}

        anomalies, summary = agent_4._detect_anomalies(df, schema)

        self.assertIn("amount", anomalies)
        self.assertEqual(anomalies["amount"]["classification"], "statistical_outlier")
        self.assertIn("statistical_outlier_rows", summary)
        self.assertIn("structural_issue_rows", summary)


if __name__ == "__main__":
    unittest.main()
