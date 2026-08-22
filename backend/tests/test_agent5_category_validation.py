import unittest

import pandas as pd

from agents.agent_5 import agent5_output_validator


class TestCategoryNormalizationValidation(unittest.TestCase):
    def test_flags_a_merge_between_two_frequent_values(self):
        state = {
            "_df_cache": pd.DataFrame({"Sales Channel": ["Offline"] * 49 + ["Online"] * 51}),
            "cleaned_df": pd.DataFrame({"Sales Channel": ["Online"] * 100}),
            "category_normalization": {
                "Sales Channel": [{"raw": "Offline", "canonical": "Online", "row_count": 49}]
            },
        }
        result = agent5_output_validator(state)

        check = result["validation_report"]["tier1_checks"]["category_normalization_safety"]
        self.assertEqual(check["status"], "fail")
        self.assertIn("frequent", check["detail"])


if __name__ == "__main__":
    unittest.main()