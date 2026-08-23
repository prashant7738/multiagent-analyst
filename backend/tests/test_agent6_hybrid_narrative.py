"""Hybrid narrative assembly: deterministic floor + LLM polish + jargon linter."""

import unittest

from agents.agent_6 import (
    _compose_hybrid_narrative,
    _fallback_narrative,
    _fallback_story,
    _jargon_hits,
    _lint_plain_language,
    _valid_story,
)


def _facts():
    return {
        "dataset": {"raw_rows": 300, "raw_cols": 4, "cleaned_rows": 300, "cleaned_cols": 9},
        "data_quality": {"overall_quality_score": 88.0},
        "rankings": {"region": {"top": [{"region": "East", "revenue_share_pct": 42.0}],
                                "bottom": [], "total_categories": 3}},
        "growth": {"best_month": {"month": "2024-11"}},
        "anomalies": {"unique_flagged_rows": 7, "unique_flagged_row_pct": 2.3},
        "charts": [{"id": "ranking_region_by_revenue", "title": "Revenue by Region",
                    "what_it_shows": "s"}],
    }


class TestJargonDetection(unittest.TestCase):
    def test_detects_banned_terms(self):
        self.assertTrue(_jargon_hits("The r-squared was high"))
        self.assertTrue(_jargon_hits("a z-score of 3.5"))
        self.assertTrue(_jargon_hits("Pearson correlation"))

    def test_clean_text_passes(self):
        self.assertEqual(_jargon_hits("Sales rise every November."), [])


class TestValidStory(unittest.TestCase):
    def test_accepts_complete_story(self):
        story = {"what_happened": "a", "why_it_matters": "b", "what_to_do_next": "c"}
        self.assertEqual(_valid_story(story), story)

    def test_rejects_missing_or_oversized_parts(self):
        self.assertIsNone(_valid_story({"what_happened": "a"}))
        self.assertIsNone(_valid_story({"what_happened": "", "why_it_matters": "b",
                                        "what_to_do_next": "c"}))
        huge = "x" * 901
        self.assertIsNone(_valid_story({"what_happened": huge, "why_it_matters": "b",
                                        "what_to_do_next": "c"}))


class TestHybridComposition(unittest.TestCase):
    def test_deterministic_floor_survives_llm_failure(self):
        facts = _facts()
        llm = {}  # LLM produced nothing usable
        merged = _compose_hybrid_narrative(llm, _fallback_narrative(facts), facts)
        self.assertTrue(merged["plain_language_insights"])
        self.assertTrue(merged["story"]["what_happened"])
        self.assertIn("glossary_terms", merged)

    def test_llm_extras_appended_after_deterministic_bullets(self):
        facts = _facts()
        det = _fallback_narrative(facts)
        llm = {
            "executive_summary": "Custom summary.",
            "plain_language_insights": [det["plain_language_insights"][0],  # duplicate
                                        "A genuinely fresh observation."],
            "story": {"what_happened": "H", "why_it_matters": "I", "what_to_do_next": "J"},
            "chart_captions": {
                "ranking_region_by_revenue": "Notice the East bar.",
                "made_up_chart_id": "Should be dropped.",
            },
        }
        merged = _compose_hybrid_narrative(llm, det, facts)
        bullets = merged["plain_language_insights"]
        self.assertEqual(bullets[0], det["plain_language_insights"][0])
        self.assertIn("A genuinely fresh observation.", bullets)
        self.assertNotIn("made_up_chart_id", merged["chart_captions"])
        self.assertEqual(merged["executive_summary"], "Custom summary.")
        self.assertEqual(merged["story"]["what_happened"], "H")

    def test_jargon_riddled_llm_story_falls_back(self):
        facts = _facts()
        det = _fallback_narrative(facts)
        llm = {
            "story": {"what_happened": "The r-squared improved",
                      "why_it_matters": "b", "what_to_do_next": "c"},
        }
        merged = _compose_hybrid_narrative(llm, det, facts)
        self.assertFalse(_jargon_hits(merged["story"]["what_happened"]))


class TestLintPass(unittest.TestCase):
    def test_swaps_jargon_bullet_for_deterministic_wording(self):
        facts = _facts()
        det = _fallback_narrative(facts)
        merged = {
            "plain_language_insights": ["The p-value suggests significance",
                                        *det["plain_language_insights"][:2]],
            "bottom_line": det.get("bottom_line", ""),
        }
        replaced = _lint_plain_language(merged, det)
        self.assertGreaterEqual(replaced, 1)
        for bullet in merged["plain_language_insights"]:
            self.assertEqual(_jargon_hits(bullet), [])


class TestFallbackStoryGrounded(unittest.TestCase):
    def test_story_cites_real_ranking_value(self):
        story = _fallback_story(_facts())
        self.assertIn("East", story["what_happened"])
        self.assertIn("42.0%", story["what_happened"])


if __name__ == "__main__":
    unittest.main()
