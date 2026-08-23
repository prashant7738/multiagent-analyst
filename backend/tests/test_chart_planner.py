"""The de-hardcoding proof: the planner must work on ANY dataset shape.

These tests deliberately use non-sales datasets (SaaS subscriptions, support
tickets) plus a no-signal control, asserting that charts are chosen by
statistical signal — not by keyword-matched domain columns.
"""

import json
import unittest

import numpy as np
import pandas as pd

from agents.chart_planner import build_chart_specs
from agents.chart_spec import validate_spec


def _saas_df(n=400, seed=7):
    rng = np.random.default_rng(seed)
    plan = rng.choice(["basic", "pro", "enterprise"], n, p=[0.5, 0.35, 0.15])
    mult = np.where(plan == "enterprise", 4.0, np.where(plan == "pro", 2.0, 1.0))
    return pd.DataFrame({
        "plan": plan,
        "seats": rng.integers(1, 50, n).astype(float),
        "mrr": mult * rng.gamma(2, 200, n),
        "churn_risk_score": rng.uniform(0, 1, n),
    })


def _ticket_df(n=300, seed=3):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "priority": rng.choice(["low", "medium", "high"], n),
        "channel": rng.choice(["email", "chat", "phone"], n),
        "resolution_hours": rng.gamma(3, 8, n),
        "created_month": rng.integers(1, 13, n).astype(float),
    })


class TestPlannerSignalDriven(unittest.TestCase):
    def test_rankings_appear_when_signal_exists(self):
        specs = build_chart_specs(_saas_df(), {"mrr": {"financial_role": "revenue"}}, {})
        families = {s["family"] for s in specs}
        self.assertIn("dimension_ranking", families)
        top = next(s for s in specs if s["family"] == "dimension_ranking")
        # The strongest group must actually be enterprise (4x multiplier).
        self.assertEqual(top["data"]["labels"][0], "enterprise")

    def test_random_categories_are_filtered_out(self):
        rng = np.random.default_rng(11)
        n = 250
        df = pd.DataFrame({
            "noise_cat": rng.choice(["a", "b", "c"], n),
            "value": rng.normal(100, 10, n),   # independent of category
        })
        specs = build_chart_specs(df, {}, {})
        ranking_specs = [s for s in specs if s["family"] == "dimension_ranking"]
        self.assertEqual(ranking_specs, [])

    def test_non_sales_ticket_dataset_still_yields_charts(self):
        specs = build_chart_specs(_ticket_df(), {}, {})
        self.assertTrue(specs)
        for spec in specs:
            self.assertEqual(validate_spec(spec), [])
            json.dumps(spec)  # JSON-safe

    def test_no_signal_dataset_degrades_gracefully(self):
        rng = np.random.default_rng(5)
        n = 120
        df = pd.DataFrame({
            "cat": ["same"] * n,
            "num": np.full(n, 5.0),          # zero variance
        })
        specs = build_chart_specs(df, {}, {})
        self.assertIsInstance(specs, list)

    def test_payload_caps_respected(self):
        specs = build_chart_specs(_saas_df(n=2000, seed=9), {}, {})
        for spec in specs:
            points = spec.get("data", {}).get("points") or []
            if points:
                self.assertLessEqual(len(points), 400)

    def test_every_spec_has_plain_language_explanation(self):
        for spec in build_chart_specs(_saas_df(), {}, {}):
            self.assertTrue(spec["title"])
            self.assertTrue(spec["why_it_matters"])
            self.assertTrue(spec["plain_summary"])
            self.assertTrue(spec["alt_text"])

    def test_trend_uses_regression_stats_when_time_axis_present(self):
        df = _saas_df()
        df["start_year"] = 2024.0
        df["start_month"] = (np.arange(len(df)) % 12 + 1).astype(float)
        stats = {
            "regression": {
                "mrr": {"slope": 2.0, "intercept": 100.0, "r_squared": 0.42,
                        "p_value": 0.001, "significant": True, "trend": "upward",
                        "x_axis": "start_year_month_index", "n": len(df)},
            },
        }
        trends = [s for s in build_chart_specs(df, {"mrr": {"financial_role": "revenue"}}, stats)
                  if s["family"] == "trend"]
        self.assertEqual(len(trends), 1)
        self.assertIn("over time", trends[0]["title"].lower())


if __name__ == "__main__":
    unittest.main()
