import unittest

import numpy as np
import pandas as pd

from agents import agent_3


def _schema(revenue_col, cost_col):
    return {
        revenue_col: {"semantic_tag": "currency", "intended_type": "float", "financial_role": "revenue"},
        cost_col: {"semantic_tag": "currency", "intended_type": "float", "financial_role": "cost"},
    }


class TestDerivedMetricReconciliation(unittest.TestCase):
    def test_profit_uses_total_cost_when_unit_cost_appears_first(self):
        revenue = pd.Series([1000.0, 1200.0, 1400.0, 1600.0, 1800.0])
        unit_cost = pd.Series([10.0, 12.0, 14.0, 16.0, 18.0])
        total_cost = pd.Series([400.0, 500.0, 600.0, 700.0, 800.0])
        df = pd.DataFrame({"Unit Cost": unit_cost, "Total Revenue": revenue,
                           "Total Cost": total_cost,
                           "Total Profit": revenue - total_cost})
        schema = {
            "Total Revenue": {"semantic_tag": "currency", "financial_role": "revenue"},
            "Unit Cost": {"semantic_tag": "currency", "financial_role": "cost"},
            "Total Cost": {"semantic_tag": "currency", "financial_role": "cost"},
        }

        result, _, derivation_map = agent_3._derive_business_metrics(df, schema)
        notes, divergences = agent_3._reconcile_derived_metrics(result, derivation_map)

        self.assertEqual(derivation_map["derived_profit"], ["Total Revenue", "Total Cost"])
        self.assertEqual(divergences, [])
        self.assertTrue(any("Reconciliation OK" in note for note in notes))

    def test_agreeing_ground_truth_column_is_not_flagged(self):
        rev = pd.Series(np.arange(100, 200, dtype=float))
        cost = pd.Series(np.arange(50, 150, dtype=float))
        df = pd.DataFrame({"Revenue": rev, "Cost": cost, "Profit": rev - cost})
        schema = _schema("Revenue", "Cost")

        df, _, derivation_map = agent_3._derive_business_metrics(df, schema)
        notes, divergences = agent_3._reconcile_derived_metrics(df, derivation_map)

        self.assertEqual(divergences, [])
        self.assertTrue(any("Reconciliation OK" in n for n in notes))

    def test_buggy_ground_truth_column_is_flagged_as_divergence(self):
        # Simulates an intentionally-wrong derived-column formula: the source
        # data's own "Profit" column reflects the true business figure, but
        # here we corrupt it far beyond tolerance so it disagrees with the
        # pipeline's derived_profit = Revenue - Cost formula.
        rev = pd.Series(np.arange(100, 200, dtype=float))
        cost = pd.Series(np.arange(50, 150, dtype=float))
        true_profit = rev - cost
        buggy_profit = true_profit * 3 + 500  # deliberately wrong
        df = pd.DataFrame({"Revenue": rev, "Cost": cost, "Profit": buggy_profit})
        schema = _schema("Revenue", "Cost")

        df, _, derivation_map = agent_3._derive_business_metrics(df, schema)
        notes, divergences = agent_3._reconcile_derived_metrics(df, derivation_map)

        self.assertEqual(len(divergences), 1)
        self.assertEqual(divergences[0]["derived_column"], "derived_profit")
        self.assertEqual(divergences[0]["matched_source_column"], "Profit")
        self.assertTrue(any("DERIVED METRIC DIVERGENCE" in n for n in notes))

    def test_full_pipeline_surfaces_divergence_as_visible_warning(self):
        rng = np.random.default_rng(7)
        n = 60
        rev = pd.Series(rng.uniform(100, 1000, size=n))
        cost = pd.Series(rng.uniform(50, 500, size=n))
        buggy_profit = (rev - cost) * 5  # deliberately wrong formula in the fixture
        df = pd.DataFrame({
            "Revenue": rev, "Cost": cost, "Profit": buggy_profit,
            "Units Sold": rng.integers(1, 50, size=n),
        })
        schema_blueprint = {
            "Revenue": {"semantic_tag": "currency", "intended_type": "float", "financial_role": "revenue"},
            "Cost": {"semantic_tag": "currency", "intended_type": "float", "financial_role": "cost"},
            "Profit": {"semantic_tag": "currency", "intended_type": "float"},
            "Units Sold": {"semantic_tag": "count", "intended_type": "int"},
        }
        state = {
            "_df_cache": df,
            "schema_blueprint": schema_blueprint,
            "raw_profile": {"duplicate_rows": 0},
        }

        result = agent_3.agent3_preprocessor(state)

        self.assertTrue(
            any("DERIVED METRIC DIVERGENCE" in e for e in result["errors"]),
            f"Expected a loud divergence warning in errors, got: {result['errors']}",
        )
        self.assertTrue(any("DERIVED METRIC DIVERGENCE" in n for n in result["preprocessing_log"]))
        self.assertTrue(any(
            r.get("diverged") for r in result["data_quality"].get("derived_metric_reconciliation", [])
        ))


if __name__ == "__main__":
    unittest.main()
