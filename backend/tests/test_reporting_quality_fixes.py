import unittest

from agents import agent_6


class TestDataQualityDetailFacts(unittest.TestCase):
    def test_extracts_duplicate_actions_and_missing_value_details(self):
        state = {
            "raw_profile": {
                "columns": {
                    "quantity": {"missing_count": 2, "missing_pct": 20.0},
                    "status": {"missing_count": 1, "missing_pct": 10.0},
                    "complete": {"missing_count": 0, "missing_pct": 0.0},
                }
            },
            "schema_blueprint": {
                "quantity": {"null_policy": {"action": "impute_median"}},
                "status": {"null_policy": {"action": "flag_only"}},
            },
            "data_quality": {
                "overall_quality_score": 91.0,
                "raw_completeness_pct": 90.0,
                "raw_missing_pct": 10.0,
                "remaining_null_pct": 2.0,
            },
            "column_ledger": {
                "row_accounting": {
                    "exact_duplicates_removed": 3,
                    "rows_dropped_by_canonical_dedup": 2,
                    "rows_dropped_by_imputation": 1,
                }
            },
        }

        facts = agent_6._extract_quality_facts(state)

        self.assertEqual(facts["duplicates"]["exact_count"], 3)
        self.assertEqual(facts["duplicates"]["near_duplicate_count"], 2)
        self.assertEqual(facts["duplicates"]["rows_dropped_for_missing_values"], 1)
        details = {item["column"]: item for item in facts["missing_values"]}
        self.assertEqual(details["quantity"]["count"], 2)
        self.assertEqual(details["quantity"]["action"], "impute_median")
        self.assertEqual(details["status"]["action"], "flag_only")
        self.assertEqual(details["complete"]["action"], "left as null")


if __name__ == "__main__":
    unittest.main()
