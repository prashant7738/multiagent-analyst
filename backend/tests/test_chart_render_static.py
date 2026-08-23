"""Static PNG twins must render for every chart_type the planner emits."""

import os
import tempfile
import unittest

import numpy as np
import pandas as pd

from agents.chart_planner import build_chart_specs
from agents.chart_render_static import render_spec_png


class TestRenderSpecPng(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.out_dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _specs(self):
        rng = np.random.default_rng(7)
        n = 300
        regions = rng.choice(["North", "South", "East", "West"], n)
        df = pd.DataFrame({
            "region": regions,
            "mrr": np.where(regions == "East", 3.0, 1.0) * rng.gamma(2, 200, n),
            "seats": rng.integers(1, 50, n).astype(float),
            "created_month": rng.integers(1, 13, n).astype(float),
        })
        stats = {
            "regression": {},
            "correlation": {"strong_pairs": [
                {"col1": "mrr", "col2": "seats", "pearson_r": 0.55}]},
            "anomaly_summary": {
                "unique_flagged_rows": 9, "unique_flagged_row_pct": 3.0,
                "prioritized_anomalies": [{"column": "mrr", "flagged_count": 6,
                                           "business_impact": "$1k"}]},
        }
        return build_chart_specs(df, {"mrr": {"financial_role": "revenue"}}, stats)

    def test_all_planned_specs_render_to_png(self):
        specs = self._specs()
        self.assertTrue(specs)
        rendered = []
        for spec in specs:
            path = render_spec_png(spec, self.out_dir)
            self.assertTrue(path, f"failed to render {spec['id']}")
            self.assertTrue(os.path.getsize(path) > 1000)
            rendered.append(path)

    def test_corrupt_spec_returns_none_instead_of_raising(self):
        bad = {"id": "bad", "chart_type": "bar", "title": "t",
               "why_it_matters": "w", "data": {}, "axis": {}}
        self.assertIsNone(render_spec_png(bad, self.out_dir))

    def test_unsupported_chart_type_returns_none(self):
        weird = dict(self.__class__ and {
            "id": "weird", "chart_type": "hologram", "title": "t",
            "why_it_matters": "w", "data": {}, "axis": {},
        })
        self.assertIsNone(render_spec_png(weird, self.out_dir))


if __name__ == "__main__":
    unittest.main()
