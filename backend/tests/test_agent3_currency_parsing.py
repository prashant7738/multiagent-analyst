import unittest

import pandas as pd

from agents import agent_2, agent_3


class TestAgent3CurrencyParsing(unittest.TestCase):
    def test_clean_currency_values_handles_common_currency_formats(self):
        df = pd.DataFrame(
            {
                "currency_col": [
                    "$1,234.56",
                    "$12,345.00",
                    "1,234",
                    "€1.234,56",
                    "$999",
                    "10.5",
                    "₹1,00,000",
                ]
            }
        )
        schema_blueprint = {
            "currency_col": {
                "semantic_tag": "currency",
                "intended_type": "float",
            }
        }
        config = {"currency_max_abs_value": 10_000_000}

        cleaned_df, notes, critical_errors = agent_3._clean_currency_values(df.copy(), schema_blueprint, config)

        self.assertEqual(critical_errors, [])
        self.assertEqual(cleaned_df["currency_col"].tolist(), [1234.56, 12345.0, 1234.0, 1234.56, 999.0, 10.5, 100000.0])
        self.assertEqual(cleaned_df["currency_col_parse_failed"].tolist(), [0, 0, 0, 0, 0, 0, 0])
        self.assertTrue(any("currency cleaned" in note for note in notes))

    def test_clean_currency_values_flags_malformed_values(self):
        df = pd.DataFrame({"currency_col": ["abc", "$1,234.56"]})
        schema_blueprint = {
            "currency_col": {
                "semantic_tag": "currency",
                "intended_type": "float",
            }
        }
        config = {"currency_max_abs_value": 10_000_000}

        cleaned_df, _, _ = agent_3._clean_currency_values(df.copy(), schema_blueprint, config)

        self.assertTrue(pd.isna(cleaned_df.loc[0, "currency_col"]))
        self.assertEqual(int(cleaned_df.loc[0, "currency_col_parse_failed"]), 1)
        self.assertEqual(int(cleaned_df.loc[1, "currency_col_parse_failed"]), 0)

    def test_currency_null_policy_is_flag_only_and_not_imputed(self):
        profile = {"missing_rate_pct": 12.5, "unique_count": 8}
        meta = {"semantic_tag": "currency", "intended_type": "float", "is_identifier": False}

        null_policy = agent_2._derive_null_policy(profile, meta)

        self.assertEqual(null_policy["action"], "flag_only")
        self.assertEqual(null_policy["threshold_pct"], 0.0)

        df = pd.DataFrame({"amount": [100.0, None, 300.0]})
        schema_blueprint = {
            "amount": {
                "semantic_tag": "currency",
                "intended_type": "float",
                "imputation_strategy": "median",
                "null_policy": null_policy,
            }
        }

        imputed_df, notes = agent_3._impute(df, schema_blueprint)

        self.assertTrue(pd.isna(imputed_df.loc[1, "amount"]))
        self.assertTrue(any("flagged only" in note for note in notes))


if __name__ == "__main__":
    unittest.main()
