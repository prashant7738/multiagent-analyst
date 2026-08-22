import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from PIL import Image

from agents import agent_4


class TestChartDimensionCap(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_dir = agent_4.CHARTS_DIR
        agent_4.CHARTS_DIR = self._tmpdir.name

    def tearDown(self):
        agent_4.CHARTS_DIR = self._original_dir
        self._tmpdir.cleanup()

    def _image_size(self, path):
        with Image.open(path) as img:
            return img.size

    def test_save_clamps_oversized_figure_to_dimension_cap(self):
        fig, ax = plt.subplots(figsize=(500, 4))
        ax.bar(range(500), range(500))
        path = agent_4._save(fig, "oversized_chart")

        width, height = self._image_size(path)
        self.assertLessEqual(width, agent_4.MAX_CHART_DIM_PX)
        self.assertLessEqual(height, agent_4.MAX_CHART_DIM_PX)

    def test_category_distribution_with_high_cardinality_stays_within_cap_and_is_top_n_other(self):
        rng = np.random.default_rng(1)
        # 1000 unique categories, non-uniform frequency
        categories = [f"cat_{i}" for i in rng.integers(0, 1000, size=5000)]
        df = pd.DataFrame({"segment": categories})
        schema = {"segment": {"semantic_tag": "categorical_label", "intended_type": "string"}}

        result, chart_candidates = agent_4._category_distributions(df, schema)

        self.assertEqual(len(chart_candidates), 1)
        width, height = self._image_size(chart_candidates[0]["path"])
        self.assertLessEqual(width, agent_4.MAX_CHART_DIM_PX)
        self.assertLessEqual(height, agent_4.MAX_CHART_DIM_PX)
        # full-fidelity stats are preserved even though the chart is grouped
        self.assertGreater(len(result["segment"]), agent_4.CATEGORY_CHART_MAX_BARS)

    def test_monthly_growth_chart_with_hundreds_of_periods_stays_within_cap(self):
        n_months = 500
        years = [2000 + (i // 12) for i in range(n_months)]
        months = [(i % 12) + 1 for i in range(n_months)]
        rng = np.random.default_rng(2)
        revenue = rng.uniform(1000, 5000, size=n_months)
        df = pd.DataFrame({
            "order_date_year": years,
            "order_date_month": months,
            "Revenue": revenue,
        })
        schema = {"Revenue": {"semantic_tag": "currency", "intended_type": "float", "financial_role": "revenue"}}

        result, chart_candidates = agent_4._growth_rates(df, schema)

        self.assertEqual(len(result["monthly"]), n_months - 1)  # dropna() drops the first NaN pct_change row
        self.assertTrue(chart_candidates)
        width, height = self._image_size(chart_candidates[0]["path"])
        self.assertLessEqual(width, agent_4.MAX_CHART_DIM_PX)
        self.assertLessEqual(height, agent_4.MAX_CHART_DIM_PX)


if __name__ == "__main__":
    unittest.main()
