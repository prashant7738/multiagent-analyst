import unittest

import numpy as np
import pandas as pd

from agents import agent_4


def _make_sales_df(n=120, seed=0):
    rng = np.random.RandomState(seed)
    regions = rng.choice(["North", "South", "East", "West", "Central"], size=n)
    categories = rng.choice(["Apparel", "Electronics", "Furniture", "Office Supplies"], size=n)
    segments = rng.choice(["Consumer", "Corporate", "Enterprise"], size=n)
    reps = rng.choice([f"Rep_{i}" for i in range(10)], size=n)
    # Noisy high-differentiation column that would otherwise win the old top-3
    # race purely because one city has an outsized share of revenue.
    cities = rng.choice([f"City_{i}" for i in range(15)], size=n)
    revenue = rng.uniform(50, 500, size=n)
    revenue[cities == "City_0"] *= 6  # make City a very "differentiated" dimension
    profit = revenue * rng.uniform(0.05, 0.3, size=n)
    return pd.DataFrame({
        "Region": regions,
        "Product_Category": categories,
        "Customer_Segment": segments,
        "Sales_Representative": reps,
        "Customer_City": cities,
        "Net_Sales": revenue,
        "Profit": profit,
    })


SCHEMA = {
    "Region": {"semantic_tag": "geographic", "intended_type": "string"},
    "Product_Category": {"semantic_tag": "categorical_label", "intended_type": "string"},
    "Customer_Segment": {"semantic_tag": "categorical_label", "intended_type": "string"},
    "Sales_Representative": {"semantic_tag": "categorical_label", "intended_type": "string"},
    "Customer_City": {"semantic_tag": "categorical_label", "intended_type": "string"},
    "Net_Sales": {"semantic_tag": "currency", "intended_type": "float", "financial_role": "revenue"},
    "Profit": {"semantic_tag": "currency", "intended_type": "float"},
}


class TestPriorityRankingDimensions(unittest.TestCase):
    def test_priority_dimensions_always_get_a_ranking_slot(self):
        df = _make_sales_df()
        result, _ = agent_4._top_bottom_rankings(df, SCHEMA)

        for expected_col in ("Region", "Product_Category", "Customer_Segment", "Sales_Representative"):
            self.assertIn(expected_col, result, f"{expected_col} missing from top/bottom rankings")

    def test_priority_dimensions_always_get_a_profit_breakdown_slot(self):
        df = _make_sales_df()
        result, _ = agent_4._profit_breakdown_by_dimension(df, SCHEMA)

        for expected_col in ("Region", "Product_Category", "Customer_Segment", "Sales_Representative"):
            self.assertIn(expected_col, result, f"{expected_col} missing from profit breakdown")

    def test_selection_still_caps_total_dimensions(self):
        df = _make_sales_df()
        cat_cols = agent_4._categorical_cols(df, SCHEMA)
        selected = agent_4._select_ranking_dimensions(df, cat_cols, "Net_Sales")
        self.assertLessEqual(len(selected), agent_4.MAX_RANKING_DIMENSIONS)

    def test_find_profit_col_excludes_margin_columns(self):
        df = pd.DataFrame({
            "Profit_Margin": [0.1, 0.2, 0.3],
            "Profit": [10.0, 20.0, 30.0],
        })
        schema = {
            "Profit_Margin": {"semantic_tag": "percentage", "intended_type": "float"},
            "Profit": {"semantic_tag": "currency", "intended_type": "float"},
        }
        self.assertEqual(agent_4._find_profit_col(df, schema), "Profit")

    def test_categorical_cols_includes_geographic_tagged_columns(self):
        # Root cause of docs/known_issues.md #3 for "Region": pandas 3.x reports
        # a plain text column's dtype as literally "str" (not "object"/"string"),
        # and semantic_tag="geographic" (what Agent 2 tags Region-like columns)
        # wasn't checked at all - so on pandas 3.x, Region silently failed BOTH
        # the dtype check and the semantic_tag check and never became a ranking
        # candidate in the first place, regardless of the top-3 selection cap.
        df = pd.DataFrame({"Region": pd.array(["North", "South", "East"], dtype="str")})
        schema = {"Region": {"semantic_tag": "geographic", "intended_type": "string"}}
        self.assertIn("Region", agent_4._categorical_cols(df, schema))


if __name__ == "__main__":
    unittest.main()
