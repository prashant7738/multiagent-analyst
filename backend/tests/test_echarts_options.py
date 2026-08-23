"""ECharts option builders must emit parseable JSON with formatting markers."""

import json
import unittest

from agents.echarts_options import build_echarts_option, option_json


def _spec(chart_type, data, axis=None):
    return {
        "id": f"test_{chart_type}", "family": "f", "section": "what_matters",
        "chart_type": chart_type, "title": "t", "subtitle": "", "render": "echarts",
        "why_it_matters": "w", "plain_summary": "p", "alt_text": "a",
        "data": data, "annotations": [], "axis": axis or {}, "priority": 1,
    }


class TestEchartsOptions(unittest.TestCase):
    def test_bar_option_has_category_and_value_axes(self):
        option = build_echarts_option(_spec(
            "bar", {"labels": ["A", "B"], "values": [1, 2]}, {"y_unit": "currency"}))
        self.assertEqual(option["xAxis"]["type"], "category")
        self.assertEqual(option["yAxis"]["type"], "value")
        self.assertEqual(option["__fmt"], "currency")
        json.loads(option_json(_spec("bar", {"labels": ["A"], "values": [1]})))

    def test_pareto_appends_running_total_series(self):
        option = build_echarts_option(_spec(
            "pareto",
            {"labels": ["A", "B"], "values": [8, 2], "cumulative_pct": [80.0, 100.0]},
            {"y_unit": "number"}))
        kinds = [s["type"] for s in option["series"]]
        self.assertIn("line", kinds)

    def test_line_with_fit_overlay(self):
        option = build_echarts_option(_spec(
            "line",
            {"x": ["2024-01", "2024-02"], "y": [1.0, 2.0],
             "fit": {"y_fit": [1.1, 1.9]}}, {}))
        self.assertEqual(len(option["series"]), 2)

    def test_scatter_includes_points_and_fit(self):
        option = build_echarts_option(_spec(
            "scatter",
            {"points": [[1, 2], [3, 4]], "fit": [[1, 2], [3, 4]]},
            {"x_label": "X"}))
        self.assertTrue(any(s["type"] == "scatter" for s in option["series"]))
        self.assertEqual(option["xAxis"]["name"], "X")

    def test_histbox_marks_median_and_mean(self):
        option = build_echarts_option(_spec(
            "histbox",
            {"bins": [0, 1, 2], "counts": [5, 7],
             "box": {"lo": 0.2, "q1": 0.5, "med": 1.0, "q3": 1.5, "hi": 1.8,
                     "outliers": [2.5], "mean": 1.1}},
            {}))
        series = option["series"][0]
        self.assertIn("markLine", series)
        line_values = [m["yAxis"] for m in series["markLine"]["data"]]
        self.assertIn(1.0, line_values)
        self.assertIn(1.1, line_values)

    def test_heatmap_serializes_matrix(self):
        option = build_echarts_option(_spec(
            "heatmap",
            {"rows": ["r1"], "cols": ["c1", "c2"], "matrix": [[3, 7]]}, {}))
        parsed = json.loads(option_json(_spec(
            "heatmap", {"rows": ["r1"], "cols": ["c1"], "matrix": [[9]]}, {})))
        self.assertTrue(parsed["series"][0]["data"])
        self.assertEqual(option["visualMap"]["max"], 7)


if __name__ == "__main__":
    unittest.main()
