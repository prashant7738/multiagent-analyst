import unittest

import numpy as np
import pandas as pd

from agents import agent_4


class TestFlagLeakageColumns(unittest.TestCase):
    def test_flags_name_pattern_columns(self):
        df = pd.DataFrame({
            "CustomerId": [1, 2, 3, 4, 5],
            "risk_score": [0.1, 0.2, 0.3, 0.4, 0.5],
            "predicted_label": [0, 1, 0, 1, 0],
            "revenue": [100, 200, 150, 300, 250],
        })
        corr = df.corr(method="pearson")

        flagged = agent_4.flag_leakage_columns(df, corr)

        self.assertIn("CustomerId", flagged)
        self.assertIn("risk_score", flagged)
        self.assertIn("predicted_label", flagged)

    def test_does_not_false_positive_on_whole_word_id_substring(self):
        # "Valid" contains the substring "lid" -> "id", and "Guideline" contains "id"
        # too. These must NOT be flagged just because "id" appears mid-word. Values
        # are repeated (not all-unique) so criterion 3 (pure identifier) can't also
        # explain a flag here - this isolates the name-pattern heuristic specifically.
        df = pd.DataFrame({
            "IsValid": [True, False, True, False, True, False],
            "Guideline": ["a", "b", "a", "b", "a", "b"],
            "revenue": [100, 200, 150, 300, 250, 220],
            "cost": [10, 20, 15, 30, 25, 22],
        })
        numeric = df[["revenue", "cost"]]
        corr = numeric.corr(method="pearson")

        flagged = agent_4.flag_leakage_columns(df, corr)

        self.assertNotIn("IsValid", flagged)
        self.assertNotIn("Guideline", flagged)

    def test_flags_complementary_probability_pair(self):
        # Two columns that are near-perfectly (anti-)correlated with each other and
        # near-zero with everything else - the classic "two halves of the same
        # external computation" pattern (e.g. complementary classifier probabilities).
        rng = np.random.RandomState(0)
        n = 200
        p = rng.uniform(0, 1, n)
        df = pd.DataFrame({
            "prob_class_0": p,
            "prob_class_1": 1 - p,
            "unrelated_metric": rng.uniform(0, 1, n),
            "another_metric": rng.uniform(0, 1, n),
        })
        corr = df.corr(method="pearson")

        flagged = agent_4.flag_leakage_columns(df, corr)

        self.assertIn("prob_class_0", flagged)
        self.assertIn("prob_class_1", flagged)

    def test_flags_pure_identifier_columns(self):
        df = pd.DataFrame({
            "row_uuid": [f"uuid-{i}" for i in range(10)],
            "category": ["a", "b"] * 5,
            "amount": list(range(10)),
        })
        corr = df[["amount"]].corr(method="pearson")

        flagged = agent_4.flag_leakage_columns(df, corr)

        self.assertIn("row_uuid", flagged)


class TestCorrelationExcludesLeakageColumns(unittest.TestCase):
    def test_strong_pairs_excludes_flagged_columns_and_reports_them_separately(self):
        rng = np.random.RandomState(1)
        n = 200
        customer_id = np.arange(n)
        revenue = 2 * customer_id + rng.normal(0, 5, n)
        cost = 0.6 * revenue + rng.normal(0, 5, n)
        df = pd.DataFrame({"customer_id": customer_id, "revenue": revenue, "cost": cost})

        correlation, _ = agent_4._correlation(df, {})

        flagged_columns = correlation.get("flagged_columns", [])
        strong_pairs = correlation.get("strong_pairs", [])
        excluded_pairs = correlation.get("excluded_pairs", [])

        self.assertIn("customer_id", flagged_columns)
        # revenue/cost are both unflagged and strongly correlated - stays a headline finding.
        self.assertTrue(any(
            {pair["col1"], pair["col2"]} == {"revenue", "cost"} for pair in strong_pairs
        ))
        self.assertTrue(all(
            pair["col1"] not in flagged_columns and pair["col2"] not in flagged_columns
            for pair in strong_pairs
        ))
        # customer_id's strong correlations move to the excluded appendix instead of
        # vanishing or being narrated as a headline finding.
        self.assertTrue(any(
            "customer_id" in (pair["col1"], pair["col2"]) for pair in excluded_pairs
        ))


if __name__ == "__main__":
    unittest.main()
