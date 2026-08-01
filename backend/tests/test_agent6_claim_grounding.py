import unittest

from agents import agent_6


class TestAgent6ClaimGrounding(unittest.TestCase):
    def test_grounded_claim_matches_known_fact(self):
        insight_facts = {
            "top_correlations": [{"col1": "revenue", "col2": "cost", "pearson_r": 0.97}],
            "dataset": {"rows": 340},
        }
        narrative = {
            "executive_summary": "Revenue and cost correlate at r=0.97 across 340 rows.",
            "key_findings": [],
        }

        report = agent_6._check_narrative_grounding(insight_facts, narrative)

        self.assertEqual(report["claims_checked"], 2)
        self.assertEqual(report["claims_grounded"], 2)
        self.assertEqual(report["claims_flagged"], 0)
        self.assertEqual(report["confidence"], 1.0)

    def test_hallucinated_claim_is_flagged(self):
        insight_facts = {
            "top_correlations": [{"col1": "revenue", "col2": "cost", "pearson_r": 0.97}],
        }
        narrative = {
            "executive_summary": "Revenue grew by 58% year over year, a remarkable result.",
            "key_findings": [],
        }

        report = agent_6._check_narrative_grounding(insight_facts, narrative)

        self.assertEqual(report["claims_checked"], 1)
        self.assertEqual(report["claims_grounded"], 0)
        self.assertEqual(report["claims_flagged"], 1)
        self.assertEqual(report["flagged_examples"][0]["value"], 58.0)

    def test_small_ordinal_numbers_are_not_treated_as_claims(self):
        insight_facts = {"dataset": {"rows": 340}}
        narrative = {
            "executive_summary": "The top 3 categories drive most of the value.",
            "key_findings": [],
        }

        report = agent_6._check_narrative_grounding(insight_facts, narrative)

        self.assertEqual(report["claims_checked"], 0)
        self.assertEqual(report["confidence"], 1.0)

    def test_no_claims_yields_full_confidence(self):
        report = agent_6._check_narrative_grounding({}, {"executive_summary": "", "key_findings": []})
        self.assertEqual(report["claims_checked"], 0)
        self.assertEqual(report["confidence"], 1.0)


if __name__ == "__main__":
    unittest.main()
