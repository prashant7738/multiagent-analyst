"""ECharts option builders for ChartSpecs.

Converts a spec's `data` payload into a pure-JSON ECharts option. Formatting
functions can't travel through JSON, so axis/tooltip formatting hints are
attached as `__fmt` markers and applied by the tiny runtime in the report
template after parsing.
"""

from __future__ import annotations

import json

from agents.report_style import CHART_COLORS, PALETTE


def build_echarts_option(spec: dict) -> dict:
    kind = spec.get("chart_type", "bar")
    data = spec.get("data") or {}
    axis = spec.get("axis") or {}

    base = {
        "__fmt": axis.get("y_unit", "number"),
        "__symbol": axis.get("symbol", ""),
        "animationDuration": 350,
        # Charts always render on white regardless of the report's light/dark theme
        # (matches the static PNG twins, which are always facecolor="white"), so
        # every chart in the report shares one background and text stays black —
        # never near-invisible dark-on-dark canvas text.
        "backgroundColor": "#ffffff",
        "textStyle": {"fontFamily": "DM Sans, Segoe UI, Helvetica Neue, Arial, sans-serif",
                      "color": "#000000"},
        "grid": {"left": 64, "right": 56, "top": 48, "bottom": axis.get("x_label") and 56 or 40,
                 "containLabel": True},
        "toolbox": {"show": True, "right": 8, "top": 0,
                    "feature": {
                        "saveAsImage": {"title": "Save image", "name": spec.get("id", "chart")},
                        "restore": {"show": False},
                    }},
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
    }

    if kind in ("bar", "pareto"):
        labels = data.get("labels") or []
        values = data.get("values") or []
        bar_data = list(values)
        if bar_data and kind != "pareto":
            # Mirror chart_render_static's semantic emphasis so screen and print agree:
            # watchlist charts flag their highest bar red (a concern), others green (a standout).
            extreme_i = max(range(len(bar_data)),
                            key=lambda i: bar_data[i] if bar_data[i] is not None else float("-inf"))
            highlight = PALETTE["accent"] if spec.get("section") == "watchlist" else PALETTE["secondary"]
            bar_data[extreme_i] = {"value": bar_data[extreme_i], "itemStyle": {"color": highlight}}
        series = [{
            "type": "bar",
            "data": bar_data,
            "itemStyle": {"color": PALETTE["primary"], "borderRadius": [3, 3, 0, 0]},
            "barMaxWidth": 46,
            # Only a plain bar chart with few bars gets on-bar value labels; a Pareto
            # already carries the running-total % on its line, and many bars make the
            # big formatted numbers ("$3.31M") collide above narrow bars. hideOverlap
            # is the safety net that drops any label that would still touch a neighbour.
            "label": {"show": kind == "bar" and len(values) <= 8, "position": "top",
                      "fontSize": 10, "color": "#000000"},
            "labelLayout": {"hideOverlap": True},
        }]
        option = {**base,
                  "xAxis": {"type": "category", "data": labels,
                            "axisLabel": {"interval": 0, "rotate": _label_rotation(labels),
                                          "fontSize": 10, "width": 110, "overflow": "truncate",
                                          "hideOverlap": True},
                            "name": axis.get("x_label"), "nameGap": 28,
                            "nameTextStyle": {"fontSize": 10, "color": "#000000"}},
                  "yAxis": {"type": "value",
                            "name": axis.get("y_label"),
                            "nameTextStyle": {"fontSize": 10, "color": "#000000"},
                            "splitLine": {"lineStyle": {"type": "dashed", "opacity": 0.4}}},
                  "series": series}
        cum = data.get("cumulative_pct")
        if kind == "pareto" and cum:
            option["series"].append({
                "type": "line", "data": cum, "yAxisIndex": 0,
                "smooth": True, "symbolSize": 6,
                "lineStyle": {"color": PALETTE["warning"], "width": 2},
                "itemStyle": {"color": PALETTE["warning"]},
                "name": "Running total %",
                "label": {"show": True, "formatter": "{c}%", "fontSize": 9,
                          "color": PALETTE["warning"]},
                "labelLayout": {"hideOverlap": True},
            })
            option["yAxis"]["max"] = max(100, max(cum) * 1.05)
        return option

    if kind == "barh":
        labels = list(reversed(data.get("labels") or []))
        values = list(reversed(data.get("values") or []))
        bar_data = list(values)
        if bar_data:
            extreme_i = max(range(len(bar_data)),
                            key=lambda i: bar_data[i] if bar_data[i] is not None else float("-inf"))
            highlight = PALETTE["accent"] if spec.get("section") == "watchlist" else PALETTE["secondary"]
            bar_data[extreme_i] = {"value": bar_data[extreme_i], "itemStyle": {"color": highlight}}
        return {**base,
                "xAxis": {"type": "value", "name": axis.get("y_label") or axis.get("x_label"),
                          "nameTextStyle": {"fontSize": 10, "color": "#000000"},
                          "splitLine": {"lineStyle": {"type": "dashed", "opacity": 0.4}}},
                "yAxis": {"type": "category", "data": labels,
                          "axisLabel": {"fontSize": 10, "width": 160, "overflow": "truncate"}},
                "series": [{"type": "bar", "data": bar_data, "barMaxWidth": 22,
                            "itemStyle": {"color": PALETTE["primary"], "borderRadius": [0, 3, 3, 0]},
                            "label": {"show": True, "position": "right", "fontSize": 9,
                                      "color": "#000000"},
                            "labelLayout": {"hideOverlap": True}}]}

    if kind == "line":
        xs, ys = data.get("x") or [], data.get("y") or []
        series = [{"type": "line", "data": ys, "smooth": True, "symbolSize": 7,
                   "lineStyle": {"color": PALETTE["primary"], "width": 2.4},
                   "itemStyle": {"color": PALETTE["primary"]}, "name": "Actual"}]
        y_fit = (data.get("fit") or {}).get("y_fit")
        if y_fit:
            series.append({"type": "line", "data": y_fit, "smooth": False, "symbol": "none",
                           "lineStyle": {"color": PALETTE["accent"], "width": 1.8,
                                         "type": "dashed"}, "name": "Overall direction"})
        return {**base,
                # grid.top (48) leaves the legend, when shown, only just enough room —
                # give it real clearance instead of trusting the two not to touch.
                "grid": {**base["grid"], "top": 68} if y_fit else base["grid"],
                "legend": {"show": bool(y_fit), "top": 0, "textStyle": {"fontSize": 10, "color": "#000000"}},
                "xAxis": {"type": "category", "data": xs,
                          "axisLabel": {"interval": _label_interval(xs), "rotate": _label_rotation(xs),
                                        "fontSize": 9}},
                "yAxis": {"type": "value", "scale": True,
                          "name": axis.get("y_label"),
                          "nameTextStyle": {"fontSize": 10, "color": "#000000"},
                          "splitLine": {"lineStyle": {"type": "dashed", "opacity": 0.4}}},
                "series": series}

    if kind == "scatter":
        points = data.get("points") or []
        fit = data.get("fit") or []
        return {**base,
                "tooltip": {"trigger": "item"},
                "xAxis": {"type": "value", "scale": True, "name": axis.get("x_label"),
                          "nameLocation": "middle", "nameGap": 30,
                          "nameTextStyle": {"fontSize": 10, "color": "#000000"},
                          "splitLine": {"lineStyle": {"type": "dashed", "opacity": 0.4}}},
                "yAxis": {"type": "value", "scale": True, "name": axis.get("y_label"),
                          "nameTextStyle": {"fontSize": 10, "color": "#000000"},
                          "splitLine": {"lineStyle": {"type": "dashed", "opacity": 0.4}}},
                "series": [
                    {"type": "scatter", "data": points, "symbolSize": 9,
                     "itemStyle": {"color": PALETTE["primary"], "opacity": 0.55}},
                    *( [{"type": "line", "data": fit, "symbol": "none", "silent": True,
                         "lineStyle": {"color": PALETTE["accent"], "width": 1.8, "type": "dashed"}}]
                       if fit else [] ),
                ]}

    if kind == "histbox":
        bins, counts = data.get("bins") or [], data.get("counts") or []
        centers = [(float(bins[i]) + float(bins[i + 1])) / 2 for i in range(len(counts))]
        box = data.get("box") or {}
        mark_area = None
        if all(box.get(k) is not None for k in ("lo", "hi")):
            mark_area = {
                "silent": True,
                "itemStyle": {"color": "rgba(22,163,74,0.08)"},
                "label": {"show": True, "position": "insideTop", "fontSize": 9,
                          "color": "#16a34a", "formatter": "middle half of records"},
                "data": [[{"coord": [box["lo"], 0]}, {"coord": [box["hi"], 0]}]],
            }
        mark_lines = []
        for key, color, name, label_pos in (("med", PALETTE["warning"], "Median", "insideEndTop"),
                                            ("mean", PALETTE["accent"], "Average", "insideEndBottom")):
            if box.get(key) is not None:
                mark_lines.append({"yAxis": box[key], "lineStyle": {"color": color, "type": "dashed"},
                                   "label": {"formatter": name, "fontSize": 9, "color": color,
                                             "position": label_pos}})
        series = {"type": "bar", "data": counts,
                  "itemStyle": {"color": PALETTE["primary"], "opacity": 0.85},
                  "barCategoryGap": "0%",
                  "tooltip": {"valueFormatter": None}}
        if mark_lines:
            series["markLine"] = {"symbol": "none", "data": mark_lines}
        if mark_area:
            series["markArea"] = mark_area
        outliers = box.get("outliers") or []
        outlier_series = []
        max_count = max(counts) if counts else 1
        if outliers:
            outlier_series.append({
                "type": "scatter", "symbolSize": 7,
                "itemStyle": {"color": PALETTE["accent"], "opacity": 0.65},
                "data": [[o, -max_count * 0.07] for o in outliers],
                "name": "Unusually high/low",
                "z": 5,
            })
        return {**base,
                "xAxis": {"type": "value", "min": min(bins), "max": max(bins),
                          "name": axis.get("x_label"), "nameLocation": "middle", "nameGap": 30,
                          "nameTextStyle": {"fontSize": 10, "color": "#000000"}},
                "yAxis": {"type": "value", "name": "Records",
                          "nameTextStyle": {"fontSize": 10, "color": "#000000"},
                          "splitLine": {"lineStyle": {"type": "dashed", "opacity": 0.4}}},
                "series": [series, *outlier_series]}

    if kind == "heatmap":
        rows, cols = data.get("rows") or [], data.get("cols") or []
        matrix = data.get("matrix") or []
        flat = [v for row in matrix for v in row]
        vmax = max(flat) if flat else 1
        series_data = [
            {"value": [c_i, r_i, count], "name": f"{rows[r_i]} × {cols[c_i]}"}
            for r_i, row in enumerate(matrix)
            for c_i, count in enumerate(row)
        ]
        return {**base,
                # The horizontal visualMap legend lives below the plot inside this
                # same fixed-height container; base.grid.bottom (40) is nowhere near
                # enough room for it (itemHeight 60 + its own labels), which made the
                # heatmap's cells/x-axis labels overlap the color-scale legend.
                "grid": {**base["grid"], "bottom": 110},
                "tooltip": {"trigger": "item", "position": "top"},
                "xAxis": {"type": "category", "data": cols,
                          "axisLabel": {"fontSize": 9, "rotate": 30},
                          "splitArea": {"show": True}},
                "yAxis": {"type": "category", "data": rows,
                          "axisLabel": {"fontSize": 9, "width": 130, "overflow": "truncate"},
                          "splitArea": {"show": True}},
                "visualMap": {"min": 0, "max": vmax, "calculable": False, "orient": "horizontal",
                              "left": "center", "bottom": 6, "itemHeight": 60,
                              "inRange": {"color": ["#fef3c7", "#d97706"]},
                              "textStyle": {"fontSize": 9, "color": "#000000"}},
                "series": [{"type": "heatmap", "data": series_data,
                            "label": {"show": vmax <= 200, "fontSize": 9},
                            "emphasis": {"itemStyle": {"shadowBlur": 4}}}]}
    return base


def option_json(spec: dict) -> str:
    """Compact JSON string safe to embed in a <script type="application/json">."""
    return json.dumps(build_echarts_option(spec), separators=(",", ":"), allow_nan=False)


# ── label helpers ─────────────────────────────────────────────────────────────

def _label_rotation(labels: list) -> int:
    longest = max((len(str(l)) for l in labels), default=0)
    n = len(labels)
    if n <= 5 and longest <= 10:
        return 0
    if longest <= 8:
        return 35
    return 45


def _label_interval(labels: list):
    return "auto" if len(labels) > 14 else 0
