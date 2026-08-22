import unittest

from agents import agent_5
from agents.agent_5 import ValidationLedger, _check_trend_sample_sufficiency, _validation_confidence


class TestAgent5TrendSampleSufficiency(unittest.TestCase):
    def test_reviewed_rule_reduces_confidence_separately_from_score(self):
        confidence = _validation_confidence(
            validation_score=100.0,
            review_required=True,
            insufficient_trends=[],
        )

        self.assertLess(confidence, 1.0)
        self.assertGreater(confidence, 0.0)

    def test_flags_significant_trend_with_too_few_points(self):
        state = {
            "stats": {
                "regression": {
                    "revenue": {
                        "significant": True,
                        "p_value": 0.01,
                        "r_squared": 0.99,
                        "n": 4,
                    },
                },
            },
        }
        ledger = ValidationLedger()

        insufficient = _check_trend_sample_sufficiency(state, ledger)

        self.assertEqual(insufficient, ["revenue (n=4)"])
        self.assertEqual(ledger.checks["trend_sample_sufficiency"]["status"], "warn")

    def test_passes_when_sample_size_is_sufficient(self):
        state = {
            "stats": {
                "regression": {
                    "revenue": {
                        "significant": True,
                        "p_value": 0.01,
                        "r_squared": 0.9,
                        "n": 24,
                    },
                },
            },
        }
        ledger = ValidationLedger()

        insufficient = _check_trend_sample_sufficiency(state, ledger)

        self.assertEqual(insufficient, [])
        self.assertEqual(ledger.checks["trend_sample_sufficiency"]["status"], "pass")

    def test_missing_n_is_treated_as_unknown_not_insufficient(self):
        # Older/mocked stats without an "n" field must not be penalized -
        # backward compatibility for callers that predate this check.
        state = {
            "stats": {
                "regression": {
                    "revenue": {
                        "significant": True,
                        "p_value": 0.01,
                        "r_squared": 0.9,
                    },
                },
            },
        }
        ledger = ValidationLedger()

        insufficient = _check_trend_sample_sufficiency(state, ledger)

        self.assertEqual(insufficient, [])
        self.assertEqual(ledger.checks["trend_sample_sufficiency"]["status"], "pass")

    def test_non_significant_trend_with_low_n_is_not_flagged(self):
        state = {
            "stats": {
                "regression": {
                    "revenue": {
                        "significant": False,
                        "p_value": 0.4,
                        "r_squared": 0.2,
                        "n": 3,
                    },
                },
            },
        }
        ledger = ValidationLedger()

        insufficient = _check_trend_sample_sufficiency(state, ledger)

        self.assertEqual(insufficient, [])


if __name__ == "__main__":
    unittest.main()
