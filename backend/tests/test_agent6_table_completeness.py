import unittest

from agents import agent_6


class TestTableCellPopulationGuarantee(unittest.TestCase):
    def test_fully_populated_tables_pass_validation(self):
        insight_facts = {
            "top_correlations": [
                {"col1": "A", "col2": "B", "pearson_r": 0.9, "strength": "strong", "direction": "positive"},
            ],
            "formulaic_pairs": [],
            "significant_trends": [
                {"column": "Revenue", "trend": "increasing", "r_squared": 0.8, "p_value": 0.01},
            ],
            "category_normalization": [
                {"column": "Region", "raw": "Nort", "canonical": "North", "row_count": 3},
            ],
            "data_quality_detail": {"missing_values": [
                {"column": "Revenue", "missing_count": 2, "missing_pct": 1.0, "action": "median imputation"},
            ]},
            "rankings": {"Region": {"top": [{"Region": "East", "total_revenue": 100, "revenue_share_pct": 50.0}], "bottom": []}},
            "profit_breakdown": {},
        }

        agent_6._validate_no_empty_required_cells(insight_facts)  # should not raise

    def test_missing_required_cell_raises_with_table_and_column_named(self):
        insight_facts = {
            "top_correlations": [
                {"col1": "A", "col2": None, "pearson_r": 0.9, "strength": "strong", "direction": "positive"},
            ],
        }

        with self.assertRaises(AssertionError) as ctx:
            agent_6._validate_no_empty_required_cells(insight_facts)

        self.assertIn("top_correlations", str(ctx.exception))
        self.assertIn("col2", str(ctx.exception))

    def test_blank_string_cell_is_treated_as_empty(self):
        insight_facts = {
            "category_normalization": [
                {"column": "Region", "raw": "  ", "canonical": "North", "row_count": 1},
            ],
        }

        with self.assertRaises(AssertionError) as ctx:
            agent_6._validate_no_empty_required_cells(insight_facts)

        self.assertIn("category_normalization", str(ctx.exception))
        self.assertIn("raw", str(ctx.exception))

    def test_minimal_edge_case_dataset_has_no_empty_required_cells(self):
        # Very few rows, no outliers, no missing values - every optional
        # section is empty, so nothing should be validated (and nothing
        # should raise).
        insight_facts = {
            "top_correlations": [],
            "formulaic_pairs": [],
            "significant_trends": [],
            "category_normalization": [],
            "data_quality_detail": {"missing_values": []},
            "rankings": {},
            "profit_breakdown": {},
        }

        agent_6._validate_no_empty_required_cells(insight_facts)  # should not raise


if __name__ == "__main__":
    unittest.main()
