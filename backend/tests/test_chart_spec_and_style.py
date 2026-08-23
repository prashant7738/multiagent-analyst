"""Unit tests for the ChartSpec contract and shared presentation helpers."""

import unittest

from agents.chart_spec import (
    finalize_specs,
    make_spec,
    validate_spec,
    wrap_legacy_candidate,
)
from agents.report_style import (
    humanize_currency,
    humanize_number,
    humanize_pct,
    humanize_ratio,
    titleize,
)


class TestMakeSpec(unittest.TestCase):
    def test_minimal_bar_spec_gets_defaults(self):
        spec = make_spec(
            spec_id="rank_region", family="dimension_ranking", chart_type="bar",
            title="Revenue by Region", why_it_matters="East leads.",
            data={"labels": ["East"], "values": [10]},
        )
        self.assertEqual(spec["render"], "echarts")
        self.assertEqual(spec["section"], "what_matters")
        self.assertEqual(spec["axis"]["y_unit"], "number")
        self.assertTrue(spec["annotations"] == [])

    def test_unknown_chart_type_rejected(self):
        with self.assertRaises(ValueError):
            make_spec(
                spec_id="x", family="f", chart_type="wordcloud",
                title="t", why_it_matters="w", data={},
            )

    def test_nan_values_sanitized(self):
        spec = make_spec(
            spec_id="d", family="distribution", chart_type="histbox",
            title="t", why_it_matters="w",
            data={"bins": [float("inf"), 0], "counts": [1]},
        )
        self.assertIsNone(spec["data"]["bins"][0])


class TestValidateAndFinalize(unittest.TestCase):
    def _spec(self, spec_id, priority):
        return make_spec(
            spec_id=spec_id, family="dimension_ranking", chart_type="bar",
            title="t", why_it_matters="w", data={"labels": ["a"], "values": [1]},
            priority=priority,
        )

    def test_validate_flags_missing_fields(self):
        problems = validate_spec({"id": "", "chart_type": "bar"})
        self.assertTrue(any("title" in p for p in problems))

    def test_finalize_dedupes_sorts_and_caps(self):
        specs = [
            self._spec("low", 10), self._spec("high", 90),
            self._spec("mid", 50), self._spec("top", 99),
            self._spec("high", 5),   # duplicate id, later occurrence dropped
        ]
        out = finalize_specs(specs, cap=3)
        self.assertEqual([s["id"] for s in out], ["top", "high", "mid"])

    def test_finalize_keeps_minimal_dicts_but_skips_junk(self):
        out = finalize_specs([None, {}, {"id": "x"}], cap=5)
        self.assertEqual(out, [{"id": "x"}])


class TestWrapLegacyCandidate(unittest.TestCase):
    def test_wraps_png_candidate_with_derived_title(self):
        wrapped = wrap_legacy_candidate({
            "path": "outputs/charts/revenue_trend_regression.png",
            "family": "regression_trend", "score": 72.5,
            "reason": "R²=0.725",
        })
        self.assertEqual(wrapped["render"], "image")
        self.assertEqual(wrapped["section"], "direction")
        self.assertEqual(wrapped["priority"], 72.5)
        self.assertIn("Trend", wrapped["title"])
        self.assertTrue(wrapped["png_path"].endswith(".png"))

    def test_returns_none_without_path(self):
        self.assertIsNone(wrap_legacy_candidate({"family": "x", "score": 1}))


class TestHumanizers(unittest.TestCase):
    def test_humanize_number_scales(self):
        self.assertEqual(humanize_number(1234567), "1.23M")
        self.assertEqual(humanize_number(4200), "4.2K")
        self.assertEqual(humanize_number(42), "42")
        self.assertEqual(humanize_number(None), "—")

    def test_humanize_currency_and_pct(self):
        self.assertEqual(humanize_currency(1234567, "$"), "$1.23M")
        self.assertEqual(humanize_pct(45.06), "45.1%")
        self.assertEqual(humanize_pct(80), "80%")

    def test_ratio_zero_total_safe(self):
        self.assertEqual(humanize_ratio(3, 10), "3 out of 10")
        self.assertEqual(humanize_ratio(3, 0), "3")

    def test_titleize_preserves_acronyms_and_strips_derived(self):
        self.assertEqual(titleize("derived_total_spend"), "Total Spend")
        self.assertEqual(titleize("mrr"), "MRR")
        self.assertEqual(titleize("order_date_month"), "Order Date Month")


if __name__ == "__main__":
    unittest.main()
