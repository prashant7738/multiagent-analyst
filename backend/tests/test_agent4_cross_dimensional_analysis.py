import unittest

import numpy as np
import pandas as pd

from agents import agent_4


SCHEMA = {
    "Region": {"semantic_tag": "geographic", "intended_type": "string"},
    "Product_Category": {"semantic_tag": "categorical_label", "intended_type": "string"},
    "Customer_Segment": {"semantic_tag": "categorical_label", "intended_type": "string"},
    "Sales_Representative": {"semantic_tag": "categorical_label", "intended_type": "string"},
    "Net_Sales": {"semantic_tag": "currency", "intended_type": "float", "financial_role": "revenue"},
    "Discount_Percentage": {"semantic_tag": "percentage", "intended_type": "float"},
    "Profit_Margin": {"semantic_tag": "percentage", "intended_type": "float"},
    "Shipping_Cost": {"semantic_tag": "currency", "intended_type": "float"},
    "Returned": {"semantic_tag": "boolean", "intended_type": "boolean"},
    "Order_Date_month": {"semantic_tag": "count", "intended_type": "int"},
}


def _make_df(n=200, seed=1):
    rng = np.random.RandomState(seed)
    discount = rng.uniform(0, 0.5, n)
    # Higher discount -> higher return probability, so the quartile bucketing
    # has a real, detectable relationship to assert on.
    returned = rng.uniform(0, 1, n) < (0.05 + discount * 0.6)
    return pd.DataFrame({
        "Region": rng.choice(["North", "South", "East", "West", "Central"], size=n),
        "Product_Category": rng.choice(["Apparel", "Electronics", "Furniture"], size=n),
        "Customer_Segment": rng.choice(["Consumer", "Corporate", "Enterprise"], size=n),
        "Sales_Representative": rng.choice([f"Rep_{i}" for i in range(8)], size=n),
        "Net_Sales": rng.uniform(50, 500, size=n),
        "Discount_Percentage": discount,
        "Profit_Margin": rng.uniform(0.05, 0.4, size=n),
        "Shipping_Cost": rng.uniform(5, 50, size=n),
        "Returned": returned,
        "Order_Date_month": rng.choice(range(1, 13), size=n),
    })


class TestDiscountVsReturnRate(unittest.TestCase):
    def test_returns_quartile_buckets_with_higher_discount_higher_return_rate(self):
        df = _make_df()
        result, candidates = agent_4._discount_vs_return_rate(df, SCHEMA)

        self.assertIn("buckets", result)
        self.assertGreaterEqual(len(result["buckets"]), 2)
        self.assertEqual(len(candidates), 1)
        rates = [b["return_rate_pct"] for b in result["buckets"]]
        # buckets come out in ascending discount order - later buckets should
        # generally show a higher return rate given the synthetic relationship.
        self.assertLess(rates[0], rates[-1])

    def test_empty_when_no_returned_column(self):
        df = _make_df().drop(columns=["Returned"])
        result, candidates = agent_4._discount_vs_return_rate(df, SCHEMA)
        self.assertEqual(result, {})
        self.assertEqual(candidates, [])


class TestMarginByCategoryOverTime(unittest.TestCase):
    def test_returns_per_category_monthly_series(self):
        df = _make_df()
        result, candidates = agent_4._margin_by_category_over_time(df, SCHEMA)

        for cat in ("Apparel", "Electronics", "Furniture"):
            self.assertIn(cat, result)
            self.assertTrue(all("month" in row and "avg_margin_pct" in row for row in result[cat]))
        self.assertEqual(len(candidates), 1)

    def test_empty_without_month_column(self):
        df = _make_df().drop(columns=["Order_Date_month"])
        result, candidates = agent_4._margin_by_category_over_time(df, SCHEMA)
        self.assertEqual(result, {})
        self.assertEqual(candidates, [])


class TestDiscountAndMarginByRep(unittest.TestCase):
    def test_returns_one_row_per_rep(self):
        df = _make_df()
        result, candidates = agent_4._discount_and_margin_by_rep(df, SCHEMA)

        self.assertEqual(result["rep_column"], "Sales_Representative")
        reps_seen = {r["Sales_Representative"] for r in result["records"]}
        self.assertEqual(reps_seen, set(df["Sales_Representative"].unique()))
        self.assertEqual(len(candidates), 1)


class TestAvgOrderValueBySegment(unittest.TestCase):
    def test_returns_avg_order_value_per_segment(self):
        df = _make_df()
        result, candidates = agent_4._avg_order_value_by_segment(df, SCHEMA)

        self.assertEqual(result["segment_column"], "Customer_Segment")
        segments_seen = {r["Customer_Segment"] for r in result["records"]}
        self.assertEqual(segments_seen, set(df["Customer_Segment"].unique()))
        self.assertEqual(len(candidates), 1)


class TestShippingCostByRegion(unittest.TestCase):
    def test_disambiguates_region_from_customer_region(self):
        df = _make_df()
        df["Customer_Region"] = df["Region"]  # decoy column that also contains "region"
        schema = dict(SCHEMA)
        schema["Customer_Region"] = {"semantic_tag": "geographic", "intended_type": "string"}

        result, candidates = agent_4._shipping_cost_by_region(df, schema)

        self.assertEqual(result["region_column"], "Region")
        regions_seen = {r["Region"] for r in result["records"]}
        self.assertEqual(regions_seen, set(df["Region"].unique()))
        self.assertEqual(len(candidates), 1)


if __name__ == "__main__":
    unittest.main()
