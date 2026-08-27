"""Unit tests for rag_service document construction and bounded-memory row sampling."""

import unittest

import pandas as pd

from api.services import rag_service


class TestFactsToDocuments(unittest.TestCase):
    def _ctx(self, **overrides):
        base = {
            "dataset": {"filename": "sales.csv", "rows": 10000, "columns": 4, "quality_score": 90},
            "available_columns": {
                "region": {"intended_type": "string", "semantic_tag": "geographic"},
                "revenue": {"intended_type": "float", "semantic_tag": "currency"},
            },
            "descriptive_stats": {
                "revenue": {"mean": 5, "median": 4, "std": 1, "min": 0, "max": 9, "missing_pct": 0},
                "derived_profit_margin_pct": {"mean": 12, "median": 11, "std": 3,
                                              "min": -4, "max": 40, "missing_pct": 0},
            },
            "category_distributions": {
                "payment_method": [
                    {"payment_method": "UPI", "count": 4213, "pct": 42.13},
                    {"payment_method": "Card", "count": 3102, "pct": 31.02},
                    {"payment_method": "Cash", "count": 2685, "pct": 26.85},
                ],
            },
        }
        base.update(overrides)
        return base

    def test_emits_columns_overview_including_derived_columns(self):
        docs = rag_service._facts_to_documents(self._ctx())
        overview = [d for d in docs if d["doc_type"] == "columns_overview"]
        self.assertEqual(len(overview), 1)
        text = overview[0]["text"]
        self.assertIn("region", text)
        self.assertIn("revenue", text)
        # derived column present only via descriptive_stats, still listed
        self.assertIn("derived_profit_margin_pct", text)
        # region, revenue, derived_profit_margin_pct, payment_method (deduped union)
        self.assertEqual(set(overview[0]["metadata"]["columns"]),
                         {"region", "revenue", "derived_profit_margin_pct", "payment_method"})

    def test_columns_overview_is_always_included(self):
        self.assertIn("columns_overview", rag_service._ALWAYS_INCLUDE_FACT_TYPES)

    def test_emits_category_distribution_doc(self):
        docs = rag_service._facts_to_documents(self._ctx())
        dist = [d for d in docs if d["doc_type"] == "category_distribution"]
        self.assertEqual(len(dist), 1)
        self.assertIn("Most common: UPI", dist[0]["text"])
        self.assertEqual(dist[0]["metadata"]["categories"], 3)

    def test_skips_near_unique_category_columns(self):
        big = [{"customer": f"c{i}", "count": 1, "pct": 0.0} for i in range(250)]
        docs = rag_service._facts_to_documents(self._ctx(category_distributions={"customer": big}))
        self.assertEqual([d for d in docs if d["doc_type"] == "category_distribution"], [])

    def test_priority_map_covers_every_always_included_type(self):
        for doc_type in rag_service._ALWAYS_INCLUDE_FACT_TYPES:
            self.assertIn(doc_type, rag_service._ALWAYS_INCLUDE_PRIORITY)


class TestReadAndSampleRows(unittest.TestCase):
    def _write_csv(self, n_rows: int) -> str:
        import tempfile, os
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        pd.DataFrame({
            "id": range(n_rows),
            "status": (["A", "B", "C", "D"] * (n_rows // 4 + 1))[:n_rows],
            "amount": range(n_rows),
        }).to_csv(path, index=False)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def test_returns_full_frame_and_true_total_when_under_cap(self):
        path = self._write_csv(30)
        sampled, total = rag_service._read_and_sample_rows(path, cap=1000)
        self.assertEqual(total, 30)
        self.assertEqual(len(sampled), 30)
        self.assertEqual(list(sampled.index), list(range(30)))

    def test_caps_rows_but_reports_true_total_across_chunks(self):
        rag_service.get_settings.cache_clear()
        import os
        os.environ["RAG_READ_CHUNK_ROWS"] = "1000"
        try:
            path = self._write_csv(5000)
            sampled, total = rag_service._read_and_sample_rows(path, cap=200)
            self.assertEqual(total, 5000)
            self.assertLessEqual(len(sampled), 200)
            # indices are true file row numbers (0..4999), not per-chunk 0..999
            self.assertTrue(all(0 <= i < 5000 for i in sampled.index))
            self.assertGreater(max(sampled.index), 1000)
        finally:
            os.environ.pop("RAG_READ_CHUNK_ROWS", None)
            rag_service.get_settings.cache_clear()

    def test_every_status_category_survives_sampling(self):
        rag_service.get_settings.cache_clear()
        import os
        os.environ["RAG_READ_CHUNK_ROWS"] = "500"
        try:
            path = self._write_csv(4000)
            sampled, _ = rag_service._read_and_sample_rows(path, cap=100)
            self.assertEqual(set(sampled["status"]), {"A", "B", "C", "D"})
        finally:
            os.environ.pop("RAG_READ_CHUNK_ROWS", None)
            rag_service.get_settings.cache_clear()


if __name__ == "__main__":
    unittest.main()
