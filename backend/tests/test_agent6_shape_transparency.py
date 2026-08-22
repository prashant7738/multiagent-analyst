import unittest

import pandas as pd

from agents import agent_6


def _raw_profile_columns(cols):
    return {"columns": {c: {} for c in cols}, "shape": {"rows": 0, "cols": len(cols)}}


class TestShapeChangeTransparency(unittest.TestCase):
    def test_low_cardinality_one_hot_dataset_explains_its_own_transform_log(self):
        raw_cols = ["ID", "Category", "Revenue", "Cost"]
        cleaned_df = pd.DataFrame({
            "ID": [1, 2, 3],
            "Revenue": [100.0, 200.0, 300.0],
            "Cost": [50.0, 80.0, 120.0],
            "Category_Alpha": [1, 0, 1],
            "Category_Beta": [0, 1, 0],
            "derived_profit": [50.0, 120.0, 180.0],
        })
        schema_blueprint = {
            "Category_Alpha": {"notes": "one-hot encoded from Category"},
            "Category_Beta": {"notes": "one-hot encoded from Category"},
        }
        state = {
            "raw_shape": {"rows": 3, "cols": len(raw_cols)},
            "raw_profile": _raw_profile_columns(raw_cols),
            "cleaned_df": cleaned_df,
            "schema_blueprint": schema_blueprint,
            "column_ledger": {"row_accounting": {"exact_duplicates_removed": 5}},
        }

        explanation = agent_6._extract_shape_explanation(state)

        self.assertEqual(explanation["raw_cols"], 4)
        self.assertEqual(explanation["cleaned_cols"], 6)
        self.assertTrue(any("Category" in n and "one-hot" in n for n in explanation["column_explanations"]))
        self.assertTrue(any("derived business metrics" in n for n in explanation["column_explanations"]))
        self.assertTrue(any("5 row(s) removed as exact duplicates" in n for n in explanation["row_explanations"]))

    def test_high_cardinality_dataset_with_dates_explains_a_different_transform_log(self):
        raw_cols = ["ID", "Region", "Revenue", "Cost", "Order_Date"]
        cleaned_df = pd.DataFrame({
            "ID": [1, 2],
            "Revenue": [500.0, 700.0],
            "Cost": [200.0, 250.0],
            "Region_North": [1, 0],
            "Region_South": [0, 1],
            "Region_Other": [0, 0],
            "Order_Date_year": [2024, 2024],
            "Order_Date_month": [1, 2],
            "derived_profit": [300.0, 450.0],
        })
        schema_blueprint = {
            "Region_North": {"notes": "top-8+Other encoded from Region"},
            "Region_South": {"notes": "top-8+Other encoded from Region"},
            "Region_Other": {"notes": "top-8+Other encoded from Region"},
        }
        state = {
            "raw_shape": {"rows": 2, "cols": len(raw_cols)},
            "raw_profile": _raw_profile_columns(raw_cols),
            "cleaned_df": cleaned_df,
            "schema_blueprint": schema_blueprint,
            "column_ledger": {"row_accounting": {"rows_dropped_by_canonical_dedup": 10}},
        }

        explanation = agent_6._extract_shape_explanation(state)

        self.assertEqual(explanation["raw_cols"], 5)
        self.assertEqual(explanation["cleaned_cols"], 9)
        self.assertTrue(any("Region" in n and "one-hot" in n for n in explanation["column_explanations"]))
        self.assertTrue(any("Order_Date" in n and "date-part" in n for n in explanation["column_explanations"]))
        self.assertTrue(any(
            "10 row(s) removed as near-duplicates" in n for n in explanation["row_explanations"]
        ))

    def test_two_datasets_produce_distinct_explanations_reflecting_their_own_logs(self):
        state_a = {
            "raw_shape": {"rows": 3, "cols": 2},
            "raw_profile": _raw_profile_columns(["ID", "Category"]),
            "cleaned_df": pd.DataFrame({"ID": [1], "Category_X": [1]}),
            "schema_blueprint": {"Category_X": {"notes": "one-hot encoded from Category"}},
            "column_ledger": {"row_accounting": {}},
        }
        state_b = {
            "raw_shape": {"rows": 3, "cols": 2},
            "raw_profile": _raw_profile_columns(["ID", "Segment"]),
            "cleaned_df": pd.DataFrame({"ID": [1], "Segment_Y": [1], "Segment_Z": [0]}),
            "schema_blueprint": {
                "Segment_Y": {"notes": "one-hot encoded from Segment"},
                "Segment_Z": {"notes": "one-hot encoded from Segment"},
            },
            "column_ledger": {"row_accounting": {}},
        }

        explanation_a = agent_6._extract_shape_explanation(state_a)
        explanation_b = agent_6._extract_shape_explanation(state_b)

        self.assertNotEqual(explanation_a["column_explanations"], explanation_b["column_explanations"])
        self.assertTrue(any("Category" in n for n in explanation_a["column_explanations"]))
        self.assertTrue(any("Segment" in n for n in explanation_b["column_explanations"]))


if __name__ == "__main__":
    unittest.main()
