import unittest

import numpy as np
import pandas as pd

from agents import agent_3, agent_4, agent_6


class TestStructuralTrustChecks(unittest.TestCase):
    def test_temporal_sequence_violations_are_reported(self):
        df = pd.DataFrame({
            "Order Date": pd.to_datetime(["2026-01-10", "2026-01-10", "2026-01-10"]),
            "Ship Date": pd.to_datetime(["2026-01-11", "2026-01-09", "2026-01-11"]),
            "Delivery Date": pd.to_datetime(["2026-01-12", "2026-01-12", "2026-01-08"]),
        })
        schema = {column: {"semantic_tag": "datetime", "intended_type": "datetime"}
                  for column in df.columns}

        result = agent_4._detect_data_quality_issues(df, schema)

        self.assertEqual(result["issues_by_rule"]["temporal_sequence_violated"], 2)
        self.assertEqual(result["data_quality_issue_rows"], 2)

    def test_near_tautological_derived_pair_is_quality_signal_not_strong_pair(self):
        df = pd.DataFrame({
            "derived_revenue": [100.0, 200.0, 300.0, 400.0],
            "derived_profit": [99.9, 199.8, 299.7, 399.6],
            "other_metric": [4.0, 1.0, 3.0, 2.0],
        })
        schema = {
            "__metadata__": {"derived_metric_sources": {
                "derived_revenue": ["sales"], "derived_profit": ["sales", "cost"]
            }},
            "derived_revenue": {"semantic_tag": "currency"},
            "derived_profit": {"semantic_tag": "currency"},
            "other_metric": {"semantic_tag": "count"},
        }

        result, _ = agent_4._correlation(df, schema)

        self.assertTrue(result["derived_quality_flags"])
        self.assertFalse(any(
            {pair["col1"], pair["col2"]} == {"derived_revenue", "derived_profit"}
            for pair in result["strong_pairs"]
        ))


class TestRankingAndTextSignalQuality(unittest.TestCase):
    def test_near_equal_ranking_is_marked_non_material(self):
        df = pd.DataFrame({
            "Category": ["Electronics", "Home", "Fashion"] * 4,
            "Revenue": [35, 34, 30] * 4,
        })
        schema = {
            "Category": {"semantic_tag": "categorical_label", "intended_type": "string"},
            "Revenue": {"semantic_tag": "currency", "intended_type": "float"},
        }

        rankings, _ = agent_4._top_bottom_rankings(df, schema)

        self.assertFalse(rankings["Category"]["is_material"])
        self.assertLess(rankings["Category"]["effect_size_ratio"], 1.5)

    def test_repetitive_token_text_field_is_flagged_and_excluded_from_categories(self):
        df = pd.DataFrame({
            "Product Name": ["without", "school", "step", "bit", "trouble"] * 8,
            "Revenue": np.arange(40, dtype=float),
        })
        schema = {
            "Product Name": {"semantic_tag": "categorical_label", "intended_type": "string"},
            "Revenue": {"semantic_tag": "currency", "intended_type": "float"},
        }

        flags = agent_3._detect_unusable_text_fields(df, schema)

        self.assertIn("Product Name", flags)
        self.assertTrue(flags["Product Name"]["likely_unusable"])


class TestNarrativeTrustSignals(unittest.TestCase):
    def test_contradictory_story_sections_are_detected(self):
        narrative = {
            "story": {
                "what_happened": "The data has serious quality issues and needs cleaning.",
                "why_it_matters": "The data is solid enough to act on with confidence.",
            }
        }

        contradictions = agent_6._detect_narrative_contradictions(narrative)

        self.assertTrue(contradictions)
        self.assertEqual(contradictions[0]["sections"], ["story.what_happened", "story.why_it_matters"])

    def test_narrative_evidence_tags_are_normalized(self):
        narrative = {
            "key_findings": ["A plain finding"],
            "plain_language_insights": [{"claim": "A direct observation", "type": "fact", "confidence": "high"}],
        }

        normalized = agent_6._normalize_narrative_evidence_tags(narrative)

        self.assertEqual(normalized["key_findings"][0]["type"], "fact")
        self.assertEqual(normalized["plain_language_insights"][0]["confidence"], "high")


if __name__ == "__main__":
    unittest.main()
