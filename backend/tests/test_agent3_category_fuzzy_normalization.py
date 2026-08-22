import unittest

import pandas as pd

from agents.agent_3 import (
    _build_canonical_category_map,
    _fuzzy_canonicalize_categories,
    _levenshtein_distance,
)


class TestLevenshteinDistance(unittest.TestCase):
    def test_identical_strings(self):
        self.assertEqual(_levenshtein_distance("Complete", "Complete"), 0)

    def test_single_insertion(self):
        self.assertEqual(_levenshtein_distance("Complete", "Completed"), 1)

    def test_single_substitution(self):
        self.assertEqual(_levenshtein_distance("Cancelled", "Canceled"), 1)

    def test_unrelated_strings(self):
        self.assertGreaterEqual(_levenshtein_distance("Shipped", "Processing"), 3)


class TestBuildCanonicalCategoryMap(unittest.TestCase):
    def test_merges_near_duplicate_spellings(self):
        # "Completed" doesn't case-fold to "Complete" (they're genuinely different
        # strings) - this is exactly the docs/known_issues.md #2 example: case
        # folding alone leaves them as separate categories.
        counts = pd.Series(["Complete"] * 100 + ["Completed"] + ["Cancelled"] * 100 + ["Canceled"]).value_counts()
        mapping, merges, flagged = _build_canonical_category_map(counts)

        self.assertEqual(mapping["Completed"], "Complete")
        self.assertEqual(mapping["Canceled"], "Cancelled")
        merged_raws = {m["raw"] for m in merges}
        self.assertEqual(merged_raws, {"Completed", "Canceled"})

    def test_does_not_merge_short_antonym_like_codes(self):
        # Region codes: single letters are trivially edit-distance-1 from each
        # other, and "North"/"South"/"East"/"West" are edit-distance 2 from a
        # sibling direction - none of these should ever be silently merged.
        counts = pd.Series(
            ["North"] * 5 + ["South"] * 5 + ["East"] * 5 + ["West"] * 5 + ["N"] * 2 + ["S"] * 2
        ).value_counts()
        mapping, merges, flagged = _build_canonical_category_map(counts)

        self.assertEqual(mapping["North"], "North")
        self.assertEqual(mapping["South"], "South")
        self.assertEqual(mapping["East"], "East")
        self.assertEqual(mapping["West"], "West")
        self.assertEqual(mapping["N"], "N")
        self.assertEqual(mapping["S"], "S")
        self.assertEqual(merges, [])

    def test_flags_short_codes_with_a_near_neighbor_instead_of_guessing(self):
        # "Cc" and "Cd" share a first letter and are edit-distance 1 apart but
        # both too short to safely fuzzy-merge - flagged, not silently merged.
        counts = pd.Series(["Central"] * 5 + ["Cc"] * 3 + ["Cd"] * 2).value_counts()
        mapping, merges, flagged = _build_canonical_category_map(counts)

        self.assertEqual(mapping["Cc"], "Cc")
        self.assertEqual(mapping["Cd"], "Cd")
        self.assertEqual(merges, [])
        flagged_labels = {f["label"] for f in flagged}
        self.assertIn("Cc", flagged_labels)
        self.assertIn("Cd", flagged_labels)

    def test_does_not_merge_different_short_words_at_distance_2(self):
        # "Card" vs "Cash": same length, edit distance 2 - real, different
        # payment methods, must never be merged just because they clear the bar.
        counts = pd.Series(["Card"] * 5 + ["Cash"] * 5).value_counts()
        mapping, merges, _ = _build_canonical_category_map(counts)
        self.assertEqual(mapping["Card"], "Card")
        self.assertEqual(mapping["Cash"], "Cash")
        self.assertEqual(merges, [])

    def test_does_not_merge_different_real_words_starting_with_different_letters(self):
        # Real false positive found on live data: "Houston"/"Boston" are both
        # >=6 chars and edit-distance 2, but are two different real cities and
        # must never be merged - they don't share a first letter.
        counts = pd.Series(["Houston"] * 5 + ["Boston"] * 5).value_counts()
        mapping, merges, _ = _build_canonical_category_map(counts)
        self.assertEqual(mapping["Houston"], "Houston")
        self.assertEqual(mapping["Boston"], "Boston")
        self.assertEqual(merges, [])


class TestFuzzyCanonicalizeCategories(unittest.TestCase):
    def test_keeps_independently_valid_countries_separate(self):
        countries = ["Brunei", "Burundi", "Slovakia", "Slovenia", "Ireland", "Iceland", "Australia", "Austria"]
        df = pd.DataFrame({"Country": countries * 10})
        schema_blueprint = {"Country": {"semantic_tag": "geographic", "intended_type": "string"}}

        result_df, _, normalization_applied = _fuzzy_canonicalize_categories(df, schema_blueprint)

        self.assertEqual(result_df["Country"].tolist(), df["Country"].tolist())
        self.assertEqual(normalization_applied, {})

    def test_does_not_fuzzy_merge_binary_categories(self):
        df = pd.DataFrame({"Sales Channel": ["Offline"] * 49 + ["Online"] * 51})
        schema_blueprint = {"Sales Channel": {"semantic_tag": "categorical_label", "intended_type": "string"}}

        result_df, _, normalization_applied = _fuzzy_canonicalize_categories(df, schema_blueprint)

        self.assertEqual(result_df["Sales Channel"].value_counts().to_dict(), {"Online": 51, "Offline": 49})
        self.assertEqual(normalization_applied, {})

    def test_only_merges_a_rare_typo_into_a_dominant_category(self):
        df = pd.DataFrame({"Status": ["Complete"] * 99 + ["Complet"] + ["Cancelled", "Shipped"]})
        schema_blueprint = {"Status": {"semantic_tag": "categorical_label", "intended_type": "string"}}

        result_df, _, normalization_applied = _fuzzy_canonicalize_categories(df, schema_blueprint)

        self.assertEqual(result_df["Status"].value_counts().to_dict(), {"Complete": 100, "Cancelled": 1, "Shipped": 1})
        self.assertEqual(normalization_applied["Status"][0]["raw"], "Complet")

    def test_merges_column_tagged_categorical_label(self):
        df = pd.DataFrame({
            "Order_Status": ["Complete"] * 100 + ["Completed"] + ["Cancelled"] * 100 + ["Canceled"] + ["Shipped"],
        })
        schema_blueprint = {
            "Order_Status": {"semantic_tag": "categorical_label", "intended_type": "string"},
        }

        result_df, notes, normalization_applied = _fuzzy_canonicalize_categories(df, schema_blueprint)

        self.assertEqual(
            result_df["Order_Status"].value_counts().to_dict(),
            {"Complete": 101, "Cancelled": 101, "Shipped": 1},
        )
        self.assertIn("Order_Status", normalization_applied)
        raws = {m["raw"] for m in normalization_applied["Order_Status"]}
        self.assertEqual(raws, {"Completed", "Canceled"})
        self.assertTrue(any("fuzzy-canonicalized" in n for n in notes))

    def test_skips_identifier_and_non_categorical_columns(self):
        df = pd.DataFrame({
            "Order_ID": ["ORD-1", "ORD-2"],
            "notes_free_text": ["Complete", "Completed"],
        })
        schema_blueprint = {
            "Order_ID": {"semantic_tag": "identifier", "is_identifier": True, "intended_type": "string"},
            "notes_free_text": {"semantic_tag": "text", "intended_type": "string"},
        }

        result_df, notes, normalization_applied = _fuzzy_canonicalize_categories(df, schema_blueprint)

        self.assertEqual(result_df["Order_ID"].tolist(), ["ORD-1", "ORD-2"])
        self.assertEqual(result_df["notes_free_text"].tolist(), ["Complete", "Completed"])
        self.assertEqual(normalization_applied, {})


if __name__ == "__main__":
    unittest.main()
