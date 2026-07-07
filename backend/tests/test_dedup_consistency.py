import unittest
from pathlib import Path

from agents.agent_1 import agent1_structural_profiler
from agents.agent_4 import _numeric_cols as agent4_numeric_cols
from agents.agent_5 import _numeric_cols as agent5_numeric_cols
from agents.agent_3 import dedup_exact_rows


class TestDedupConsistency(unittest.TestCase):
    def setUp(self):
        self.csv_path = Path(__file__).resolve().parents[1] / "sample_sales.csv"

    def test_agent3_dedup_matches_agent1_duplicate_count(self):
        state = {
            "csv_path": str(self.csv_path),
            "errors": [],
        }
        state = agent1_structural_profiler(state)

        expected_duplicates = int(state["raw_profile"]["duplicate_rows"])
        raw_df = state["_df_cache"]

        deduped_df, actual_duplicates, _samples = dedup_exact_rows(
            raw_df,
            expected_duplicate_count=expected_duplicates,
        )

        self.assertEqual(actual_duplicates, expected_duplicates)
        self.assertEqual(len(deduped_df), len(raw_df) - expected_duplicates)

    def test_dedup_mismatch_includes_duplicate_key_samples(self):
        state = {
            "csv_path": str(self.csv_path),
            "errors": [],
        }
        state = agent1_structural_profiler(state)

        expected_duplicates = int(state["raw_profile"]["duplicate_rows"])
        raw_df = state["_df_cache"]

        with self.assertRaises(ValueError) as ctx:
            dedup_exact_rows(raw_df, expected_duplicate_count=expected_duplicates + 1)

        msg = str(ctx.exception)
        self.assertIn("Dedup consistency mismatch", msg)
        self.assertIn("duplicate_key_samples=", msg)


class TestBankCsvIngestion(unittest.TestCase):
    def setUp(self):
        self.csv_path = Path(__file__).resolve().parents[1] / "bank.csv"

    def test_agent1_parses_mixed_delimiter_bank_csv_without_artificial_missingness(self):
        state = {
            "csv_path": str(self.csv_path),
            "errors": [],
        }

        state = agent1_structural_profiler(state)
        raw_profile = state["raw_profile"]

        self.assertEqual(raw_profile["shape"], {"rows": 4521, "cols": 17})
        self.assertEqual(raw_profile["total_missing"], 0)
        self.assertEqual(raw_profile["overall_missing_rate_pct"], 0.0)


class TestNumericColumnFiltering(unittest.TestCase):
    def test_analysis_helpers_ignore_raw_and_scaled_backups(self):
        import pandas as pd

        df = pd.DataFrame(
            {
                "age": [0.1, 0.2, 0.3],
                "age_raw": [30, 40, 50],
                "age_scaled": [0.1, 0.2, 0.3],
                "balance": [1.0, 2.0, 3.0],
                "balance_raw": [100, 200, 300],
                "balance_scaled": [1.0, 2.0, 3.0],
            }
        )
        schema_blueprint = {
            "age": {"is_identifier": False, "semantic_tag": "unknown"},
            "age_raw": {"is_identifier": False, "semantic_tag": "unknown"},
            "age_scaled": {"is_identifier": False, "semantic_tag": "unknown"},
            "balance": {"is_identifier": False, "semantic_tag": "unknown"},
            "balance_raw": {"is_identifier": False, "semantic_tag": "unknown"},
            "balance_scaled": {"is_identifier": False, "semantic_tag": "unknown"},
        }

        expected = ["age", "balance"]
        self.assertEqual(agent4_numeric_cols(df, schema_blueprint), expected)
        self.assertEqual(agent5_numeric_cols(df, schema_blueprint), expected)


if __name__ == "__main__":
    unittest.main()
