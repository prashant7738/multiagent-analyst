"""ChartSpec — the data-driven chart contract shared across the pipeline.

Agent 4 (statistics) and the chart planner emit ChartSpec dicts instead of
bare PNG paths. Each spec fully describes one visualization:

  * WHAT it shows        -> title / subtitle / why_it_matters (plain English)
  * THE DATA behind it   -> `data` (small pre-aggregated series, never raw rows)
  * HOW to draw it       -> chart_type + axis formatting hints
  * WHY it earned a slot -> priority score from signal strength

Two render targets consume the same spec:
  * interactive ECharts option JSON built by the report template (screen)
  * a matplotlib PNG rendered by agents/chart_render_static.py (print/PDF)

Legacy PNG-only charts (families whose plotting still lives inside agent_4)
are wrapped as render="image" specs so the gallery stays uniform.
"""

from __future__ import annotations

import math
import re

CHART_TYPES = frozenset({
    "bar",            # vertical bars: {labels, values}
    "barh",           # horizontal bars: {labels, values}
    "line",           # time/aggregated line: {x, y} (+ optional fit.y_fit)
    "scatter",        # points + fit line: {points, fit}
    "histbox",        # histogram + box stats: {bins, counts, box}
    "heatmap",        # matrix: {rows, cols, matrix}
    "pareto",         # bars + cumulative % line: {labels, values, cumulative_pct}
})

# Which report section each family belongs to. Families missing here fall
# back to "explore" (the general findings section).
SECTION_BY_FAMILY = {
    "dimension_ranking": "what_matters",
    "pareto": "what_matters",
    "distribution": "shape",
    "trend": "direction",
    "seasonality": "direction",
    "correlation_scatter": "relationships",
    "correlation_heatmap": "relationships",
    "crosstab": "relationships",
    "anomaly_overlay": "watchlist",
    # legacy agent_4 families
    "regression_trend": "direction",
    "revenue_histogram": "shape",
    "distribution_boxplot": "shape",
    "growth_rates": "direction",
    "top_bottom": "what_matters",
    "profit_breakdown": "what_matters",
    "seasonality_heatmap": "direction",
    "category_distribution": "shape",
    "discount_return_rate": "watchlist",
    "category_margin_trend": "direction",
    "rep_discount_margin": "watchlist",
    "segment_order_value": "what_matters",
    "region_shipping_cost": "watchlist",
    "shipping_lead_time": "watchlist",
}

AXIS_UNITS = frozenset({"number", "currency", "percent", "count"})


def make_spec(
    *,
    spec_id: str,
    family: str,
    chart_type: str,
    title: str,
    why_it_matters: str,
    data: dict,
    subtitle: str = "",
    plain_summary: str = "",
    alt_text: str = "",
    annotations: list | None = None,
    axis: dict | None = None,
    priority: float = 0.0,
    png_path: str | None = None,
) -> dict:
    """Build a validated ChartSpec dict with all optional fields normalized."""
    if chart_type not in CHART_TYPES:
        raise ValueError(f"Unknown chart_type '{chart_type}' for spec '{spec_id}'")
    spec = {
        "id": str(spec_id),
        "family": family,
        "section": SECTION_BY_FAMILY.get(family, "what_matters"),
        "chart_type": chart_type,
        "render": "image" if (png_path and not data) else "echarts",
        "title": title,
        "subtitle": subtitle or "",
        "why_it_matters": why_it_matters,
        "plain_summary": plain_summary or why_it_matters,
        "alt_text": alt_text or title,
        "data": _sanitize_data(data),
        "annotations": [a for a in (annotations or []) if a],
        "axis": _normalize_axis(axis or {}),
        "priority": round(float(priority), 2),
    }
    if png_path:
        spec["png_path"] = png_path
    return spec


# Legacy agent_4 charts don't get a narrated description from the planner or the
# LLM, so without this they'd show only the terse `reason` score string (e.g.
# "max |pearson r|=0.97") as if it were an explanation of the chart. One plain-
# language sentence per family so every chart says what it actually shows.
_FAMILY_BLURBS = {
    "correlation_heatmap": "This heatmap shows how strongly every pair of numeric columns moves together — darker cells mean a stronger relationship, pale cells mean little to no connection.",
    "correlation_scatter": "Each dot is one record, plotted by its two values. The dashed line is the general trend — dots hugging it closely mean a dependable relationship.",
    "growth_rates_monthly": "How this metric changed from one month to the next, so you can spot which periods grew and which pulled back.",
    "growth_rates_quarterly": "How this metric changed from one quarter to the next, so you can spot which periods grew and which pulled back.",
    "top_bottom_ranking": "The categories that contribute the most and the least, ranked side by side so the gap between them is easy to see.",
    "profit_breakdown": "How profit is distributed across categories, highlighting which ones carry the business and which barely contribute.",
    "seasonality_monthly": "How this metric typically behaves across the calendar year, so seasonal highs and lows stand out.",
    "seasonality_quarterly": "How this metric typically behaves across quarters, so seasonal highs and lows stand out.",
    "category_distribution": "How often each category appears in your data — tall bars are the common cases, short bars are the rare ones.",
    "distribution_boxplot": "The spread of your numeric columns side by side — the box marks the middle half of the values, and dots beyond it are unusually high or low entries.",
    "revenue_histogram": "How your values are distributed — tall bars mark where most records fall, and the shape shows whether typical values cluster tightly or spread out.",
    "regression_trend": "The overall direction of this metric over time, with a fitted line showing whether it's generally rising, falling, or flat.",
    "derived_margin_trend": "How the derived profit margin has moved over time.",
    "derived_metrics_summary": "A summary view of the business metrics the pipeline derived from your columns.",
    "discount_return_rate": "How the return rate changes as the discount offered gets bigger, so you can see whether steep discounts come with more returns.",
    "category_margin_trend": "How profit margin for each category has moved over time.",
    "rep_discount_margin": "Average discount given and the margin left over, compared across the people or teams responsible.",
    "segment_order_value": "The typical order value for each segment, so you can see which segments spend more per order.",
    "region_shipping_cost": "The average shipping cost for each region, so you can spot where fulfillment is more expensive.",
    "shipping_lead_time": "How long orders typically take to ship, broken down by group.",
}

# finalize_specs() only treats a legacy chart and a planner chart as the same
# chart (and drops one) when their (section, chart_type, title) all match.
# Every legacy family used to report chart_type="bar" regardless of what it
# actually was, so a legacy correlation_scatter could never match its planner
# equivalent and both survived — the exact "same chart twice" bug this maps
# away from. Values must be members of CHART_TYPES.
_FAMILY_CHART_TYPES = {
    "correlation_heatmap": "heatmap",
    "correlation_scatter": "scatter",
    "regression_trend": "line",
    "derived_margin_trend": "line",
    "category_margin_trend": "line",
    "revenue_histogram": "histbox",
    "distribution_boxplot": "histbox",
}


def wrap_legacy_candidate(candidate: dict) -> dict | None:
    """Convert an agent_4 legacy chart candidate ({path, family, score, reason})
    into an image-render spec so old families keep their slot in the unified
    gallery. Returns None for unusable candidates."""
    path = candidate.get("path")
    family = candidate.get("family", "legacy")
    reason = candidate.get("reason") or ""
    title = candidate.get("title") or _title_from_path(path, family)
    blurb = _FAMILY_BLURBS.get(family) or reason or f"Shows {family.replace('_', ' ')} patterns found in your data."
    try:
        priority = float(candidate.get("score", 0.0))
    except (TypeError, ValueError):
        priority = 0.0
    if not path:
        return None
    return {
        "id": f"legacy_{family}_{abs(hash(path)) % 10_000}",
        "family": family,
        "section": SECTION_BY_FAMILY.get(family, "what_matters"),
        "chart_type": _FAMILY_CHART_TYPES.get(family, "bar"),
        "render": "image",
        "title": title,
        "subtitle": "",
        "why_it_matters": blurb,
        "plain_summary": blurb,
        "alt_text": title,
        "data": {},
        "annotations": [{"label": "Signal", "value": reason}] if reason else [],
        "axis": {},
        "priority": round(priority, 2),
        "png_path": path,
    }


def finalize_specs(specs: list, cap: int = 10) -> list:
    """Dedupe by id and semantic chart identity, then cap by priority."""
    seen: set[str] = set()
    seen_semantic: dict[tuple, str] = {}
    unique = []
    ordered_specs = sorted(
        (spec for spec in specs if spec and isinstance(spec, dict)),
        key=lambda spec: spec.get("priority", 0.0),
        reverse=True,
    )
    for spec in ordered_specs:
        sid = spec.get("id")
        title = re.sub(r"[^a-z0-9]+", " ", str(spec.get("title", "")).lower()).strip()
        if sid in seen:
            continue
        seen.add(sid)
        source_kind = "legacy" if str(sid).startswith("legacy_") else "planner"
        semantic_identity = (spec.get("section"), spec.get("chart_type"), title)
        previous_kind = seen_semantic.get(semantic_identity)
        if previous_kind and previous_kind != source_kind:
            continue
        seen_semantic.setdefault(semantic_identity, source_kind)
        unique.append(spec)
    return unique[:cap]


def validate_spec(spec: dict) -> list[str]:
    """Return a list of problems (empty list = valid)."""
    problems = []
    for key in ("id", "family", "chart_type", "title", "why_it_matters"):
        if not spec.get(key):
            problems.append(f"missing/empty '{key}'")
    if spec.get("chart_type") not in CHART_TYPES:
        problems.append(f"unknown chart_type '{spec.get('chart_type')}'")
    unit = (spec.get("axis") or {}).get("y_unit")
    if unit is not None and unit not in AXIS_UNITS:
        problems.append(f"unknown y_unit '{unit}'")
    n_points = _count_points(spec.get("data") or {})
    if n_points > 2000:
        problems.append(f"data payload too large ({n_points} points)")
    return problems


# ── internals ────────────────────────────────────────────────────────────────

def _count_points(node) -> int:
    if isinstance(node, dict):
        return sum(_count_points(v) for v in node.values())
    if isinstance(node, (list, tuple)):
        return sum(_count_points(v) for v in node)
    if isinstance(node, (int, float)) and not isinstance(node, bool):
        return 1
    return 0


def _sanitize_data(data: dict) -> dict:
    """Coerce numpy-ish values into plain JSON-safe numbers; drop NaN/inf."""
    clean: dict = {}
    for key, value in (data or {}).items():
        clean[key] = _sanitize_value(value)
    return clean


def _sanitize_value(value):
    if isinstance(value, dict):
        return {k: _sanitize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(v) for v in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        fval = float(value)
        if math.isnan(fval) or math.isinf(fval):
            return None
        return round(fval, 6)
    return value


def _normalize_axis(axis: dict) -> dict:
    allowed = {"y_unit", "symbol", "log_y", "x_label", "y_label", "x_granularity"}
    out = {}
    for key in allowed:
        if key in axis and axis[key] not in (None, ""):
            out[key] = axis[key]
    out.setdefault("y_unit", "number")
    return out


def _title_from_path(path, family: str) -> str:
    # Chart PNGs are saved with os.path.join, which emits native (backslash on
    # Windows) separators - splitting on "/" alone leaves the directory prefix
    # glued onto the title (e.g. "Charts\\<hash>\\correlation Heatmap"). Split on
    # both separators regardless of host OS so the stripped basename is clean.
    base = re.split(r"[\\/]", str(path))[-1] if path else family
    stem = base.rsplit(".", 1)[0] if "." in base else base
    words = stem.replace("_", " ").split()
    small = {"by", "of", "the", "and", "to", "per", "vs", "over", "in", "on"}
    titled = " ".join(
        w if (i > 0 and w.lower() in small) else w.capitalize()
        for i, w in enumerate(words[:10])
    )
    return titled or family.replace("_", " ").capitalize()
