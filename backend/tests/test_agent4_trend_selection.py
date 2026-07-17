import unittest

import numpy as np
import pandas as pd

from agents import agent_4


class TestAgent4TrendSelection(unittest.TestCase):
    def test_correlation_keeps_business_metrics_and_excludes_date_parts(self):
        frame = pd.DataFrame({
            "order_date_year": [2022, 2022, 2023, 2023],
            "order_date_month": [1, 2, 1, 2],
            "order_date_quarter": [1, 1, 1, 1],
            "quantity": [1, 2, 3, 4],
            "unit_price": [10, 20, 30, 40],
            "total_sales": [10, 40, 90, 160],
            "unrelated_numeric_field": [4, 1, 3, 2],
        })

        correlation, _ = agent_4._correlation(frame, {})

        self.assertEqual(
            set(correlation["pearson"]),
            {"quantity", "unit_price", "total_sales"},
        )

    def test_regression_does_not_emit_date_parts_as_targets(self):
        frame = pd.DataFrame({
            "order_date_year": [2022, 2022, 2023, 2023],
            "order_date_month": [1, 2, 1, 2],
            "quantity": [4, 1, 3, 2],
        })

        regression, _ = agent_4._regression_trends(frame, {})

        self.assertNotIn("order_date_year", regression)
        self.assertNotIn("order_date_month", regression)
        self.assertEqual(regression["quantity"]["x_axis"], "order_date_year_month_index")
        self.assertTrue(np.isfinite(regression["quantity"]["r_squared"]))


if __name__ == "__main__":
    unittest.main()