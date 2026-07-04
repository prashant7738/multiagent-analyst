import unittest
from pathlib import Path

from agents.agent_1 import agent1_structural_profiler
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


if __name__ == "__main__":
    unittest.main()
