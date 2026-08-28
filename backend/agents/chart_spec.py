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
    descriptive: str = "",
    diagnostic: str = "",
    alt_text: str = "",
    annotations: list | None = None,
    axis: dict | None = None,
    priority: float = 0.0,
    png_path: str | None = None,
    dedup_key: str = "",
) -> dict:
    """Build a validated ChartSpec dict with all optional fields normalized.

    ``descriptive`` — a plain-language read-out of what the chart literally shows
    for *this* data (extremes, spread, counts). ``diagnostic`` — what explains that
    shape (skew driven by a tail, one group dominating, a trend that is mostly
    noise). Both are rendered under the chart alongside ``why_it_matters`` (the
    business "so what"). ``dedup_key`` — an explicit identity used by
    ``finalize_specs`` to collapse the same chart arriving from both the planner
    and a legacy agent_4 builder; when empty a key is derived from the title.
    """
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
        "descriptive": descriptive or "",
        "diagnostic": diagnostic or "",
        "alt_text": alt_text or title,
        "data": _sanitize_data(data),
        "annotations": [a for a in (annotations or []) if a],
        "axis": _normalize_axis(axis or {}),
        "priority": round(float(priority), 2),
        "dedup_key": str(dedup_key or ""),
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


# Families that describe the same underlying visual concept, so a legacy PNG and
# a planner spec for (say) "trend of revenue" collapse to one even when their
# titles are worded differently ("Revenue Linear Trend" vs "Revenue over time").
_FAMILY_GROUP = {
    "regression_trend": "trend", "derived_margin_trend": "trend",
    "category_margin_trend": "trend", "growth_rates": "trend",
    "growth_rates_monthly": "trend", "growth_rates_quarterly": "trend",
    "trend": "trend",
    "revenue_histogram": "distribution", "distribution_boxplot": "distribution",
    "category_distribution": "distribution", "distribution": "distribution",
    "correlation_heatmap": "correlation_heatmap",
    "correlation_scatter": "correlation_scatter",
    "seasonality": "seasonality", "seasonality_monthly": "seasonality",
    "seasonality_quarterly": "seasonality", "seasonality_heatmap": "seasonality",
    "seasonality_pattern": "seasonality",
    "top_bottom": "ranking", "top_bottom_ranking": "ranking",
    "dimension_ranking": "ranking", "profit_breakdown": "ranking",
    "segment_order_value": "ranking",
    "pareto": "pareto", "crosstab": "crosstab", "anomaly_overlay": "anomaly",
}

# Words that carry no identity when comparing two charts — chart-shape nouns and
# the connective glue. Stripping them from the title and the explicit dedup_key
# leaves just the columns/dimensions the chart is about, which is what decides
# whether the planner spec and a legacy PNG are the same chart.
_TITLE_STOPWORDS = frozenset({
    "the", "a", "an", "of", "by", "vs", "over", "per", "and", "or", "to", "in",
    "on", "is", "are", "how", "what", "where", "do", "does", "did", "your", "you",
    "this", "that", "it", "there", "their", "was", "were", "with", "for",
    "trend", "trends", "linear", "regression", "chart", "plot", "graph", "line",
    "distribution", "distributed", "distributions", "dist", "spread", "values",
    "value", "count", "counts", "histogram", "histbox", "boxplot", "box",
    "scatter", "heatmap", "pareto", "pie", "donut", "map",
    "time", "month", "monthly", "quarter", "quarterly", "year", "yearly",
    "calendar", "rhythm", "seasonal", "seasonality", "concentrated", "across",
    "each", "between", "travel", "together", "shape", "numbers", "numeric",
    "cols", "records", "record", "dot", "dots",
    "unusual", "cluster", "clusters", "rate", "rates", "ratio", "summary",
    "overview", "breakdown", "ranking", "ranked", "top", "bottom", "avg",
    "average", "total", "share", "level", "levels", "move", "moves",
})


def _identity_tokens(text: str) -> set[str]:
    return {
        t for t in re.split(r"[^a-z0-9]+", str(text).lower())
        if len(t) > 1 and not t.isdigit() and t not in _TITLE_STOPWORDS
    }


def _dedup_identity(spec: dict) -> tuple[tuple, bool]:
    """Return ((section, group, sorted_tokens), is_meaningful).

    Both the planner (explicit ``dedup_key``) and legacy PNGs (title only) reduce
    to the same ``(section, visual concept, columns)`` triple, so "Revenue Linear
    Trend" and "Revenue over time" collapse to one chart. ``is_meaningful`` is
    False only when nothing comparable could be extracted (e.g. a synthetic spec
    titled "t"); callers then fall back to the historical "collapse across
    sources only" rule so unrelated placeholder specs survive.
    """
    section = spec.get("section")
    group = _FAMILY_GROUP.get(spec.get("family"), spec.get("chart_type") or "")
    tokens = _identity_tokens(spec.get("title", ""))
    explicit = str(spec.get("dedup_key") or "")
    if explicit:
        tokens |= _identity_tokens(explicit)
    return ((section, group, tuple(sorted(tokens))), bool(tokens))


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
    diagnostic = candidate.get("diagnostic") or (
        f"Selected because {reason}." if reason else ""
    )
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
        "descriptive": candidate.get("descriptive") or blurb,
        "diagnostic": diagnostic,
        "alt_text": title,
        "data": {},
        "annotations": [{"label": "Signal", "value": reason}] if reason else [],
        "axis": {},
        "priority": round(priority, 2),
        "png_path": path,
        "dedup_key": str(candidate.get("dedup_key") or ""),
    }


def finalize_specs(specs: list, cap: int = 10) -> list:
    """Dedupe by id and by chart identity, then cap by priority.

    Chart identity is (report section, visual concept, the columns/dimensions the
    title is about). Two specs with the same identity collapse to the
    higher-priority one regardless of whether they came from the planner or a
    legacy agent_4 PNG — this is what stops the same chart being shown twice.
    """
    seen: set[str] = set()
    seen_identity: dict[tuple, str] = {}
    unique = []
    ordered_specs = sorted(
        (spec for spec in specs if spec and isinstance(spec, dict)),
        key=lambda spec: spec.get("priority", 0.0),
        reverse=True,
    )
    for spec in ordered_specs:
        sid = spec.get("id")
        if sid in seen:
            continue
        seen.add(sid)
        source_kind = "legacy" if str(sid).startswith("legacy_") else "planner"
        identity, meaningful = _dedup_identity(spec)
        prev_kind = seen_identity.get(identity)
        if prev_kind is not None and (meaningful or prev_kind != source_kind):
            continue
        seen_identity.setdefault(identity, source_kind)
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
