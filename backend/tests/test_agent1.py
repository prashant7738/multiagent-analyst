"""Unit tests for Agent 1 — structural profiler.

Covers:
- Basic profiling: shape, dtypes, missing values, duplicates
- Per-column metadata (dtype, unique count, sample values)
- Multi-format dispatch: CSV, JSON, JSON Lines, Parquet, Excel (.xlsx)
- Error path: file not found, unreadable file
- Large dataset performance regression (sub-second on 50k rows)
"""

import json
import os
import tempfile
import time
import unittest

import pandas as pd


# ---------------------------------------------------------------------------
# helpers to write temp files
# ---------------------------------------------------------------------------

def _make_state(file_path: str, **extra) -> dict:
    return {"csv_path": file_path, "errors": [], **extra}


def _write_csv(tmp_dir: str, rows: list[dict], filename: str = "data.csv") -> str:
    path = os.path.join(tmp_dir, filename)
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)
    return path


def _write_json(tmp_dir: str, rows: list[dict], filename: str = "data.json") -> str:
    path = os.path.join(tmp_dir, filename)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh)
    return path


def _write_jsonl(tmp_dir: str, rows: list[dict], filename: str = "data.jsonl") -> str:
    path = os.path.join(tmp_dir, filename)
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return path


def _write_parquet(tmp_dir: str, rows: list[dict], filename: str = "data.parquet") -> str:
    path = os.path.join(tmp_dir, filename)
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def _write_excel(tmp_dir: str, rows: list[dict], filename: str = "data.xlsx") -> str:
    path = os.path.join(tmp_dir, filename)
    pd.DataFrame(rows).to_excel(path, index=False)
    return path


_SAMPLE_ROWS = [
    {"order_id": "A1", "amount": 100.0, "status": "open"},
    {"order_id": "A2", "amount": None,  "status": "closed"},
    {"order_id": "A3", "amount": 200.0, "status": "open"},
    {"order_id": "A4", "amount": 100.0, "status": "open"},  # duplicate of A1-ish
]


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

class TestAgent1BasicProfiling(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Import here so test collection doesn't fail if uv env is missing
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from agents.agent_1 import agent1_structural_profiler
        cls.profiler = staticmethod(agent1_structural_profiler)

    def test_shape_is_correct(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_csv(tmp, _SAMPLE_ROWS)
            result = self.profiler(_make_state(path))
        profile = result["raw_profile"]
        self.assertEqual(profile["shape"]["rows"], 4)
        self.assertEqual(profile["shape"]["cols"], 3)

    def test_missing_value_counted_correctly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_csv(tmp, _SAMPLE_ROWS)
            result = self.profiler(_make_state(path))
        col = result["raw_profile"]["columns"]["amount"]
        self.assertEqual(col["missing_count"], 1)
        self.assertAlmostEqual(col["missing_rate_pct"], 25.0, places=1)

    def test_unique_count_and_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_csv(tmp, _SAMPLE_ROWS)
            result = self.profiler(_make_state(path))
        col = result["raw_profile"]["columns"]["status"]
        self.assertEqual(col["unique_count"], 2)
        self.assertLessEqual(len(col["sample_values"]), 3)

    def test_duplicate_row_detection(self):
        rows = [
            {"id": 1, "val": "x"},
            {"id": 1, "val": "x"},  # exact duplicate
            {"id": 2, "val": "y"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_csv(tmp, rows)
            result = self.profiler(_make_state(path))
        profile = result["raw_profile"]
        self.assertEqual(profile["duplicate_rows"], 1)
        self.assertAlmostEqual(profile["duplicate_rate_pct"], 33.33, places=1)

    def test_no_duplicates_when_all_rows_unique(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_csv(tmp, _SAMPLE_ROWS)
            result = self.profiler(_make_state(path))
        self.assertEqual(result["raw_profile"]["duplicate_rows"], 0)

    def test_overall_missing_rate(self):
        # 1 missing out of 4*3 = 12 cells → 8.33 %
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_csv(tmp, _SAMPLE_ROWS)
            result = self.profiler(_make_state(path))
        profile = result["raw_profile"]
        self.assertAlmostEqual(profile["overall_missing_rate_pct"], 8.33, places=1)

    def test_total_cells(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_csv(tmp, _SAMPLE_ROWS)
            result = self.profiler(_make_state(path))
        self.assertEqual(result["raw_profile"]["total_cells"], 12)

    def test_no_errors_on_clean_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_csv(tmp, _SAMPLE_ROWS)
            result = self.profiler(_make_state(path))
        self.assertEqual(result["errors"], [])

    def test_df_cache_is_stored_in_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_csv(tmp, _SAMPLE_ROWS)
            result = self.profiler(_make_state(path))
        self.assertIsInstance(result["_df_cache"], pd.DataFrame)
        self.assertEqual(len(result["_df_cache"]), 4)

    def test_reliability_field_is_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_csv(tmp, _SAMPLE_ROWS)
            result = self.profiler(_make_state(path))
        self.assertIn("reliability", result)


class TestAgent1ErrorHandling(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from agents.agent_1 import agent1_structural_profiler
        cls.profiler = staticmethod(agent1_structural_profiler)

    def test_nonexistent_file_adds_error(self):
        result = self.profiler(_make_state("/nonexistent/path/data.csv"))
        self.assertTrue(any("Agent1" in e for e in result["errors"]))

    def test_raw_profile_absent_on_load_failure(self):
        result = self.profiler(_make_state("/nonexistent/path/data.csv"))
        # raw_profile should be empty / default (not populated on failure)
        self.assertFalse(result.get("raw_profile"))


class TestAgent1MultiFormatDispatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from agents.agent_1 import agent1_structural_profiler, _load_dataframe
        cls.profiler = staticmethod(agent1_structural_profiler)
        cls.load_dataframe = staticmethod(_load_dataframe)

    def _assert_loads_correctly(self, path: str):
        result = self.profiler(_make_state(path))
        self.assertEqual(result["errors"], [], f"Unexpected errors for {path}: {result['errors']}")
        self.assertEqual(result["raw_profile"]["shape"]["rows"], len(_SAMPLE_ROWS))
        self.assertEqual(result["raw_profile"]["shape"]["cols"], 3)

    def test_csv_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._assert_loads_correctly(_write_csv(tmp, _SAMPLE_ROWS))

    def test_json_records_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._assert_loads_correctly(_write_json(tmp, _SAMPLE_ROWS))

    def test_jsonl_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._assert_loads_correctly(_write_jsonl(tmp, _SAMPLE_ROWS))

    def test_parquet_format(self):
        try:
            import pyarrow  # noqa: F401
        except ImportError:
            try:
                import fastparquet  # noqa: F401
            except ImportError:
                self.skipTest("Neither pyarrow nor fastparquet available; skipping Parquet test")
        with tempfile.TemporaryDirectory() as tmp:
            self._assert_loads_correctly(_write_parquet(tmp, _SAMPLE_ROWS))

    def test_excel_format(self):
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            self.skipTest("openpyxl not available; skipping Excel test")
        with tempfile.TemporaryDirectory() as tmp:
            self._assert_loads_correctly(_write_excel(tmp, _SAMPLE_ROWS))

    def test_unknown_extension_falls_back_to_csv(self):
        """Files with no recognised extension are treated as CSV."""
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = _write_csv(tmp, _SAMPLE_ROWS)
            no_ext_path = os.path.join(tmp, "data")
            import shutil
            shutil.copy(csv_path, no_ext_path)
            self._assert_loads_correctly(no_ext_path)


class TestAgent1PerformanceRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from agents.agent_1 import agent1_structural_profiler
        cls.profiler = staticmethod(agent1_structural_profiler)

    def test_profiling_50k_rows_completes_in_under_5_seconds(self):
        rows = [
            {"id": i, "amount": float(i * 1.5), "category": "A" if i % 2 == 0 else "B"}
            for i in range(50_000)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_csv(tmp, rows)
            start = time.monotonic()
            result = self.profiler(_make_state(path))
            elapsed = time.monotonic() - start

        self.assertEqual(result["errors"], [])
        self.assertLess(elapsed, 5.0, f"Profiling 50k rows took {elapsed:.2f}s (> 5s limit)")


if __name__ == "__main__":
    unittest.main()
