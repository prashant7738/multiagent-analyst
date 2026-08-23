"""Static PNG renderer for ChartSpecs (print / PDF path).

Interactive ECharts canvases can't be captured by WeasyPrint, so every
spec that renders interactively gets a deterministic matplotlib twin here.
Both paths read the SAME spec dict, so screen and print always agree.

Usage:
    png_path = render_spec_png(spec, out_dir)   # returns path or None
"""

from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

from agents.report_style import CHART_COLORS, PALETTE, humanize_number, safe_filename_component


def render_spec_png(spec: dict, out_dir: str) -> str | None:
    """Render one ChartSpec to `<out_dir>/static_<id>.png`. Best-effort."""
    try:
        os.makedirs(out_dir, exist_ok=True)
        safe_id = safe_filename_component(spec.get("id", "chart"))
        out_path = os.path.join(out_dir, f"static_{safe_id}.png")
        _draw(spec, out_path)
        return out_path if os.path.exists(out_path) else None
    except Exception:  # noqa: BLE001 — print fallback must never break the report
        return None


def _formatter(axis_cfg: dict):
    unit = axis_cfg.get("y_unit", "number")
    symbol = axis_cfg.get("symbol", "") or ""

    def fmt(value, _pos=None):
        if unit == "percent":
            return f"{humanize_number(value)}%"
        if unit == "currency":
            return f"{symbol}{humanize_number(value)}"
        return humanize_number(value)
    return fmt


def _style(fig, ax, spec, axis_cfg, tight: bool = True):
    ax.set_title(spec.get("title", ""), fontsize=13, fontweight="bold", pad=14)
    subtitle = spec.get("subtitle", "")
    if subtitle:
        ax.text(0.5, 1.015, subtitle, transform=ax.transAxes,
                ha="center", va="bottom", fontsize=9, color="#6b7280")
    if axis_cfg.get("x_label"):
        ax.set_xlabel(axis_cfg["x_label"], fontsize=10)
    if axis_cfg.get("y_label"):
        ax.set_ylabel(axis_cfg["y_label"], fontsize=10)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_formatter(axis_cfg)))
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    if tight:
        fig.tight_layout()


def _rotate_labels(ax, labels):
    if len(labels) > 6:
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=40, ha="right", fontsize=8)
    else:
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, fontsize=9)


def _draw(spec: dict, out_path: str) -> None:
    kind = spec.get("chart_type", "bar")
    data = spec.get("data") or {}
    axis_cfg = spec.get("axis") or {}

    fig = plt.figure(figsize=(8, 4.4), facecolor="white")

    if kind in ("bar", "pareto"):
        labels = list(data.get("labels") or [])
        values = list(data.get("values") or [])
        if not labels or len(values) != len(labels):
            raise ValueError("bar data missing")
        ax = fig.add_subplot(111)
        colors = [PALETTE["primary"]] * len(values)
        if values:
            top_i = int(np.argmax(values))
            colors[top_i] = PALETTE["accent"] if kind != "pareto" else PALETTE["primary"]
        ax.bar(range(len(values)), values, color=colors, alpha=0.88)
        _rotate_labels(ax, labels)
        if kind == "pareto":
            cum = data.get("cumulative_pct") or []
            if len(cum) == len(values):
                ax2 = ax.twinx()
                ax2.plot(range(len(cum)), cum, color=PALETTE["warning"],
                         marker="o", linewidth=2, markersize=5, label="Running total %")
                ax2.set_ylim(0, 108)
                ax2.set_ylabel("Cumulative share", fontsize=9)
                ax2.tick_params(labelsize=8)
                ax2.legend(fontsize=8, loc="lower right")
        _style(fig, ax, spec, axis_cfg)

    elif kind == "barh":
        labels = list(data.get("labels") or [])
        values = list(data.get("values") or [])
        if not labels or len(values) != len(labels):
            raise ValueError("barh data missing")
        ax = fig.add_subplot(111)
        ypos = np.arange(len(values))[::-1]
        ax.barh(ypos, values, color=[PALETTE["primary"]] * len(values), alpha=0.85, height=0.62)
        ax.set_yticks(ypos)
        ax.set_yticklabels(labels, fontsize=9)
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(_formatter(axis_cfg)))
        ax.grid(axis="x", linestyle="--", alpha=0.35)
        _style(fig, ax, spec, axis_cfg)

    elif kind == "line":
        xs, ys = list(data.get("x") or []), list(data.get("y") or [])
        if not xs or len(xs) != len(ys):
            raise ValueError("line data missing")
        ax = fig.add_subplot(111)
        ax.plot(range(len(xs)), ys, color=PALETTE["primary"], marker="o",
                linewidth=2.2, markersize=4, label="Actual")
        y_fit = ((data.get("fit") or {}).get("y_fit") or [])
        if len(y_fit) == len(xs):
            ax.plot(range(len(xs)), y_fit, "--", color=PALETTE["accent"],
                    linewidth=1.8, label="Overall direction")
            ax.legend(fontsize=8, loc="best")
        _rotate_labels(ax, [str(x) for x in xs])
        _style(fig, ax, spec, axis_cfg)

    elif kind == "scatter":
        pts = np.asarray(data.get("points") or [], dtype=float)
        if pts.size == 0 or pts.shape[1] != 2:
            raise ValueError("scatter data missing")
        ax = fig.add_subplot(111)
        ax.scatter(pts[:, 0], pts[:, 1], s=16, alpha=0.55,
                   color=PALETTE["primary"], edgecolors="none")
        fit = np.asarray((data.get("fit") or []), dtype=float)
        if fit.shape == (2, 2):
            ax.plot(fit[:, 0], fit[:, 1], "--", linewidth=1.8, color=PALETTE["accent"])
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(_formatter(axis_cfg)))
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(_formatter(axis_cfg)))
        ax.grid(linestyle="--", alpha=0.35)
        _style(fig, ax, spec, axis_cfg)

    elif kind == "histbox":
        bins = list(data.get("bins") or [])
        counts = list(data.get("counts") or [])
        box = data.get("box") or {}
        if len(bins) < 2 or len(counts) != len(bins) - 1:
            raise ValueError("histbox data missing")
        gs = fig.add_gridspec(2, 1, height_ratios=[3, 1], hspace=0.08)
        axh = fig.add_subplot(gs[0])
        axh.stairs(counts, bins, fill=True, color=PALETTE["primary"], alpha=0.82)
        has_stat_lines = False
        for stat_key, color, ls in (("mean", PALETTE["accent"], "--"), ("median", PALETTE["warning"], "-")):
            v = box.get(stat_key)
            if v is not None:
                axh.axvline(v, color=color, linestyle=ls, linewidth=1.6, label=f"{stat_key.capitalize()}")
                has_stat_lines = True
        if has_stat_lines:
            axh.legend(fontsize=8)
        _style(fig, axh, spec, axis_cfg, tight=False)
        fig.subplots_adjust(top=0.86)
        axb = fig.add_subplot(gs[1], sharex=axh)
        bx_stats = {
            "med": box.get("med"), "q1": box.get("q1"), "q3": box.get("q3"),
            "whislo": box.get("lo"), "whishi": box.get("hi"),
            "fliers": list(box.get("outliers") or []),
        }
        if all(bx_stats[k] is not None for k in ("med", "q1", "q3")):
            axb.bxp([bx_stats], vert=False, patch_artist=True, widths=0.7,
                    boxprops={"facecolor": "#bfdbfe", "alpha": 0.9},
                    medianprops={"color": PALETTE["warning"], "linewidth": 2},
                    flierprops={"marker": "o", "markersize": 4,
                                "markerfacecolor": PALETTE["accent"], "alpha": 0.7})
        axb.set_yticks([])
        axb.set_ylabel("")
        axb.tick_params(labelsize=8)

    elif kind == "heatmap":
        rows, cols = list(data.get("rows") or []), list(data.get("cols") or [])
        matrix = np.asarray(data.get("matrix") or [], dtype=float)
        if matrix.size == 0 or matrix.shape != (len(rows), len(cols)):
            raise ValueError("heatmap data missing")
        ax = fig.add_subplot(111)
        image = ax.imshow(matrix, cmap="Blues", aspect="auto")
        ax.set_xticks(range(len(cols)))
        ax.set_xticklabels([str(c)[:14] for c in cols], rotation=30, ha="right", fontsize=8)
        ax.set_yticks(range(len(rows)))
        ax.set_yticklabels([str(r)[:18] for r in rows], fontsize=8)
        if matrix.size <= 64:
            thresh = matrix.max() * 0.6 if matrix.max() else 1
            for i in range(matrix.shape[0]):
                for j in range(matrix.shape[1]):
                    ax.text(j, i, humanize_number(matrix[i, j]), ha="center", va="center",
                            fontsize=7, color="white" if matrix[i, j] > thresh else "#374151")
        cbar = fig.colorbar(image, ax=ax, shrink=0.8)
        cbar.ax.tick_params(labelsize=7)
        ax.grid(False)
        _style(fig, ax, spec, {**axis_cfg, "y_unit": "number"})

    else:
        raise ValueError(f"unsupported chart_type '{kind}'")

    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
