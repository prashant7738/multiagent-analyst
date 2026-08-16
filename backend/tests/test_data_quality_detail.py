"""Bug 3 — Data Quality Detail reporting.

Verifies agent_6._extract_data_quality_detail surfaces the pipeline's ACTUAL
duplicate handling and per-column missing-value handling, reconciled against
cleaned_df so it never claims an imputation that did not happen.
"""

import unittest

import pandas as pd

from agents import agent_6


def _build_state():
    # cleaned_df's null counts encode what the pipeline actually did:
    #   revenue -> imputed (0 nulls left), discount -> flagged only (3 left),
    #   notes   -> impute requested but not applied (4 left),
    #   price   -> currency, imputation blocked (2 left).
    cleaned = pd.DataFrame({
        "revenue":  [1.0, 2.0, 3.0, 4.0],
        "discount": [0.1, None, None, None],
        "cost":     [10, 20, 30, 40],
        "notes":    [None, None, None, None],
        "price":    [None, 5.0, None, 7.0],
    })
    return {
        "column_ledger": {
            "row_accounting": {
                "input_rows": 100,
                "exact_duplicates_removed": 12,
                "rows_dropped_by_canonical_dedup": 3,
                "final_rows": 85,
            }
        },
        "raw_profile": {
            "shape": {"rows": 100, "cols": 5},
            "columns": {
                "revenue":  {"missing_count": 12, "missing_rate_pct": 12.0},
                "discount": {"missing_count": 3,  "missing_rate_pct": 3.0},
                "cost":     {"missing_count": 0,  "missing_rate_pct": 0.0},
                "notes":    {"missing_count": 4},  # missing_rate_pct omitted -> computed
                "price":    {"missing_count": 2,  "missing_rate_pct": 2.0},
            },
        },
        "schema_blueprint": {
            "revenue":  {"null_policy": {"action": "impute_median"}, "semantic_tag": "numeric"},
            "discount": {"null_policy": {"action": "flag_only"}, "semantic_tag": "numeric"},
            "notes":    {"null_policy": {"action": "impute_median"}, "semantic_tag": "string"},
            "price":    {"null_policy": {"action": "impute_median"}, "semantic_tag": "currency"},
        },
        "cleaned_df": cleaned,
    }


class TestDataQualityDetail(unittest.TestCase):
    def setUp(self):
        self.detail = agent_6._extract_data_quality_detail(_build_state())
        self.missing = {r["column"]: r for r in self.detail["missing_values"]}

    # --- duplicates -----------------------------------------------------------
    def test_duplicate_counts_appear(self):
        dups = self.detail["duplicates"]
        self.assertEqual(dups["exact_duplicates_detected"], 12)
        self.assertEqual(dups["exact_duplicates_removed"], 12)

    def test_duplicate_action_matches_actual_pipeline_behavior(self):
        # Agent 3 removes exact duplicates, so the report must say so.
        self.assertEqual(self.detail["duplicates"]["action"], "duplicates removed")

    def test_near_duplicates_reported(self):
        dups = self.detail["duplicates"]
        self.assertEqual(dups["near_duplicates_detected"], 3)
        self.assertIn("near-duplicates removed", dups["near_duplicate_action"])

    def test_no_exact_duplicates_reported_accurately(self):
        state = _build_state()
        state["column_ledger"]["row_accounting"]["exact_duplicates_removed"] = 0
        detail = agent_6._extract_data_quality_detail(state)
        self.assertEqual(detail["duplicates"]["action"], "no exact duplicates detected")

    # --- missing values -------------------------------------------------------
    def test_missing_counts_correct_for_every_affected_column(self):
        self.assertEqual(self.missing["revenue"]["missing_count"], 12)
        self.assertEqual(self.missing["discount"]["missing_count"], 3)
        self.assertEqual(self.missing["notes"]["missing_count"], 4)
        self.assertEqual(self.missing["price"]["missing_count"], 2)
        # A column with no missing values is not listed.
        self.assertNotIn("cost", self.missing)

    def test_missing_percentages_calculated_correctly(self):
        self.assertEqual(self.missing["revenue"]["missing_pct"], 12.0)
        # notes omitted missing_rate_pct -> computed from raw shape (4/100).
        self.assertEqual(self.missing["notes"]["missing_pct"], 4.0)

    def test_imputation_method_matches_what_actually_happened(self):
        self.assertEqual(self.missing["revenue"]["action"], "median imputation")

    def test_flag_only_column_reported_as_left_as_null(self):
        self.assertEqual(self.missing["discount"]["action"], "left as null")

    def test_requested_but_unapplied_imputation_reported_as_left_as_null(self):
        # Blueprint asked for median imputation but the nulls survived in
        # cleaned_df -> must not falsely claim imputation.
        self.assertEqual(self.missing["notes"]["action"], "left as null")

    def test_currency_imputation_block_reported_as_left_as_null(self):
        self.assertEqual(self.missing["price"]["action"], "left as null")


if __name__ == "__main__":
    unittest.main()
