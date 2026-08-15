import unittest

from agents import agent_6


def _row(cat_col, value, revenue, share):
    return {cat_col: value, "total_revenue": revenue, "revenue_share_pct": share}


class TestRankingTableTruncationFix(unittest.TestCase):
    def test_no_category_missing_when_total_equals_four_and_limit_is_three(self):
        # Reproduces docs/known_issues.md #4: total_categories=4 with the
        # default TOP_RANKING_LIMIT=3 and Agent 4's default n=5 means Agent
        # 4's raw "top"/"bottom" lists are literally identical (both head(5)
        # and tail(5) of a 4-row frame return every row in the same
        # descending order) - independently slicing each to 3 used to render
        # ranks 1-3 twice and drop rank 4 (the true worst) entirely.
        rows = [
            _row("Region", "North", 400, 40.0),
            _row("Region", "South", 300, 30.0),
            _row("Region", "East", 200, 20.0),
            _row("Region", "West", 100, 10.0),
        ]
        data = {"top": rows, "bottom": rows, "total_categories": 4}

        sliced = agent_6._slice_top_bottom_rows("Region", data, limit=3)

        shown = {row["Region"] for row in sliced["top"] + sliced["bottom"]}
        self.assertEqual(shown, {"North", "South", "East", "West"})
        self.assertEqual(len(sliced["top"]), 3)
        self.assertEqual(len(sliced["bottom"]), 1)
        self.assertEqual(sliced["bottom"][0]["Region"], "West")

    def test_bottom_table_is_worst_first_not_a_duplicate_of_top(self):
        rows = [
            _row("Region", "North", 400, 40.0),
            _row("Region", "South", 300, 30.0),
            _row("Region", "East", 200, 20.0),
            _row("Region", "West", 100, 10.0),
        ]
        data = {"top": rows, "bottom": rows, "total_categories": 4}

        sliced = agent_6._slice_top_bottom_rows("Region", data, limit=3)

        self.assertNotEqual(
            {row["Region"] for row in sliced["top"]},
            {row["Region"] for row in sliced["bottom"]},
        )

    def test_large_category_count_keeps_existing_non_overlapping_behavior(self):
        # total_categories > 2*limit: top/bottom windows from Agent 4 already
        # don't overlap, so this must behave like the pre-fix logic (aside
        # from bottom now reading worst-first).
        top = [_row("Region", f"Top{i}", 100 - i, 10.0) for i in range(5)]
        bottom = [_row("Region", f"Bottom{i}", 10 - i, 1.0) for i in range(5)]
        data = {"top": top, "bottom": bottom, "total_categories": 20}

        sliced = agent_6._slice_top_bottom_rows("Region", data, limit=3)

        self.assertEqual([r["Region"] for r in sliced["top"]], ["Top0", "Top1", "Top2"])
        self.assertEqual([r["Region"] for r in sliced["bottom"]], ["Bottom4", "Bottom3", "Bottom2"])

    def test_extract_ranking_facts_applies_dedup_slicing(self):
        rows = [
            _row("Region", "North", 400, 40.0),
            _row("Region", "South", 300, 30.0),
            _row("Region", "East", 200, 20.0),
            _row("Region", "West", 100, 10.0),
        ]
        stats = {"top_bottom": {"Region": {"top": rows, "bottom": rows, "total_categories": 4}}}

        facts = agent_6._extract_ranking_facts(stats)

        shown = {row["Region"] for row in facts["Region"]["top"] + facts["Region"]["bottom"]}
        self.assertEqual(shown, {"North", "South", "East", "West"})

    def test_extract_profit_facts_applies_dedup_slicing(self):
        def profit_row(value, total, share):
            return {"Region": value, "total_profit": total, "profit_share_pct": share}

        rows = [profit_row("North", 40, 40.0), profit_row("South", 30, 30.0),
                profit_row("East", 20, 20.0), profit_row("West", 10, 10.0)]
        stats = {"profit_breakdown": {"Region": {"top": rows, "bottom": rows, "total_categories": 4}}}

        facts = agent_6._extract_profit_facts(stats)

        shown = {row["Region"] for row in facts["Region"]["top"] + facts["Region"]["bottom"]}
        self.assertEqual(shown, {"North", "South", "East", "West"})


if __name__ == "__main__":
    unittest.main()
