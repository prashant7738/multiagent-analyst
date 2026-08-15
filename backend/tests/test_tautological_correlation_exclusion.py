import unittest

import numpy as np
import pandas as pd

from agents import agent_3, agent_4


class TestDerivationMapTracking(unittest.TestCase):
    def test_derive_business_metrics_records_profit_sources(self):
        df = pd.DataFrame({
            "revenue": [100.0, 200.0, 300.0, 400.0],
            "cost": [50.0, 90.0, 120.0, 180.0],
        })
        schema_blueprint = {
            "revenue": {"semantic_tag": "currency", "financial_role": "revenue", "intended_type": "float"},
            "cost": {"semantic_tag": "currency", "financial_role": "cost", "intended_type": "float"},
        }

        result_df, notes, derivation_map = agent_3._derive_business_metrics(df, schema_blueprint)

        self.assertIn("derived_profit", result_df.columns)
        self.assertEqual(set(derivation_map["derived_profit"]), {"revenue", "cost"})
        self.assertIn("revenue", derivation_map["derived_profit_margin_pct"])

    def test_no_derivation_map_entries_when_no_metrics_derived(self):
        df = pd.DataFrame({"unrelated_col": [1, 2, 3]})
        _, _, derivation_map = agent_3._derive_business_metrics(df, {})
        self.assertEqual(derivation_map, {})


class TestTautologicalCorrelationExclusion(unittest.TestCase):
    def _schema_with_derivation_map(self, derivation_map):
        return {"__metadata__": {"derived_metric_sources": derivation_map}}

    def test_excludes_pair_that_is_a_direct_formula_of_the_other(self):
        rng = np.random.RandomState(0)
        revenue = rng.uniform(100, 1000, 60)
        cost = rng.uniform(50, 500, 60)
        df = pd.DataFrame({
            "revenue": revenue,
            "cost": cost,
            "derived_profit": revenue - cost,
            "unrelated_metric": rng.uniform(0, 1, 60),
        })
        schema_blueprint = self._schema_with_derivation_map({
            "derived_profit": ["revenue", "cost"],
        })

        correlation, _ = agent_4._correlation(df, schema_blueprint)

        formulaic_pairs = {(p["col1"], p["col2"]) for p in correlation["formulaic_pairs"]}
        strong_pairs = {(p["col1"], p["col2"]) for p in correlation["strong_pairs"]}
        self.assertIn(("derived_profit", "revenue"), formulaic_pairs | {(b, a) for a, b in formulaic_pairs})
        self.assertNotIn(("derived_profit", "revenue"), strong_pairs)
        self.assertNotIn(("revenue", "derived_profit"), strong_pairs)

    def test_does_not_exclude_genuinely_independent_strong_pair(self):
        # Moderate (not near-perfect) correlation - strong enough to clear the
        # >=0.5 display cutoff but well under flag_leakage_columns' 0.98
        # "near-perfect" threshold, so this isolates the formulaic-pair check
        # from the unrelated leakage heuristic.
        rng = np.random.RandomState(1)
        base = rng.uniform(0, 100, 60)
        df = pd.DataFrame({
            "revenue": base,
            "cost": base * 0.6 + rng.normal(0, 25, 60),
            "unrelated_metric": rng.uniform(0, 1, 60),
        })
        schema_blueprint = self._schema_with_derivation_map({})

        correlation, _ = agent_4._correlation(df, schema_blueprint)

        strong_pairs = {(p["col1"], p["col2"]) for p in correlation["strong_pairs"]}
        self.assertTrue(
            ("revenue", "cost") in strong_pairs or ("cost", "revenue") in strong_pairs
        )
        self.assertEqual(correlation["formulaic_pairs"], [])

    def test_is_formulaic_pair_checks_both_directions(self):
        derivation_map = {"derived_profit": ["revenue", "cost"]}
        self.assertTrue(agent_4._is_formulaic_pair("derived_profit", "revenue", derivation_map))
        self.assertTrue(agent_4._is_formulaic_pair("revenue", "derived_profit", derivation_map))
        self.assertFalse(agent_4._is_formulaic_pair("revenue", "cost", derivation_map))


if __name__ == "__main__":
    unittest.main()
