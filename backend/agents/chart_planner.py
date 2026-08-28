"""Domain-free chart planner — turns computed facts into ChartSpecs.

Unlike the legacy keyword-gated families inside agent_4, this planner scores
EVERY candidate visualization on statistical signal strength, so it works on
any dataset shape (sales, HR, IoT sensors, support tickets...) without domain
hardcoding:

  dimension_ranking   category column vs numeric metric   -> ANOVA eta-squared
  pareto              concentration of value in few groups -> top-N share
  distribution        numeric spread interest              -> |skew| + outliers
  trend               metric vs time                       -> regression r²
  seasonality_pattern month-of-year movement               -> coefficient of variation
  correlation_scatter strongest related pair              -> |r| scatter + fit
  crosstab            two category columns                -> Cramér's V heatmap
  anomaly_overlay     unusual records per column          -> flagged density

Every builder returns plain-dict ChartSpecs (agents/chart_spec.py) whose
`data` payloads are pre-aggregated and size-capped, so both the interactive
ECharts renderer and the static PNG twin consume exactly the same bytes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from agents.chart_spec import make_spec
from agents.report_style import humanize_number, humanize_pct, titleize

# ── payload caps ──────────────────────────────────────────────────────────────
MAX_BAR_LABELS = 15          # bars per ranking/spec chart before "Other"
MAX_SCATTER_POINTS = 400     # stride-sampled points per scatter
MAX_OUTLIERS_LISTED = 30     # outlier dots drawn per histbox
MIN_GROUP_ROWS = 3           # smallest usable category group
MIN_ROWS_FOR_GROUPS = 8      # minimum rows before group comparisons make sense
CAT_MAX_UNIQUE = 25          # above this a categorical isn't readable anyway
CROSSTAB_MAX_UNIQUE = 8      # heatmap cells stay readable
MAX_SPECS_PER_FAMILY = 2     # let up to N qualifying trends/pairs compete for a chart slot, not just the single best


# ── local column classification (kept independent of agent_4) ────────────────
_VALIDATION_SUFFIXES = ("_parse_failed", "_range_failed")
_BACKUP_SUFFIXES = ("_raw", "_scaled", "_was_clipped")
_DATE_DERIVED_SUFFIXES = (
    "_year", "_month", "_quarter", "_day",
    "_day_of_week", "_is_weekend", "_week_of_year",
)

_FINANCIAL_TOKENS = ("revenue", "sales", "price", "cost", "profit", "amount",
                     "spend", "fee", "salary", "income", "budget", "payment")
_PERCENT_TOKENS = ("pct", "percent", "rate", "margin", "ratio")


def _numeric_cols(df, schema_blueprint):
    cols = []
    for col in df.columns:
        if col.endswith(_VALIDATION_SUFFIXES) or col.endswith(_BACKUP_SUFFIXES):
            continue
        meta = schema_blueprint.get(col, {}) if isinstance(schema_blueprint, dict) else {}
        if meta.get("analysis_allowed") is False or meta.get("is_identifier"):
            continue
        if meta.get("semantic_tag") in ("datetime", "identifier"):
            continue
        if pd.api.types.is_bool_dtype(df[col]):
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            cols.append(col)
    return cols


def _categorical_cols(df, schema_blueprint):
    cols = []
    for col in df.columns:
        if col.endswith(_VALIDATION_SUFFIXES):
            continue
        meta = schema_blueprint.get(col, {}) if isinstance(schema_blueprint, dict) else {}
        if meta.get("analysis_allowed") is False or meta.get("is_identifier"):
            continue
        if meta.get("semantic_tag") in ("datetime", "identifier"):
            continue
        is_string_col = (
            df[col].dtype == object
            or str(df[col].dtype) in ("string", "str")
            or (hasattr(df[col].dtype, "name") and df[col].dtype.name in ("string", "str"))
        )
        if is_string_col or meta.get("semantic_tag") in ("categorical_label", "geographic"):
            if 2 <= df[col].nunique(dropna=True) <= CAT_MAX_UNIQUE:
                cols.append(col)
    return cols


def _is_date_derived(col: str) -> bool:
    return any(col.endswith(s) for s in _DATE_DERIVED_SUFFIXES)


def _unit_for(col: str, schema_blueprint) -> dict:
    """Axis formatting hints inferred from semantic metadata + name tokens."""
    meta = schema_blueprint.get(col, {}) if isinstance(schema_blueprint, dict) else {}
    financial_role = str(meta.get("financial_role") or "").lower()
    tokens = set(_tokenize(col))
    if financial_role in {"revenue", "cost", "profit"} or tokens & set(_FINANCIAL_TOKENS):
        return {"y_unit": "currency"}
    if tokens & set(_PERCENT_TOKENS):
        return {"y_unit": "percent"}
    return {"y_unit": "number"}


def _tokenize(col: str) -> list[str]:
    import re
    return re.findall(r"[a-z0-9]+", str(col).lower())


def _primary_metric(df, schema_blueprint):
    """The headline numeric metric: explicit revenue tag first, then best-variance."""
    numeric = _numeric_cols(df, schema_blueprint)
    if not numeric:
        return None
    for col in numeric:
        if (schema_blueprint.get(col, {}) or {}).get("financial_role") == "revenue":
            return col
    spend = "derived_total_spend"
    if spend in numeric:
        return spend
    best, best_cv = None, -1.0
    for col in numeric:
        s = df[col].dropna()
        if len(s) < MIN_ROWS_FOR_GROUPS or float(s.mean() or 0) == 0:
            continue
        cv = abs(float(s.std()) / float(s.mean()))
        if cv > best_cv:
            best, best_cv = col, cv
    return best or numeric[0]


# ── entry point ───────────────────────────────────────────────────────────────

def build_chart_specs(df, schema_blueprint, stats) -> list[dict]:
    """Compute all generic ChartSpecs. Never raises for data-shaped reasons;
    individual builders are isolated so one failure can't kill the rest."""
    specs: list[dict] = []
    builders = (
        lambda: _dimension_ranking_specs(df, schema_blueprint),
        lambda: _pareto_spec(df, schema_blueprint),
        lambda: _distribution_specs(df, schema_blueprint),
        lambda: _trend_spec(df, schema_blueprint, stats),
        lambda: _seasonality_pattern_spec(df, schema_blueprint),
        lambda: _correlation_scatter_spec(df, stats),
        lambda: _crosstab_spec(df, schema_blueprint),
        lambda: _anomaly_overlay_spec(stats),
    )
    for builder in builders:
        try:
            produced = builder()
            if produced:
                specs.extend(produced)
        except Exception:  # noqa: BLE001 — planner output is best-effort by design
            continue
    return specs


# ── 1. dimension rankings (eta² scored) ───────────────────────────────────────

def _dimension_ranking_specs(df, schema_blueprint) -> list[dict]:
    metric = _primary_metric(df, schema_blueprint)
    cat_cols = _categorical_cols(df, schema_blueprint)
    if not metric or not cat_cols or len(df) < MIN_ROWS_FOR_GROUPS:
        return []

    scored = []
    for cat in cat_cols:
        eta2, groups_n, means = _eta_squared(df[cat], df[metric])
        if eta2 is None:
            continue
        scored.append((eta2, cat, groups_n, means))

    scored.sort(key=lambda t: t[0], reverse=True)
    specs = []
    for eta2, cat, groups_n, means in scored[:3]:
        if eta2 < 0.08:   # below ~weak effect: the chart would look like noise
            continue
        ordered = sorted(means.items(), key=lambda kv: kv[1], reverse=True)
        top_name, top_val = ordered[0]
        bottom_name, bottom_val = ordered[-1]
        total_mean = float(pd.Series(list(means.values())).mean()) or 1e-9
        lift = (top_val / total_mean - 1.0) * 100
        specs.append(make_spec(
            spec_id=f"ranking_{cat}_by_{metric}",
            family="dimension_ranking",
            chart_type="bar",
            title=f"{titleize(metric)} by {titleize(cat)}",
            subtitle=f"average {titleize(metric).lower()} across {groups_n} groups",
            why_it_matters=(
                f"'{top_name}' leads {titleize(cat)} with an average {titleize(metric).lower()} "
                f"of {humanize_pct(lift)} {'above' if lift >= 0 else 'below'} the overall average."
            ),
            plain_summary=(
                f"This chart compares {titleize(cat).lower()} groups side by side. "
                f"{titleize(top_name)} comes out ahead; the gap between groups is "
                f"{'noticeable' if eta2 >= 0.14 else 'modest'}."
            ),
            descriptive=(
                f"Average {titleize(metric).lower()} across {groups_n} {titleize(cat).lower()} "
                f"groups runs from {humanize_number(bottom_val)} ({titleize(str(bottom_name))}) "
                f"to {humanize_number(top_val)} ({titleize(str(top_name))}), against an overall "
                f"average of {humanize_number(total_mean)}."
            ),
            diagnostic=(
                f"{titleize(cat)} membership accounts for about {round(eta2 * 100)}% of the "
                f"variation in {titleize(metric).lower()} (eta-squared = {eta2:.2f}) — "
                + ("a strong separation, so this ranking is dependable."
                   if eta2 >= 0.14 else
                   "a modest separation, so read the order as indicative rather than firm.")
            ),
            dedup_key=f"ranking:{metric}:{cat}",
            alt_text=f"Bar chart of average {metric} for each {cat} group",
            data={"labels": [str(k) for k, _ in ordered[:MAX_BAR_LABELS]],
                  "values": [round(float(v), 4) for _, v in ordered[:MAX_BAR_LABELS]]},
            annotations=[{"label": f"Top: {top_name}", "value": round(float(top_val), 4)}],
            axis={**_unit_for(metric, schema_blueprint), "x_label": titleize(cat),
                  "y_label": f"Avg {titleize(metric)}"},
            priority=round(eta2 * 100, 2),
        ))
    return specs


def _eta_squared(cat_series, metric_series):
    """ANOVA effect size: share of the metric's variance explained by groups.
    Returns (eta2 | None, n_groups, {group: mean})."""
    working = pd.DataFrame({"g": cat_series, "v": pd.to_numeric(metric_series, errors="coerce")}).dropna()
    grouped = working.groupby("g", observed=True)["v"]
    sizes = grouped.size()
    sizes = sizes[sizes >= MIN_GROUP_ROWS]
    if len(sizes) < 2 or int(sizes.sum()) < MIN_ROWS_FOR_GROUPS:
        return None, 0, {}
    working = working[working["g"].isin(sizes.index)]
    grand = float(working["v"].mean())
    ss_total = float(((working["v"] - grand) ** 2).sum())
    if ss_total <= 0:
        return None, 0, {}
    ss_between = float(sum(
        len(g) * (float(g.mean()) - grand) ** 2
        for _, g in working.groupby("g", observed=True)["v"]
    ))
    eta2 = max(0.0, min(1.0, ss_between / ss_total))
    means = {str(k): float(v) for k, v in grouped.mean().items()}
    return eta2, len(sizes), means


# ── 2. pareto concentration ───────────────────────────────────────────────────

def _pareto_spec(df, schema_blueprint) -> list[dict]:
    metric = _primary_metric(df, schema_blueprint)
    if not metric:
        return []
    best_cat, best_score, best_data = None, 0.0, None
    for cat in _categorical_cols(df, schema_blueprint):
        sums = df.groupby(cat, observed=True)[metric].sum().sort_values(ascending=False)
        sums = sums[sums > 0]
        total = float(sums.sum())
        if total <= 0 or len(sums) < 3:
            continue
        top1 = float(sums.iloc[0]) / total * 100
        top3 = float(sums.head(min(3, len(sums))).sum()) / total * 100
        score = 0.6 * top1 + 0.4 * top3
        if score > best_score:
            labels = [str(k) for k in sums.index[:10]]
            values = [float(v) for v in sums.values[:10]]
            cumulative, running = [], 0.0
            for v in values:
                running += v
                cumulative.append(round(running / total * 100, 2))
            best_cat, best_score, best_data = cat, score, {
                "labels": labels, "values": [round(v, 4) for v in values],
                "cumulative_pct": cumulative,
            }
    if not best_data or best_score < 30:
        return []

    # Aggregate the tail into one honest "Other" bucket so the shape stays readable.
    if len(best_data["labels"]) == 10:
        other_mask = ~df[best_cat].astype(str).isin(best_data["labels"])
        if other_mask.any():
            tail_sum = float(df.loc[other_mask, metric].sum())
            if tail_sum > 0:
                best_data["labels"].append("Other")
                best_data["values"].append(round(tail_sum, 4))
                prev = best_data["cumulative_pct"][-1]
                best_data["cumulative_pct"].append(round(prev + tail_sum / float(df[metric].sum()) * 100, 2))

    top_label = best_data["labels"][0]
    top_share = best_data["cumulative_pct"][0]
    n_shown = len(best_data["labels"])
    top_k = min(3, len(best_data["cumulative_pct"]))
    top_k_share = best_data["cumulative_pct"][top_k - 1]
    return [make_spec(
        spec_id=f"pareto_{best_cat}_{metric}",
        family="pareto",
        chart_type="pareto",
        title=f"How concentrated is {titleize(metric)}?",
        subtitle=f"share of total {titleize(metric).lower()} by {titleize(best_cat)}",
        why_it_matters=(
            f"The single largest {titleize(best_cat).lower()} ('{top_label}') accounts for "
            f"{humanize_pct(top_share)} of all {titleize(metric).lower()} — "
            f"{'heavily' if top_share >= 50 else 'moderately'} concentrated."
        ),
        plain_summary=(
            f"Bars show how much each {titleize(best_cat).lower()} contributes, biggest first. "
            f"The line tracks the running total: where it climbs steeply, that small set of "
            f"items drives most of the business."
        ),
        descriptive=(
            f"'{top_label}' alone is {humanize_pct(top_share)} of total {titleize(metric).lower()}; "
            f"the top {top_k} together reach {humanize_pct(top_k_share)} across "
            f"{n_shown} shown {titleize(best_cat).lower()} values."
        ),
        diagnostic=(
            "The cumulative line "
            + ("shoots up then flattens — value is concentrated in a few "
               f"{titleize(best_cat).lower()}, the classic 80/20 shape."
               if top_share >= 50 else
               "climbs fairly evenly — value is spread across many "
               f"{titleize(best_cat).lower()} rather than concentrated.")
        ),
        dedup_key=f"pareto:{best_cat}:{metric}",
        alt_text=f"Pareto chart of {metric} concentration across {best_cat}",
        data=best_data,
        annotations=[{"label": f"{top_label} = {humanize_pct(top_share)}", "value": round(top_share, 2)}],
        axis={**_unit_for(metric, schema_blueprint), "x_label": titleize(best_cat),
              "y_label": titleize(metric)},
        priority=round(min(95.0, best_score), 2),
    )]


# ── 3. distributions (histogram + box in one spec) ────────────────────────────

def _distribution_specs(df, schema_blueprint) -> list[dict]:
    candidates = []
    for col in _numeric_cols(df, schema_blueprint):
        if _is_date_derived(col):
            continue
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(s) < 20 or float(s.std() or 0) == 0:
            continue
        skew = float(s.skew()) if len(s) >= 3 else 0.0
        std = float(s.std())
        outliers = s[(s - s.mean()).abs() > 3 * std]
        interest = min(100.0, abs(skew) * 40 + (len(outliers) / len(s)) * 300)
        candidates.append((interest, col, s, skew, outliers))
    candidates.sort(key=lambda t: t[0], reverse=True)

    specs = []
    for interest, col, s, skew, outliers in candidates[:2]:
        if interest < 20:
            continue
        counts_arr, bin_edges_arr = np.histogram(s, bins=min(20, max(5, s.nunique())))
        q1, med, q3 = (float(s.quantile(q)) for q in (0.25, 0.5, 0.75))
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        shape_word = (
            "most values sit at the low end with a long tail of high ones" if skew > 0.8
            else "most values sit at the high end with a long tail of low ones" if skew < -0.8
            else "values are fairly balanced around the middle"
        )
        mean_v = float(s.mean())
        mean_gap = 0.05 * abs(med) if med else 0.0
        specs.append(make_spec(
            spec_id=f"distribution_{col}",
            family="distribution",
            chart_type="histbox",
            title=f"How are {titleize(col)} values spread?",
            subtitle=f"{len(s):,} records · typical range highlighted",
            why_it_matters=(
                f"{titleize(col)} is {'strongly skewed' if abs(skew) > 1 else 'moderately skewed' if abs(skew) > 0.5 else 'roughly symmetric'} — "
                f"{shape_word}. Averages alone would hide that."
            ),
            plain_summary=(
                "Tall bars mark where most records fall; the box underneath shows the middle "
                "half of the data and the dots beyond it are unusually high or low entries "
                "worth knowing about."
            ),
            descriptive=(
                f"{len(s):,} values: median {humanize_number(med)}, mean {humanize_number(mean_v)}, "
                f"middle half between {humanize_number(q1)} and {humanize_number(q3)}. "
                f"{len(outliers)} fall beyond ±3 standard deviations."
            ),
            diagnostic=(
                f"The mean is {'well above' if mean_v > med + mean_gap else 'well below' if mean_v < med - mean_gap else 'close to'} "
                f"the median"
                + (f", pulled by a long {'right' if skew > 0 else 'left'} tail (skew {skew:+.2f})."
                   if abs(skew) > 0.5 else
                   f", so the spread is roughly symmetric (skew {skew:+.2f}).")
            ),
            dedup_key=f"distribution:{col}",
            alt_text=f"Histogram and box summary of {col}",
            data={
                "bins": [round(float(b), 6) for b in bin_edges_arr],
                "counts": [int(c) for c in counts_arr],
                "box": {
                    "lo": round(lo, 4), "q1": round(q1, 4), "med": round(med, 4),
                    "q3": round(q3, 4), "hi": round(hi, 4),
                    "outliers": [round(float(o), 4) for o in outliers.head(MAX_OUTLIERS_LISTED)],
                },
                "mean": round(float(s.mean()), 4), "median": round(float(med), 4),
            },
            annotations=[
                {"label": "Median", "value": round(float(med), 4)},
                {"label": "Average", "value": round(float(s.mean()), 4)},
            ],
            axis={**_unit_for(col, schema_blueprint), "x_label": titleize(col), "y_label": "Records"},
            priority=round(interest, 2),
        ))
    return specs


# ── 4. trend over time (from Agent 4's regression results) ───────────────────

def _trend_direction_word(y_fit: list, y_values: list, slope_direction: str) -> str:
    """A statistically significant regression can still have a practically tiny fitted
    change (common with large n) - only call it "upward"/"downward" when the fitted line
    actually moves by a meaningful amount relative to the typical value, else "flat"."""
    if not y_fit or not y_values:
        return slope_direction
    avg = sum(abs(v) for v in y_values) / len(y_values) or 1e-9
    pct_change = abs(y_fit[-1] - y_fit[0]) / avg * 100
    return slope_direction if pct_change >= 3 else "flat"


def _trend_spec(df, schema_blueprint, stats) -> list[dict]:
    regression = (stats or {}).get("regression") or {}
    if not isinstance(regression, dict) or not regression:
        return []
    year_col = next((c for c in df.columns if c.endswith("_year")), None)
    month_col = next((c for c in df.columns if c.endswith("_month")), None)
    if not year_col or not month_col:
        return []  # row-index trends stay covered by the legacy PNG

    eligible = [
        (info.get("r_squared") or 0.0, col)
        for col, info in regression.items()
        if info.get("significant") and info.get("r_squared") is not None
        and col in df.columns and not _is_date_derived(col)
    ]
    if not eligible:
        return []
    eligible.sort(reverse=True)

    specs = []
    for r_squared, col in eligible[:MAX_SPECS_PER_FAMILY]:
        info = regression[col]
        working = pd.DataFrame({
            "idx": (pd.to_numeric(df[year_col], errors="coerce") * 12
                    + pd.to_numeric(df[month_col], errors="coerce")),
            "y": pd.to_numeric(df[col], errors="coerce"),
        }).dropna()
        if working.empty:
            continue
        monthly = working.groupby("idx")["y"].mean().reset_index().sort_values("idx")
        if len(monthly) < 3:
            continue
        labels = [_idx_to_month_label(i) for i in monthly["idx"]]
        y_fit = [round(float(info["slope"]) * float(i) + float(info["intercept"]), 4)
                 for i in monthly["idx"]]
        y_values = [round(float(v), 4) for v in monthly["y"]]
        direction = _trend_direction_word(y_fit, y_values, info.get("trend", "upward"))

        if direction == "flat":
            subtitle = "monthly averages · little overall change"
            why_it_matters = (
                f"{titleize(col)} is statistically significant but the actual month-to-month change is "
                f"small — the fitted line explains {humanize_pct(r_squared * 100)} of the pattern, but this "
                f"looks stable rather than a meaningful trend."
            )
            plain_summary = (
                f"Each point is one month's typical {titleize(col).lower()}. The dashed line stays "
                f"roughly flat — this metric has held steady over the period shown."
            )
        else:
            subtitle = f"monthly averages · {direction} direction"
            why_it_matters = (
                f"{titleize(col)} has been moving steadily {direction} — the fitted line explains "
                f"{humanize_pct(r_squared * 100)} of the month-to-month pattern, so this looks like a real trend rather than noise."
            )
            plain_summary = (
                f"Each point is one month's typical {titleize(col).lower()}. The dashed line is the "
                f"overall direction of travel: {'rising' if direction == 'upward' else 'falling'} over the period shown."
            )

        avg_abs = (sum(abs(v) for v in y_values) / len(y_values)) or 1e-9
        fitted_move_pct = abs(y_fit[-1] - y_fit[0]) / avg_abs * 100
        descriptive = (
            f"{len(monthly)} monthly points, from {humanize_number(y_values[0])} to "
            f"{humanize_number(y_values[-1])}; the fitted line moves about "
            f"{humanize_pct(fitted_move_pct)} end to end."
        )
        diagnostic = (
            f"The straight-line fit explains {humanize_pct(r_squared * 100)} of the "
            f"month-to-month movement — "
            + (f"a clear {direction} path with ordinary fluctuation around it."
               if r_squared >= 0.3 and direction != "flat" else
               "most of the movement is short-term noise, so the "
               f"{direction if direction != 'flat' else 'overall'} slope is weak.")
        )
        specs.append(make_spec(
            spec_id=f"trend_{col}",
            family="trend",
            chart_type="line",
            title=f"{titleize(col)} over time",
            subtitle=subtitle,
            why_it_matters=why_it_matters,
            plain_summary=plain_summary,
            descriptive=descriptive,
            diagnostic=diagnostic,
            dedup_key=f"trend:{col}",
            alt_text=f"Line chart of monthly {col} with fitted trend line",
            data={
                "x": labels,
                "y": y_values,
                "fit": {"y_fit": y_fit},
            },
            annotations=[
                {"label": "Direction", "value": direction},
                {"label": "Pattern strength", "value": round(float(r_squared), 4)},
            ],
            axis={**_unit_for(col, schema_blueprint), "x_granularity": "month",
                  "y_label": titleize(col)},
            priority=round(float(r_squared) * 100, 2),
        ))
    return specs


def _idx_to_month_label(idx) -> str:
    idx = int(idx)
    year, month = divmod(idx, 12)
    return f"{year}-{month:02d}"


# ── 5. seasonality pattern (month-of-year movement) ───────────────────────────

_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _seasonality_pattern_spec(df, schema_blueprint) -> list[dict]:
    month_col = next((c for c in df.columns if c.endswith("_month")), None)
    metric = _primary_metric(df, schema_blueprint)
    if not month_col or not metric:
        return []
    months = pd.to_numeric(df[month_col], errors="coerce")
    values = pd.to_numeric(df[metric], errors="coerce")
    working = pd.DataFrame({"m": months, "v": values}).dropna()
    monthly = working.groupby("m")["v"].mean()
    if len(monthly) < 6:
        return []
    mean_of_means = float(monthly.mean()) or 1e-9
    cv = float(monthly.std()) / abs(mean_of_means)
    if cv < 0.05:
        return []
    ordered = [(int(m), float(monthly.loc[m])) for m in sorted(monthly.index)]
    best_m, best_v = max(ordered, key=lambda t: t[1])
    worst_m, worst_v = min(ordered, key=lambda t: t[1])
    return [make_spec(
        spec_id=f"seasonality_{metric}",
        family="seasonality_pattern",
        chart_type="bar",
        title=f"Is there a yearly rhythm in {titleize(metric)}?",
        subtitle="average by calendar month",
        why_it_matters=(
            f"{titleize(metric)} peaks in {_MONTH_NAMES[best_m - 1]} and dips in "
            f"{_MONTH_NAMES[worst_m - 1]} — worth planning stock, staffing, or campaigns around."
        ),
        plain_summary=(
            "This shows the typical level for each calendar month, averaged across all years "
            f"in the data. {_MONTH_NAMES[best_m - 1]} is the strong month; "
            f"{_MONTH_NAMES[worst_m - 1]} is the quiet one."
        ),
        descriptive=(
            f"Monthly average swings from {humanize_number(worst_v)} in "
            f"{_MONTH_NAMES[worst_m - 1]} to {humanize_number(best_v)} in "
            f"{_MONTH_NAMES[best_m - 1]}, around a year-round mean of "
            f"{humanize_number(mean_of_means)}."
        ),
        diagnostic=(
            f"Month-to-month variation is about {humanize_pct(cv * 100)} of the average — "
            + ("a pronounced yearly rhythm rather than random scatter."
               if cv >= 0.2 else
               "a mild seasonal wobble rather than a strong pattern.")
        ),
        dedup_key=f"seasonality:{metric}",
        alt_text=f"Bar chart of average {metric} by calendar month",
        data={
            "labels": [_MONTH_NAMES[m - 1] for m, _ in ordered],
            "values": [round(v, 4) for _, v in ordered],
        },
        annotations=[
            {"label": f"Peak: {_MONTH_NAMES[best_m - 1]}", "value": round(best_v, 4)},
            {"label": f"Low: {_MONTH_NAMES[worst_m - 1]}", "value": round(worst_v, 4)},
        ],
        axis={**_unit_for(metric, schema_blueprint), "x_granularity": "month_of_year",
              "y_label": f"Avg {titleize(metric)}"},
        priority=round(min(85.0, cv * 150), 2),
    )]


# ── 6. correlation scatter (best available pair) ─────────────────────────────

def _correlation_scatter_spec(df, stats) -> list[dict]:
    pairs = ((stats or {}).get("correlation") or {}).get("strong_pairs") or []
    specs = []
    for pair in pairs:
        if len(specs) >= MAX_SPECS_PER_FAMILY:
            break
        col_x, col_y = pair.get("col1"), pair.get("col2")
        if not col_x or not col_y or col_x not in df.columns or col_y not in df.columns:
            continue
        if _is_date_derived(col_x) or _is_date_derived(col_y):
            continue
        working = pd.DataFrame({
            "x": pd.to_numeric(df[col_x], errors="coerce"),
            "y": pd.to_numeric(df[col_y], errors="coerce"),
        }).dropna()
        if len(working) < 15:
            continue
        stride = max(1, len(working) // MAX_SCATTER_POINTS)
        sample = working.iloc[::stride]
        try:
            slope, intercept, r_value, p_value, _ = scipy_stats.linregress(sample["x"], sample["y"])
        except Exception:  # noqa: BLE001
            continue
        xs = sample["x"].to_numpy(dtype=float)
        fit = [[round(float(xs.min()), 4), round(float(intercept + slope * xs.min()), 4)],
               [round(float(xs.max()), 4), round(float(intercept + slope * xs.max()), 4)]]
        direction = "rise together" if slope > 0 else "move in opposite directions"
        r = float(pair.get("pearson_r") or r_value or 0.0)
        specs.append(make_spec(
            spec_id=f"scatter_{col_x}_{col_y}",
            family="correlation_scatter",
            chart_type="scatter",
            title=f"{titleize(col_x)} vs {titleize(col_y)}",
            subtitle=f"each dot is one record · r = {pair.get('pearson_r')}",
            why_it_matters=(
                f"When {titleize(col_x).lower()} changes, {titleize(col_y).lower()} tends to "
                f"{direction}. Knowing one gives you an early read on the other."
            ),
            plain_summary=(
                "Each dot is one record. The dashed line is the general direction: dots hugging "
                "the line closely mean a dependable relationship; a loose cloud means it is weaker."
            ),
            descriptive=(
                f"{len(sample):,} records plotted; Pearson r = {round(r, 2)}, so about "
                f"{humanize_pct(r * r * 100)} of {titleize(col_y).lower()}'s variation lines up "
                f"with {titleize(col_x).lower()}."
            ),
            diagnostic=(
                "Points "
                + ("hug the fitted line — a dependable, roughly linear link."
                   if abs(r) >= 0.7 else
                   "sit in a loose band around the line — a real but weak link, with other "
                   "factors clearly at play.")
            ),
            dedup_key=f"scatter:{'|'.join(sorted([col_x, col_y]))}",
            alt_text=f"Scatter plot of {col_x} against {col_y} with fitted line",
            data={
                "points": [[round(float(x), 4), round(float(y), 4)]
                           for x, y in zip(sample["x"], sample["y"])],
                "fit": fit,
            },
            annotations=[{"label": "Link strength (r)", "value": round(float(pair.get("pearson_r") or 0), 3)}],
            axis={**_unit_for(col_x, {}), "x_label": titleize(col_x), "y_label": titleize(col_y)},
            priority=round(abs(float(pair.get("pearson_r") or 0)) * 100, 2),
        ))
    return specs


# ── 7. crosstab heatmap (Cramér's V) ─────────────────────────────────────────

def _crosstab_spec(df, schema_blueprint) -> list[dict]:
    cats = [c for c in _categorical_cols(df, schema_blueprint)
            if df[c].nunique(dropna=True) <= CROSSTAB_MAX_UNIQUE]
    if len(cats) < 2:
        return []
    scored = []
    for i in range(len(cats)):
        for j in range(i + 1, len(cats)):
            c1, c2 = cats[i], cats[j]
            table = pd.crosstab(df[c1], df[c2]).to_numpy()
            if table.shape[0] < 2 or table.shape[1] < 2 or table.sum() < 10:
                continue
            try:
                chi2, _, _, _ = scipy_stats.chi2_contingency(table)
            except Exception:  # noqa: BLE001
                continue
            n = table.sum()
            denom = n * (min(table.shape) - 1)
            v = float(np.sqrt(chi2 / denom)) if denom else 0.0
            if v >= 0.15:
                scored.append((v, c1, c2))
    if not scored:
        return []
    scored.sort(key=lambda t: t[0], reverse=True)
    specs = []
    for v, c1, c2 in scored[:MAX_SPECS_PER_FAMILY]:
        ct = pd.crosstab(df[c1].astype(str), df[c2].astype(str))
        strength = "meaningful link" if v >= 0.3 else "some link"
        specs.append(make_spec(
            spec_id=f"crosstab_{c1}_{c2}",
            family="crosstab",
            chart_type="heatmap",
            title=f"Do {titleize(c1)} and {titleize(c2)} travel together?",
            subtitle=f"record counts · {strength} detected",
            why_it_matters=(
                f"{titleize(c1)} and {titleize(c2)} show a {strength}: certain combinations occur far "
                f"more often than chance, which is useful for targeting and planning."
            ),
            plain_summary=(
                "Darker cells mark combinations that happen more often. Scan for dark rows/columns — "
                "they reveal which mixtures dominate your data."
            ),
            descriptive=(
                f"{ct.shape[0]}×{ct.shape[1]} category grid; Cramér's V = {round(float(v), 2)} "
                f"({strength})."
            ),
            diagnostic=(
                f"Certain {titleize(c1).lower()} / {titleize(c2).lower()} combinations occur "
                f"{'far more' if v >= 0.3 else 'somewhat more'} often than they would if the two "
                f"dimensions were unrelated."
            ),
            dedup_key=f"crosstab:{'|'.join(sorted([c1, c2]))}",
            alt_text=f"Heatmap of record counts between {c1} and {c2}",
            data={
                "rows": list(ct.index)[:CROSSTAB_MAX_UNIQUE],
                "cols": list(ct.columns)[:CROSSTAB_MAX_UNIQUE],
                "matrix": [[int(v_) for v_ in row][:CROSSTAB_MAX_UNIQUE] for row in ct.to_numpy()],
            },
            annotations=[{"label": "Link strength", "value": round(v, 3)}],
            axis={"x_label": titleize(c2), "y_label": titleize(c1)},
            priority=round(v * 90, 2),
        ))
    return specs


# ── 8. anomaly watchlist ──────────────────────────────────────────────────────

def _anomaly_overlay_spec(stats) -> list[dict]:
    summary = (stats or {}).get("anomaly_summary") or {}
    prioritized = summary.get("prioritized_anomalies") or []
    items = [(p.get("column"), p.get("flagged_count") or 0) for p in prioritized]
    items = [(c, n) for c, n in items if c and n]
    if not items:
        return []
    items.sort(key=lambda t: t[1], reverse=True)
    items = items[:8]
    pct = float(summary.get("unique_flagged_row_pct") or 0.0)
    top_col, top_n = items[0]
    return [make_spec(
        spec_id="anomaly_watchlist",
        family="anomaly_overlay",
        chart_type="barh",
        title="Where do unusual records cluster?",
        subtitle=f"{summary.get('unique_flagged_rows', '?')} records flagged in total",
        why_it_matters=(
            f"About {humanize_pct(pct)} of records look unusual compared with their column's normal "
            f"range. These are worth a manual check for data-entry mistakes or one-off events."
        ),
        plain_summary=(
            "Each bar counts how many unusually high or low entries were found in that column. "
            "Longer bars deserve a closer look before you act on any averages."
        ),
        descriptive=(
            f"{summary.get('unique_flagged_rows', '?')} records ({humanize_pct(pct)}) flagged "
            f"across {len(items)} column(s); the most in {titleize(str(top_col))} ({int(top_n)})."
        ),
        diagnostic=(
            "Flags mark values outside each column's normal range (z-score / IQR). A cluster in "
            "one column usually points to a unit or data-entry problem rather than that many "
            "genuine outliers."
        ),
        dedup_key="anomaly:watchlist",
        alt_text="Horizontal bar chart of flagged record counts per column",
        data={
            "labels": [titleize(c) for c, _ in items],
            "values": [int(n) for _, n in items],
        },
        annotations=[{"label": "Share of all records", "value": round(pct, 2)}],
        axis={"y_unit": "count", "x_label": "Flagged records"},
        priority=round(min(80.0, pct * 8), 2),
    )]
