import unittest
from pathlib import Path
import tempfile

import pandas as pd

from agents.agent_1 import agent1_structural_profiler
from agents.agent_2 import _assess_column_suitability, _derive_encoding_strategy, _infer_semantic_tag_from_metadata
from agents.agent_4 import _numeric_cols as agent4_numeric_cols
from agents.agent_4 import _numeric_cols as agent5_numeric_cols
from agents.agent_3 import agent3_preprocessor, dedup_exact_rows


class TestDedupConsistency(unittest.TestCase):
    def setUp(self):
        self.csv_path = Path(__file__).resolve().parents[1] / "sample_sales.csv"

    def test_agent3_dedup_matches_agent1_duplicate_count(self):
        state = {
            "csv_path": str(self.csv_path),
            "errors": [],
        }
        state = agent1_structural_profiler(state)

        expected_duplicates = int(state["raw_profile"]["duplicate_rows"])
        raw_df = state["_df_cache"]

        deduped_df, actual_duplicates, _samples = dedup_exact_rows(
            raw_df,
            expected_duplicate_count=expected_duplicates,
        )

        self.assertEqual(actual_duplicates, expected_duplicates)
        self.assertEqual(len(deduped_df), len(raw_df) - expected_duplicates)

    def test_dedup_mismatch_includes_duplicate_key_samples(self):
        state = {
            "csv_path": str(self.csv_path),
            "errors": [],
        }
        state = agent1_structural_profiler(state)

        expected_duplicates = int(state["raw_profile"]["duplicate_rows"])
        raw_df = state["_df_cache"]

        with self.assertRaises(ValueError) as ctx:
            dedup_exact_rows(raw_df, expected_duplicate_count=expected_duplicates + 1)

        msg = str(ctx.exception)
        self.assertIn("Dedup consistency mismatch", msg)
        self.assertIn("duplicate_key_samples=", msg)


class TestBankCsvIngestion(unittest.TestCase):
    def setUp(self):
        self.csv_path = Path(__file__).resolve().parents[1] / "bank.csv"

    def test_agent1_parses_mixed_delimiter_bank_csv_without_artificial_missingness(self):
        state = {
            "csv_path": str(self.csv_path),
            "errors": [],
        }

        state = agent1_structural_profiler(state)
        raw_profile = state["raw_profile"]

        self.assertEqual(raw_profile["shape"], {"rows": 4521, "cols": 17})
        self.assertEqual(raw_profile["total_missing"], 0)
        self.assertEqual(raw_profile["overall_missing_rate_pct"], 0.0)

    def test_agent1_populates_reliability_metadata(self):
        state = {
            "csv_path": str(self.csv_path),
            "errors": [],
        }

        state = agent1_structural_profiler(state)
        reliability = state.get("reliability", {})

        self.assertIsInstance(reliability, dict)
        self.assertIn("overall_confidence", reliability)
        self.assertIn("decision_readiness", reliability)
        self.assertIn("agent1", reliability.get("stage_confidence", {}))
        self.assertGreaterEqual(reliability["overall_confidence"], 0.0)
        self.assertLessEqual(reliability["overall_confidence"], 1.0)


class TestNumericColumnFiltering(unittest.TestCase):
    def test_analysis_helpers_ignore_raw_and_scaled_backups(self):
        import pandas as pd

        df = pd.DataFrame(
            {
                "age": [0.1, 0.2, 0.3],
                "age_raw": [30, 40, 50],
                "age_scaled": [0.1, 0.2, 0.3],
                "balance": [1.0, 2.0, 3.0],
                "balance_raw": [100, 200, 300],
                "balance_scaled": [1.0, 2.0, 3.0],
            }
        )
        schema_blueprint = {
            "age": {"is_identifier": False, "semantic_tag": "unknown"},
            "age_raw": {"is_identifier": False, "semantic_tag": "unknown"},
            "age_scaled": {"is_identifier": False, "semantic_tag": "unknown"},
            "balance": {"is_identifier": False, "semantic_tag": "unknown"},
            "balance_raw": {"is_identifier": False, "semantic_tag": "unknown"},
            "balance_scaled": {"is_identifier": False, "semantic_tag": "unknown"},
        }

        expected = ["age", "balance"]
        self.assertEqual(agent4_numeric_cols(df, schema_blueprint), expected)
        self.assertEqual(agent5_numeric_cols(df, schema_blueprint), expected)

    def test_analysis_helpers_exclude_boolean_columns_from_numeric_selection(self):
        import pandas as pd

        df = pd.DataFrame(
            {
                "is_active": [True, False, True],
                "score": [1.0, 2.0, 3.0],
            }
        )
        schema_blueprint = {
            "is_active": {"is_identifier": False, "semantic_tag": "unknown"},
            "score": {"is_identifier": False, "semantic_tag": "unknown"},
        }

        self.assertEqual(agent4_numeric_cols(df, schema_blueprint), ["score"])
        self.assertEqual(agent5_numeric_cols(df, schema_blueprint), ["score"])


class TestAgent2SuitabilityMetadata(unittest.TestCase):
    def test_agent2_infers_semantic_tag_from_column_name_and_metadata(self):
        profile = {
            "dtype": "object",
            "missing_count": 2,
            "missing_rate_pct": 0.4,
            "unique_count": 950,
            "sample_values": ["2024-01-01", "2024-01-02", "2024-01-03"],
        }

        semantic_tag = _infer_semantic_tag_from_metadata(
            column_name="Order Date",
            profile=profile,
            inferred_type="datetime",
        )

        self.assertEqual(semantic_tag, "datetime")

    def test_agent2_marks_identifier_like_columns_unsuitable_when_duplicates_are_high(self):
        profile = {
            "dtype": "object",
            "missing_count": 0,
            "missing_rate_pct": 0.0,
            "unique_count": 10,
            "sample_values": ["A-100", "A-100", "A-100"],
        }

        assessment = _assess_column_suitability(
            column_name="Customer Id",
            profile=profile,
            semantic_tag="identifier",
            intended_type="string",
            total_rows=100,
        )

        self.assertFalse(assessment["is_suitable"])
        self.assertEqual(assessment["reason_category"], "identifier_duplicates")
        self.assertGreater(assessment["duplicate_pressure_pct"], 80.0)

    def test_agent2_keeps_low_cardinality_category_suitable_even_with_duplicates(self):
        profile = {
            "dtype": "object",
            "missing_count": 1,
            "missing_rate_pct": 0.1,
            "unique_count": 5,
            "sample_values": ["Online", "Online", "Offline"],
        }

        assessment = _assess_column_suitability(
            column_name="Shipping Mode",
            profile=profile,
            semantic_tag="categorical_label",
            intended_type="string",
            total_rows=1000,
        )

        self.assertTrue(assessment["is_suitable"])
        self.assertEqual(assessment["reason_category"], "low_cardinality_category")

    def test_agent2_defaults_low_cardinality_categories_to_one_hot_encoding(self):
        profile = {
            "dtype": "object",
            "missing_count": 0,
            "missing_rate_pct": 0.0,
            "unique_count": 6,
            "sample_values": ["Online", "Retail", "Wholesale"],
        }

        strategy = _derive_encoding_strategy(
            profile=profile,
            meta={
                "semantic_tag": "categorical_label",
                "intended_type": "string",
                "is_identifier": False,
                "analysis_allowed": True,
            },
        )

        self.assertEqual(strategy["method"], "one_hot")

    def test_agent2_preserves_explicit_ordinal_encoding_order(self):
        profile = {
            "dtype": "object",
            "missing_count": 0,
            "missing_rate_pct": 0.0,
            "unique_count": 3,
            "sample_values": ["low", "medium", "high"],
        }

        strategy = _derive_encoding_strategy(
            profile=profile,
            meta={
                "semantic_tag": "categorical_label",
                "intended_type": "string",
                "is_identifier": False,
                "analysis_allowed": True,
                "encoding_strategy": {
                    "method": "ordinal",
                    "order": ["low", "medium", "high"],
                    "reason": "explicit order",
                },
            },
        )

        self.assertEqual(strategy["method"], "ordinal")
        self.assertEqual(strategy["order"], ["low", "medium", "high"])

    def test_agent1_profiles_parseability_and_agent2_uses_it_for_semantics(self):
        csv_text = """customer_id,order_date,amount
A100,2024-01-05,$10.50
A101,2024-02-01,$20.25
"""

        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as handle:
            handle.write(csv_text)
            temp_path = Path(handle.name)

        try:
            state = agent1_structural_profiler({"csv_path": str(temp_path), "errors": []})
            profile = state["raw_profile"]["columns"]

            self.assertTrue(profile["customer_id"]["candidate_key_hint"])
            self.assertGreaterEqual(profile["order_date"]["parseability"]["datetime_pct"], 100.0)
            self.assertTrue(profile["amount"]["format_hints"]["currency_like"])

            self.assertEqual(
                _infer_semantic_tag_from_metadata(
                    column_name="customer_id",
                    profile=profile["customer_id"],
                    inferred_type="string",
                ),
                "identifier",
            )
            self.assertEqual(
                _infer_semantic_tag_from_metadata(
                    column_name="order_date",
                    profile=profile["order_date"],
                    inferred_type="datetime",
                ),
                "datetime",
            )
            self.assertEqual(
                _infer_semantic_tag_from_metadata(
                    column_name="amount",
                    profile=profile["amount"],
                    inferred_type="string",
                ),
                "currency",
            )
        finally:
            temp_path.unlink(missing_ok=True)


class TestAgent3EncodingAndCanonicalDedup(unittest.TestCase):
    def test_agent3_canonicalizes_then_deduplicates_and_encodes_categories(self):
        df = pd.DataFrame(
            {
                "record_id": [1, 1],
                "shipping_mode": ["Home_Delivery", "home delivery"],
                "amount": [10, 10],
            }
        )
        raw_profile = {
            "shape": {"rows": 2, "cols": 3},
            "columns": {
                "record_id": {
                    "dtype": "int64",
                    "missing_rate_pct": 0.0,
                    "unique_count": 1,
                    "sample_values": [1, 1],
                },
                "shipping_mode": {
                    "dtype": "object",
                    "missing_rate_pct": 0.0,
                    "unique_count": 2,
                    "sample_values": ["Home_Delivery", "home delivery"],
                },
                "amount": {
                    "dtype": "float64",
                    "missing_rate_pct": 0.0,
                    "unique_count": 1,
                    "sample_values": [10, 10],
                },
            },
            "duplicate_rows": 0,
            "total_missing": 0,
            "overall_missing_rate_pct": 0.0,
        }
        schema_blueprint = {
            "record_id": {
                "intended_type": "int",
                "semantic_tag": "identifier",
                "is_identifier": True,
                "scaling_allowed": False,
                "imputation_strategy": "drop",
                "encoding_strategy": {"method": "none", "reason": "identifier"},
                "analysis_allowed": True,
            },
            "shipping_mode": {
                "intended_type": "string",
                "semantic_tag": "categorical_label",
                "is_identifier": False,
                "scaling_allowed": False,
                "imputation_strategy": "mode",
                "encoding_strategy": {"method": "one_hot", "reason": "low-cardinality category"},
                "analysis_allowed": True,
            },
            "amount": {
                "intended_type": "float",
                "semantic_tag": "unknown",
                "is_identifier": False,
                "scaling_allowed": True,
                "imputation_strategy": "median",
                "encoding_strategy": {"method": "none", "reason": "numeric"},
                "analysis_allowed": True,
            },
        }

        state = {
            "_df_cache": df,
            "raw_profile": raw_profile,
            "schema_blueprint": schema_blueprint,
            "errors": [],
        }

        result = agent3_preprocessor(state)

        cleaned_df = result["cleaned_df"]
        self.assertEqual(len(cleaned_df), 1)
        self.assertIn("shipping_mode__Home Delivery", cleaned_df.columns)
        self.assertIn("shipping_mode__Home Delivery", result["schema_blueprint"])
        self.assertFalse(result["schema_blueprint"]["shipping_mode__Home Delivery"]["analysis_allowed"])


if __name__ == "__main__":
    unittest.main()
