import os
import re
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from scipy import stats as scipy_stats
from agents.agent_1 import GraphState
from agents.agent_3 import _is_count_field
from agents.rule_definitions import rule_manifest
from main import update_reliability

warnings.filterwarnings("ignore")

CHARTS_DIR = "outputs/charts"
os.makedirs(CHARTS_DIR, exist_ok=True)


def _clear_chart_dir():
    for filename in os.listdir(CHARTS_DIR):
        if not filename.lower().endswith(".png"):
            continue
        path = os.path.join(CHARTS_DIR, filename)
        if os.path.isfile(path):
            os.remove(path)

# ── palette ───────────────────────────────────────────────────────────────────
COLORS = {
    "primary":   "#2563EB",
    "secondary": "#16A34A",
    "accent":    "#DC2626",
    "warning":   "#D97706",
    "purple":    "#7C3AED",
    "bars":      ["#2563EB", "#16A34A", "#DC2626", "#D97706", "#7C3AED",
                  "#0891B2", "#DB2777", "#65A30D", "#EA580C", "#4F46E5"],
}

def _save(fig, name):
    path = os.path.join(CHARTS_DIR, f"{name}.png")
    if os.path.exists(path):
        os.remove(path)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path

# ── filter out internal validation columns ──
_VALIDATION_SUFFIXES = ("_parse_failed", "_range_failed")
_BACKUP_SUFFIXES = ("_raw", "_scaled", "_was_clipped")
ANOMALY_Z_THRESHOLD = 3.5

# A heatmap of near-zero correlations tells the reader nothing useful - skip
# drawing it rather than dumping a wall of gray/pale cells into the report.
CORRELATION_HEATMAP_MIN_R = 0.3
# Global cap on total charts across all families, applied by informativeness
# ranking rather than truncating whichever family happens to run last.
MAX_CHARTS_PER_REPORT = int(os.getenv("MAX_CHARTS_PER_REPORT", "16"))


def _numeric_cols(df, schema_blueprint):
    """Return numeric columns, excluding validation suffixes and identifiers/datetimes."""
    cols = []
    for col in df.columns:
        if col.endswith(_VALIDATION_SUFFIXES):
            continue
        if col.endswith(_BACKUP_SUFFIXES):
            continue
        meta = schema_blueprint.get(col, {})
        if meta.get("analysis_allowed") is False:
            continue
        if meta.get("is_identifier"):
            continue
        if meta.get("semantic_tag") in ("datetime", "identifier"):
            continue
        if pd.api.types.is_bool_dtype(df[col]):
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            cols.append(col)
    return cols

# Date-derived column suffixes that are mechanically correlated and add noise to
# correlation heatmaps and regression trend outputs.
_DATE_DERIVED_SUFFIXES = (
    "_year", "_month", "_quarter", "_day",
    "_day_of_week", "_is_weekend", "_week_of_year",
)

def _is_date_derived(col: str) -> bool:
    return any(col.endswith(s) for s in _DATE_DERIVED_SUFFIXES)


def _has_meaningful_variation(values, min_cv: float = 0.03) -> bool:
    """Guard against drawing a time-series chart for data that is essentially flat.
    A flat line/bar chart with no real movement isn't a meaningful insight - it's
    just noise. Uses coefficient of variation (std / mean) as a cheap, scale-free
    signal-strength check."""
    s = pd.Series(values).dropna()
    if len(s) < 2:
        return False
    mean = s.mean()
    if mean == 0:
        return bool(s.std() > 0)
    return bool((s.std() / abs(mean)) >= min_cv)


def _categorical_cols(df, schema_blueprint):
    """Return categorical columns, excluding validation suffixes and identifiers/datetimes."""
    cols = []
    for col in df.columns:
        if col.endswith(_VALIDATION_SUFFIXES):
            continue
        meta = schema_blueprint.get(col, {})
        if meta.get("analysis_allowed") is False:
            continue
        if meta.get("is_identifier"):
            continue
        if meta.get("semantic_tag") in ("datetime", "identifier"):
            continue
        # pandas 3.x reports text-column dtype as literally "str" (not "object"/
        # "string") via str(dtype) - without checking for it here, every
        # "geographic"-tagged column (e.g. Region) on pandas 3.x silently fell out
        # of both the dtype check AND the semantic_tag check below (which only
        # matched "categorical_label"), excluding it from every ranking/insight
        # function downstream (docs/known_issues.md #3).
        is_string_col = (
            df[col].dtype == object
            or str(df[col].dtype) in ("string", "str")
            or (hasattr(df[col].dtype, "name") and df[col].dtype.name in ("string", "str"))
        )
        if is_string_col or meta.get("semantic_tag") in ("categorical_label", "geographic"):
            cols.append(col)
    return cols


def _find_col(df, keywords, schema_blueprint):
    """Find a column containing any keyword; restrict to valid numeric columns."""
    numeric_cols = _numeric_cols(df, schema_blueprint)
    for col in numeric_cols:
        for kw in keywords:
            if re.search(rf'\b{re.escape(kw)}\b', col.lower()):
                return col
    return None

def _find_revenue_col(df, schema_blueprint):
    """Locate the primary revenue/sales metric column.

    Preference order:
    1. A column Agent 2 explicitly tagged financial_role="revenue" - this
       avoids conflating a customer/personal attribute (like "Income") with
       company revenue, which naive keyword matching cannot distinguish.
    2. A derived total-spend proxy (sum of per-category spend columns, e.g.
       MntWines/MntFruits) computed by Agent 3 when the dataset has no real
       revenue column at all.
    3. Whole-word keyword match on common revenue/sales column names.
       "income" is intentionally NOT included here - see agent_2.py's
       financial_role tagging for why customer income != company revenue.
    Candidates with no real variation (e.g. a constant placeholder column)
    are skipped in favor of the next tier - a flat "revenue" column is not
    a usable business metric even if the name/tag matches.
    """
    numeric_cols = _numeric_cols(df, schema_blueprint)

    for col in numeric_cols:
        if (
            schema_blueprint.get(col, {}).get("financial_role") == "revenue"
            and _has_meaningful_variation(df[col])
        ):
            return col

    if "derived_total_spend" in numeric_cols and _has_meaningful_variation(df["derived_total_spend"]):
        return "derived_total_spend"

    keywords = ["total_sales", "revenue", "net_sales", "total_amount", "sales"]
    keyword_col = _find_col(df, keywords, schema_blueprint)
    if keyword_col and _has_meaningful_variation(df[keyword_col]):
        return keyword_col
    return None


def _revenue_label(rev_col):
    """Human-friendly label for whatever metric _find_revenue_col resolved to.

    Chart titles/axes must describe what the column actually is (e.g.
    "Total Spend" or "Income") rather than always saying "Revenue" - that
    mismatch is what caused honest column titles to sit under dishonest
    "Revenue ..." captions/narrative.
    """
    if not rev_col:
        return rev_col
    label = rev_col[len("derived_"):] if rev_col.startswith("derived_") else rev_col
    return label.replace("_", " ").strip().title()


def _slug(label):
    """Filesystem/caption-safe slug so saved chart filenames match their titles."""
    slug = re.sub(r"[^a-z0-9]+", "_", str(label).lower()).strip("_")
    return slug or "value"


def _datetime_cols(df, schema_blueprint):
    cols = []
    for col, meta in schema_blueprint.items():
        if col not in df.columns:
            continue
        if meta.get("semantic_tag") == "datetime" or meta.get("intended_type") == "datetime":
            cols.append(col)
    return cols


def _build_chart_plan(df, schema_blueprint):
    numeric_cols = _numeric_cols(df, schema_blueprint)
    categorical_cols = _categorical_cols(df, schema_blueprint)
    datetime_cols = _datetime_cols(df, schema_blueprint)
    revenue_col = _find_revenue_col(df, schema_blueprint)
    profit_col = _find_profit_col(df, schema_blueprint)
    derived_cols = [c for c in df.columns if c.startswith("derived_") and pd.api.types.is_numeric_dtype(df[c])]

    time_axis_cols = [c for c in df.columns if c.endswith(("_year", "_month", 
        "_quarter", "_day", "_day_of_week", "_is_weekend", "_week_of_year"))]
    has_time_axis = bool(datetime_cols or time_axis_cols)
    month_col_present = any(c.endswith("_month") for c in df.columns)

    discount_col = _find_numeric_col_by_phrases(
        df, schema_blueprint, ["discount percentage", "discount pct", "discount rate", "discount"]
    )
    returned_col = _find_boolean_col_by_phrases(df, ["returned", "is returned", "return flag"])
    margin_col = _find_numeric_col_by_phrases(df, schema_blueprint, ["profit margin", "margin pct", "margin"])
    category_col = _find_categorical_col_by_phrases(df, schema_blueprint, ["product category", "category"])
    rep_col = _find_categorical_col_by_phrases(df, schema_blueprint, ["sales representative", "representative"])
    segment_col = _find_categorical_col_by_phrases(df, schema_blueprint, ["customer segment", "segment"])
    region_col = _find_categorical_col_by_phrases(df, schema_blueprint, ["region"])
    shipping_col = _find_numeric_col_by_phrases(df, schema_blueprint, ["shipping cost", "shipping"])
    lead_time_col = "derived_days_to_ship" if "derived_days_to_ship" in df.columns else None

    if revenue_col and has_time_axis and categorical_cols:
        dataset_type = "sales_timeseries"
    elif revenue_col and categorical_cols:
        dataset_type = "sales_categorical"
    elif has_time_axis and numeric_cols:
        dataset_type = "time_series"
    elif categorical_cols and numeric_cols:
        dataset_type = "mixed_analytics"
    elif numeric_cols:
        dataset_type = "numeric_table"
    elif categorical_cols:
        dataset_type = "categorical_table"
    else:
        dataset_type = "general_table"

    return {
        "dataset_type": dataset_type,
        "numeric_columns": numeric_cols,
        "categorical_columns": categorical_cols,
        "datetime_columns": datetime_cols,
        "revenue_column": revenue_col,
        "profit_column": profit_col,
        "derived_columns": derived_cols,
        "has_time_axis": has_time_axis,
        "chart_families": {
            "descriptive": True,
            "correlation": len(numeric_cols) >= 2,
            "growth_rates": bool(revenue_col and has_time_axis),
            "top_bottom": bool(revenue_col and categorical_cols),
            "profit_breakdown": bool(profit_col and categorical_cols),
            "seasonality": bool(revenue_col and has_time_axis),
            "anomalies": len(numeric_cols) >= 1,
            "distributions": len(categorical_cols) >= 1,
            "regression": bool(revenue_col and has_time_axis),
            "distribution_charts": len(numeric_cols) >= 1,
            "derived_metrics": len(derived_cols) >= 1,
            "discount_return_rate": bool(discount_col and returned_col),
            "category_margin_trend": bool(margin_col and category_col and month_col_present),
            "rep_discount_margin": bool(rep_col and discount_col and margin_col),
            "segment_order_value": bool(segment_col and revenue_col),
            "region_shipping_cost": bool(shipping_col and region_col),
            "shipping_lead_time": bool(lead_time_col),
        },
    }

# ─────────────────────────────────────────────────────────────────────────────
# 1 — DESCRIPTIVE STATISTICS
# ─────────────────────────────────────────────────────────────────────────────

def _descriptive_stats(df, schema_blueprint):
    result = {}
    for col in _numeric_cols(df, schema_blueprint):
        s = df[col].dropna()
        if len(s) == 0:
            continue
        result[col] = {
            "count":    int(s.count()),
            "mean":     round(float(s.mean()), 4),
            "median":   round(float(s.median()), 4),
            "std":      round(float(s.std()), 4),
            "variance": round(float(s.var()), 4),
            "min":      round(float(s.min()), 4),
            "max":      round(float(s.max()), 4),
            "q1":       round(float(s.quantile(0.25)), 4),
            "q3":       round(float(s.quantile(0.75)), 4),
            "skewness": round(float(s.skew()), 4),
            "kurtosis": round(float(s.kurt()), 4),
        }
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 1.5 — LEAKAGE / JUNK COLUMN DETECTION
# ─────────────────────────────────────────────────────────────────────────────

# Bare/short tokens ("id", "index") are matched whole-word only, against the
# column name split on non-alphanumeric boundaries and camelCase transitions -
# a naive substring check on these would false-positive on names like "Valid"
# or "Guide" (see agent_3._find_col for the same lesson learned on keyword
# matching elsewhere in this codebase). Multi-character/underscore-anchored
# patterns (e.g. "_score", "predicted_") are distinctive enough to stay as
# plain substring checks.
_LEAKAGE_WHOLE_WORD_PATTERNS = frozenset({"id", "index"})
_LEAKAGE_CAMEL_SPLIT = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_LEAKAGE_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def _leakage_name_tokens(col: str) -> list[str]:
    normalized = _LEAKAGE_CAMEL_SPLIT.sub("_", col).lower()
    return [t for t in _LEAKAGE_TOKEN_SPLIT.split(normalized) if t]


def flag_leakage_columns(df, corr_matrix, name_patterns=None):
    """Flag columns likely to be IDs, model outputs, or leakage artifacts.

    Runs on the correlation matrix as a safety net *in addition to* Agent 2's
    semantic tagging (`is_identifier`/`semantic_tag`) - it exists specifically
    to catch columns the schema blueprint mistagged or never saw (e.g. an
    external model's output score/probability columns baked into the raw
    file, like the well-known "Naive_Bayes_Classifier_..." leakage columns in
    some public churn datasets). Flagged columns are excluded from headline
    "Top Correlations" findings and reported to Insight Generation separately
    instead of being narrated as business signal.
    """
    name_patterns = name_patterns or [
        "classifier", "naive_bayes", "_score", "_proba", "predicted_",
        "id", "clientnum", "customerid", "index", "_uuid",
    ]
    flagged = set()

    # 1. Name-based heuristic (whole-word for ambiguous short tokens).
    for col in df.columns:
        low = col.lower()
        tokens = None
        for pattern in name_patterns:
            if pattern in _LEAKAGE_WHOLE_WORD_PATTERNS:
                if tokens is None:
                    tokens = _leakage_name_tokens(col)
                if pattern in tokens:
                    flagged.add(col)
                    break
            elif pattern in low:
                flagged.add(col)
                break

    # 2. Near-perfect correlation with exactly one other column, near-zero
    #    with everything else = likely two halves of the same external
    #    computation (e.g. complementary probabilities).
    for col in corr_matrix.columns:
        row = corr_matrix[col].drop(col)
        near_one = (row.abs() > 0.98).sum()
        near_zero = (row.abs() < 0.1).sum()
        if near_one == 1 and near_zero >= len(row) - 2:
            flagged.add(col)

    # 3. Pure identifiers: unique count == row count, non-target.
    for col in df.columns:
        if len(df) > 0 and df[col].nunique() == len(df) and str(df[col].dtype) in ("int64", "object", "str", "string"):
            flagged.add(col)

    return flagged


# ─────────────────────────────────────────────────────────────────────────────
# 2 — CORRELATION MATRIX
# ─────────────────────────────────────────────────────────────────────────────

def _get_derivation_map(schema_blueprint):
    """Agent 3's known revenue/discount/cost/profit formula relationships
    (e.g. derived_profit = revenue - cost), recorded in
    schema_blueprint['__metadata__']['derived_metric_sources'] at derivation
    time. Used to exclude tautological pairs from "Top Correlations" by
    explicit formula knowledge rather than a correlation-value cutoff
    (docs/known_issues.md #5).
    """
    metadata = schema_blueprint.get("__metadata__")
    if not isinstance(metadata, dict):
        return {}
    derivation_map = metadata.get("derived_metric_sources")
    return derivation_map if isinstance(derivation_map, dict) else {}


def _is_formulaic_pair(c1, c2, derivation_map):
    """True if c1/c2 are directly related by a known formula (one is derived
    from the other), not just incidentally correlated."""
    return c2 in derivation_map.get(c1, []) or c1 in derivation_map.get(c2, [])


def _is_exact_derived_pair(c1, c2, corr_df, derivation_map):
    """Catch exact identities where the derived formula is indirect.

    For example, revenue_per_unit = total_revenue / units and total_revenue =
    unit_price * units, so revenue_per_unit is exactly unit_price even though
    Unit Price is not listed as a direct source in the derivation map.
    """
    if not (c1.startswith("derived_") or c2.startswith("derived_")):
        return False
    if not derivation_map.get(c1) and not derivation_map.get(c2):
        return False
    left = pd.to_numeric(corr_df[c1], errors="coerce")
    right = pd.to_numeric(corr_df[c2], errors="coerce")
    return bool(len(left) >= 3 and np.isclose(left, right, rtol=1e-9, atol=1e-9).all())


def _correlation(df, schema_blueprint):
    # Use every analysis-eligible numeric column (per Agent 2's schema tags),
    # not a fixed name whitelist - that way this works on any dataset, not just
    # ones shaped like a sales CSV. Date-derived columns are excluded because
    # they're mechanically correlated with each other and the base date column,
    # adding noise rather than insight.
    cols = [
        c for c in _numeric_cols(df, schema_blueprint)
        if not _is_date_derived(c)
    ]
    if len(cols) < 2:
        return {}, []

    corr_df = df[cols].dropna()
    if len(corr_df) < 3:
        return {}, []

    pearson  = corr_df.corr(method="pearson").round(4)
    spearman = corr_df.corr(method="spearman").round(4)

    flagged_columns = flag_leakage_columns(df, pearson)
    derivation_map = _get_derivation_map(schema_blueprint)

    strong_pairs = []
    max_abs_r = 0.0
    excluded_pairs = []
    formulaic_pairs = []
    for i, c1 in enumerate(cols):
        for c2 in cols[i+1:]:
            r = pearson.loc[c1, c2]
            max_abs_r = max(max_abs_r, abs(float(r)))
            if abs(r) >= 0.5:
                pair = {
                    "col1": c1, "col2": c2,
                    "pearson_r": round(float(r), 4),
                    "direction": "positive" if r > 0 else "negative",
                    "strength":  "strong" if abs(r) >= 0.7 else "moderate",
                }
                if _is_formulaic_pair(c1, c2, derivation_map) or _is_exact_derived_pair(c1, c2, corr_df, derivation_map):
                    formulaic_pairs.append(pair)
                elif c1 in flagged_columns or c2 in flagged_columns:
                    excluded_pairs.append(pair)
                else:
                    strong_pairs.append(pair)

    result = {
        "pearson":         pearson.to_dict(),
        "spearman":        spearman.to_dict(),
        "strong_pairs":    strong_pairs,
        "max_abs_r":       round(max_abs_r, 4),
        "flagged_columns": sorted(flagged_columns & set(cols)),
        "excluded_pairs":  excluded_pairs,
        "formulaic_pairs": formulaic_pairs,
    }
    chart_candidates = []

    # A wall of near-zero correlation cells is noise, not insight - only draw
    # the heatmap when at least one pair shows a real relationship.
    if max_abs_r >= CORRELATION_HEATMAP_MIN_R:
        fig, ax = plt.subplots(figsize=(max(6, len(cols)), max(5, len(cols)-1)))
        im = ax.imshow(pearson.values, cmap="RdYlGn", vmin=-1, vmax=1, aspect="auto")
        plt.colorbar(im, ax=ax, shrink=0.8)
        ax.set_xticks(range(len(cols)))
        ax.set_yticks(range(len(cols)))
        ax.set_xticklabels(cols, rotation=45, ha="right", fontsize=9)
        ax.set_yticklabels(cols, fontsize=9)
        for i in range(len(cols)):
            for j in range(len(cols)):
                ax.text(j, i, f"{pearson.values[i,j]:.2f}",
                        ha="center", va="center", fontsize=8,
                        color="black" if abs(pearson.values[i,j]) < 0.7 else "white")
        ax.set_title("Pearson Correlation Heatmap", fontsize=13, fontweight="bold", pad=12)
        fig.tight_layout()
        path = _save(fig, "correlation_heatmap")
        chart_candidates.append({
            "path": path, "family": "correlation_heatmap",
            "score": round(max_abs_r * 100, 1),
            "reason": f"max |pearson r|={max_abs_r:.2f}",
        })

    # Give the single strongest relationship an actual scatter plot instead of
    # making the reader infer it from one heatmap cell - this is also what
    # makes the chart set vary by dataset instead of always looking the same.
    if strong_pairs:
        top_pair = max(strong_pairs, key=lambda p: abs(p["pearson_r"]))
        c1, c2 = top_pair["col1"], top_pair["col2"]
        pair_df = df[[c1, c2]].dropna()
        if len(pair_df) >= 3:
            fig, ax = plt.subplots(figsize=(6.5, 5))
            ax.scatter(pair_df[c1], pair_df[c2], color=COLORS["primary"],
                       alpha=0.6, s=35, edgecolor="white")
            slope, intercept = np.polyfit(pair_df[c1].to_numpy(dtype="float64"),
                                           pair_df[c2].to_numpy(dtype="float64"), 1)
            xs = np.linspace(pair_df[c1].min(), pair_df[c1].max(), 100)
            ax.plot(xs, slope * xs + intercept, color=COLORS["accent"],
                    linewidth=2, linestyle="--")
            ax.set_xlabel(c1, fontsize=10)
            ax.set_ylabel(c2, fontsize=10)
            ax.set_title(f"{c1} vs {c2} (r={top_pair['pearson_r']:.2f}, {top_pair['strength']})",
                         fontsize=12, fontweight="bold")
            fig.tight_layout()
            scatter_path = _save(fig, f"scatter_{_slug(c1)}_vs_{_slug(c2)}")
            chart_candidates.append({
                "path": scatter_path, "family": "correlation_scatter",
                "score": round(abs(top_pair["pearson_r"]) * 100, 1),
                "reason": f"strongest pair r={top_pair['pearson_r']:.2f}",
            })

    return result, chart_candidates


# ─────────────────────────────────────────────────────────────────────────────
# 3 — GROWTH RATES (MoM and QoQ)
# ─────────────────────────────────────────────────────────────────────────────

def _growth_rates(df, schema_blueprint):
    result = {}
    chart_candidates = []

    rev_col = _find_revenue_col(df, schema_blueprint)
    if not rev_col or not pd.api.types.is_numeric_dtype(df[rev_col]):
        return result, chart_candidates

    label = _revenue_label(rev_col)
    slug = _slug(label)

    month_col = next((c for c in df.columns if c.endswith("_month")), None)
    year_col  = next((c for c in df.columns if c.endswith("_year")), None)

    if month_col and year_col:
        monthly = (
            df.groupby([year_col, month_col])[rev_col]
            .sum()
            .reset_index()
            .sort_values([year_col, month_col])
        )
        monthly["mom_growth_pct"] = monthly[rev_col].pct_change() * 100
        monthly["label"] = (
            monthly[year_col].astype(str) + "-M"
            + monthly[month_col].astype(str).str.zfill(2)
        )
        result["monthly"] = monthly.dropna().to_dict(orient="records")

        if len(monthly) >= 2 and _has_meaningful_variation(monthly[rev_col]):
            fig, ax = plt.subplots(figsize=(max(8, len(monthly)), 4))
            ax.bar(monthly["label"], monthly[rev_col],
                   color=COLORS["primary"], alpha=0.85, label=label)
            ax2 = ax.twinx()
            valid = monthly.dropna(subset=["mom_growth_pct"])
            ax2.plot(valid["label"], valid["mom_growth_pct"],
                     color=COLORS["accent"], marker="o", linewidth=2, label="MoM Growth %")
            ax2.axhline(0, color="gray", linewidth=0.8, linestyle="--")
            ax.set_xlabel("Month", fontsize=10)
            ax.set_ylabel(label, fontsize=10)
            ax2.set_ylabel("MoM Growth %", fontsize=10)
            ax.set_title(f"Monthly {label} & MoM Growth", fontsize=13, fontweight="bold")
            plt.xticks(rotation=45, ha="right")
            lines1, labels1 = ax.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax.legend(lines1+lines2, labels1+labels2, loc="upper left", fontsize=9)
            fig.tight_layout()
            growth_path = _save(fig, f"monthly_{slug}_growth")
            max_swing = float(valid["mom_growth_pct"].abs().max()) if not valid.empty else 0.0
            chart_candidates.append({
                "path": growth_path, "family": "growth_rates_monthly",
                "score": round(min(100.0, max_swing), 1),
                "reason": f"max MoM swing={max_swing:.1f}%",
            })

    quarter_col = next((c for c in df.columns if c.endswith("_quarter")), None)
    if quarter_col and year_col:
        quarterly = (
            df.groupby([year_col, quarter_col])[rev_col]
            .sum()
            .reset_index()
            .sort_values([year_col, quarter_col])
        )
        quarterly["qoq_growth_pct"] = quarterly[rev_col].pct_change() * 100
        quarterly["label"] = (
            quarterly[year_col].astype(str) + "-Q"
            + quarterly[quarter_col].astype(str)
        )
        result["quarterly"] = quarterly.dropna().to_dict(orient="records")

        if len(quarterly) >= 2 and _has_meaningful_variation(quarterly[rev_col]):
            fig, ax = plt.subplots(figsize=(max(6, len(quarterly)+2), 4))
            bars = ax.bar(quarterly["label"], quarterly[rev_col],
                          color=COLORS["secondary"], alpha=0.85)
            for bar, val in zip(bars, quarterly[rev_col]):
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                        f"{val:,.0f}", ha="center", va="bottom", fontsize=9)
            ax.set_title(f"Quarterly {label}", fontsize=13, fontweight="bold")
            ax.set_ylabel(label)
            ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
            fig.tight_layout()
            quarterly_path = _save(fig, f"quarterly_{slug}")
            valid_q = quarterly.dropna(subset=["qoq_growth_pct"])
            max_swing_q = float(valid_q["qoq_growth_pct"].abs().max()) if not valid_q.empty else 0.0
            chart_candidates.append({
                "path": quarterly_path, "family": "growth_rates_quarterly",
                "score": round(min(100.0, max_swing_q), 1),
                "reason": f"max QoQ swing={max_swing_q:.1f}%",
            })

    return result, chart_candidates


# ─────────────────────────────────────────────────────────────────────────────
# 4 — TOP / BOTTOM N RANKINGS
# ─────────────────────────────────────────────────────────────────────────────

# docs/known_issues.md #3: Region/Product_Category/Customer_Segment/
# Sales_Representative-style dimensions were never guaranteed a ranking slot -
# they simply lost the "top 3 most differentiated" selection race against
# noisier columns (e.g. Customer_City, Product_Name). Matched by keyword
# (not hardcoded exact column names) so it generalizes to similarly-named
# columns in other datasets.
PRIORITY_DIMENSION_KEYWORDS = ("region", "category", "segment", "representative")
MAX_RANKING_DIMENSIONS = 6  # was an unconditional top-3; raised to leave room for priority dims


def _is_priority_dimension(col):
    tokens = re.findall(r"[a-z0-9]+", col.lower())
    return any(kw in tokens for kw in PRIORITY_DIMENSION_KEYWORDS)


def _select_ranking_dimensions(df, cat_cols, metric_col):
    """Pick categorical columns to rank `metric_col` by.

    Business-priority dimensions (region/category/segment/representative-style
    columns, matched by keyword) always get a slot if they pass the basic
    cardinality sanity check, topped up with the most metric-differentiated of
    the rest, up to MAX_RANKING_DIMENSIONS total. A column with <2 unique
    values can't be ranked; one with >20 groups makes "bottom N" meaningless
    single-row noise rather than a real underperformer.
    """
    priority_cols = []
    other_candidates = []
    for cat_col in cat_cols:
        nunique = df[cat_col].nunique(dropna=True)
        if nunique < 2 or nunique > 20:
            continue
        totals = df.groupby(cat_col)[metric_col].sum()
        grand_total = totals.sum()
        if grand_total == 0:
            continue
        shares = totals / grand_total * 100
        spread = float(shares.max() - shares.min())
        if _is_priority_dimension(cat_col):
            priority_cols.append(cat_col)
        else:
            other_candidates.append((cat_col, spread))

    other_candidates.sort(key=lambda c: c[1], reverse=True)
    remaining_slots = max(0, MAX_RANKING_DIMENSIONS - len(priority_cols))
    return priority_cols + [c for c, _ in other_candidates[:remaining_slots]]


def _find_profit_col(df, schema_blueprint):
    """Locate the primary profit column, explicitly excluding margin/percentage
    columns (e.g. "Profit_Margin") so profit breakdowns sum an absolute
    currency amount, not a percentage."""
    numeric_cols = _numeric_cols(df, schema_blueprint)
    exact = [c for c in numeric_cols if c.lower() == "profit"]
    if exact:
        return exact[0]
    for col in numeric_cols:
        tokens = re.findall(r"[a-z0-9]+", col.lower())
        if "profit" in tokens and "margin" not in tokens:
            return col
    return None


def _top_bottom_rankings(df, schema_blueprint, n=5):
    result = {}
    chart_candidates = []

    rev_col = _find_revenue_col(df, schema_blueprint)
    if not rev_col or not pd.api.types.is_numeric_dtype(df[rev_col]):
        return result, chart_candidates

    label = _revenue_label(rev_col)
    slug = _slug(label)
    cat_cols = _categorical_cols(df, schema_blueprint)
    selected_cat_cols = _select_ranking_dimensions(df, cat_cols, rev_col)

    for cat_col in selected_cat_cols:
        grouped = (
            df.groupby(cat_col)[rev_col]
            .agg(["sum", "mean", "count"])
            .reset_index()
            .rename(columns={"sum": "total_revenue", "mean": "avg_revenue", "count": "records"})
            .sort_values("total_revenue", ascending=False)
        )
        grouped["revenue_share_pct"] = (
            grouped["total_revenue"] / grouped["total_revenue"].sum() * 100
        ).round(2)

        top_n    = grouped.head(n)
        bottom_n = grouped.tail(n)

        result[cat_col] = {
            "top":    top_n.to_dict(orient="records"),
            "bottom": bottom_n.to_dict(orient="records"),
            "total_categories": len(grouped),
        }

        fig, ax = plt.subplots(figsize=(8, max(3, len(top_n) * 0.6 + 1)))
        bars = ax.barh(
            top_n[cat_col].astype(str),
            top_n["total_revenue"],
            color=COLORS["bars"][:len(top_n)],
            alpha=0.88,
        )
        for bar, pct in zip(bars, top_n["revenue_share_pct"]):
            ax.text(bar.get_width(), bar.get_y() + bar.get_height()/2,
                    f"  {pct:.1f}%", va="center", fontsize=9)
        ax.set_xlabel(f"Total {label}", fontsize=10)
        ax.set_title(f"Top {n} {cat_col} by {label}", fontsize=13, fontweight="bold")
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        ax.invert_yaxis()
        fig.tight_layout()
        ranking_path = _save(fig, f"top_{n}_{cat_col.lower()}_{slug}")
        spread = float(grouped["revenue_share_pct"].max() - grouped["revenue_share_pct"].min())
        chart_candidates.append({
            "path": ranking_path, "family": "top_bottom_ranking",
            "score": round(min(100.0, spread), 1),
            "reason": f"{cat_col} revenue share spread={spread:.1f}pp",
        })

    return result, chart_candidates


def _profit_breakdown_by_dimension(df, schema_blueprint, n=5):
    """Same ranking treatment as `_top_bottom_rankings` but for profit instead
    of revenue - kept as a separate stats key (`profit_breakdown`) rather than
    reshaping `top_bottom`'s existing dict, so existing consumers of
    `total_revenue`/`avg_revenue`/`revenue_share_pct` are unaffected."""
    result = {}
    chart_candidates = []

    profit_col = _find_profit_col(df, schema_blueprint)
    if not profit_col or not pd.api.types.is_numeric_dtype(df[profit_col]):
        return result, chart_candidates

    label = profit_col.replace("_", " ").strip().title()
    slug = _slug(label)
    cat_cols = _categorical_cols(df, schema_blueprint)
    selected_cat_cols = _select_ranking_dimensions(df, cat_cols, profit_col)

    for cat_col in selected_cat_cols:
        grouped = (
            df.groupby(cat_col)[profit_col]
            .agg(["sum", "mean", "count"])
            .reset_index()
            .rename(columns={"sum": "total_profit", "mean": "avg_profit", "count": "records"})
            .sort_values("total_profit", ascending=False)
        )
        total = grouped["total_profit"].sum()
        grouped["profit_share_pct"] = (grouped["total_profit"] / total * 100).round(2) if total else 0.0

        top_n = grouped.head(n)
        bottom_n = grouped.tail(n)

        result[cat_col] = {
            "top": top_n.to_dict(orient="records"),
            "bottom": bottom_n.to_dict(orient="records"),
            "total_categories": len(grouped),
        }

        fig, ax = plt.subplots(figsize=(8, max(3, len(top_n) * 0.6 + 1)))
        bars = ax.barh(
            top_n[cat_col].astype(str),
            top_n["total_profit"],
            color=COLORS["bars"][:len(top_n)],
            alpha=0.88,
        )
        for bar, pct in zip(bars, top_n["profit_share_pct"]):
            ax.text(bar.get_width(), bar.get_y() + bar.get_height()/2,
                    f"  {pct:.1f}%", va="center", fontsize=9)
        ax.set_xlabel(f"Total {label}", fontsize=10)
        ax.set_title(f"Top {n} {cat_col} by {label}", fontsize=13, fontweight="bold")
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        ax.invert_yaxis()
        fig.tight_layout()
        chart_path = _save(fig, f"top_{n}_{cat_col.lower()}_{slug}")
        spread = float(grouped["profit_share_pct"].max() - grouped["profit_share_pct"].min()) if not grouped.empty else 0.0
        chart_candidates.append({
            "path": chart_path, "family": "profit_breakdown",
            "score": round(min(100.0, spread), 1),
            "reason": f"{cat_col} profit share spread={spread:.1f}pp",
        })

    return result, chart_candidates


# ─────────────────────────────────────────────────────────────────────────────
# 5 — SEASONALITY DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def _seasonality(df, schema_blueprint):
    result = {}
    chart_candidates = []

    rev_col = _find_revenue_col(df, schema_blueprint)
    if not rev_col or not pd.api.types.is_numeric_dtype(df[rev_col]):
        return result, chart_candidates

    label = _revenue_label(rev_col)
    slug = _slug(label)

    month_names = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                   7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}

    month_col = next((c for c in df.columns if c.endswith("_month")), None)
    if month_col:
        monthly_avg = df.groupby(month_col)[rev_col].mean().reset_index()
        monthly_avg["month_name"] = monthly_avg[month_col].map(month_names)
        best_month  = monthly_avg.loc[monthly_avg[rev_col].idxmax()]
        worst_month = monthly_avg.loc[monthly_avg[rev_col].idxmin()]

        result["monthly"] = {
            "avg_by_month": monthly_avg.to_dict(orient="records"),
            "best_month":   {"month": best_month["month_name"],  "avg_revenue": round(float(best_month[rev_col]), 2)},
            "worst_month":  {"month": worst_month["month_name"], "avg_revenue": round(float(worst_month[rev_col]), 2)},
        }

        if _has_meaningful_variation(monthly_avg[rev_col]):
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(monthly_avg["month_name"], monthly_avg[rev_col],
                    marker="o", color=COLORS["primary"], linewidth=2.5, markersize=7)
            ax.fill_between(range(len(monthly_avg)), monthly_avg[rev_col],
                            alpha=0.1, color=COLORS["primary"])
            ax.set_xticks(range(len(monthly_avg)))
            ax.set_xticklabels(monthly_avg["month_name"])
            ax.set_title(f"Monthly {label} Seasonality", fontsize=13, fontweight="bold")
            ax.set_ylabel(f"Avg {label}", fontsize=10)
            ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
            ax.grid(axis="y", linestyle="--", alpha=0.5)
            fig.tight_layout()
            monthly_path = _save(fig, f"monthly_{slug}_seasonality")
            spread = abs(float(best_month[rev_col]) - float(worst_month[rev_col]))
            relative_spread = spread / max(abs(float(worst_month[rev_col])), 1e-9) * 100
            chart_candidates.append({
                "path": monthly_path, "family": "seasonality_monthly",
                "score": round(min(100.0, relative_spread), 1),
                "reason": f"best/worst month spread={relative_spread:.1f}%",
            })

    quarter_col = next((c for c in df.columns if c.endswith("_quarter")), None)
    if quarter_col:
        quarterly_avg = df.groupby(quarter_col)[rev_col].mean().reset_index()
        quarterly_avg["quarter_name"] = "Q" + quarterly_avg[quarter_col].astype(str)
        best_q  = quarterly_avg.loc[quarterly_avg[rev_col].idxmax()]
        worst_q = quarterly_avg.loc[quarterly_avg[rev_col].idxmin()]

        result["quarterly"] = {
            "avg_by_quarter": quarterly_avg.to_dict(orient="records"),
            "best_quarter":   {"quarter": best_q["quarter_name"],  "avg_revenue": round(float(best_q[rev_col]), 2)},
            "worst_quarter":  {"quarter": worst_q["quarter_name"], "avg_revenue": round(float(worst_q[rev_col]), 2)},
        }

        if _has_meaningful_variation(quarterly_avg[rev_col]):
            fig, ax = plt.subplots(figsize=(6, 4))
            bars = ax.bar(quarterly_avg["quarter_name"], quarterly_avg[rev_col],
                          color=COLORS["bars"][:4], alpha=0.88, width=0.5)
            for bar, val in zip(bars, quarterly_avg[rev_col]):
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                        f"{val:,.0f}", ha="center", va="bottom", fontsize=9)
            ax.set_title(f"Quarterly {label} Seasonality", fontsize=13, fontweight="bold")
            ax.set_ylabel(f"Avg {label}", fontsize=10)
            ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
            fig.tight_layout()
            quarterly_path = _save(fig, f"quarterly_{slug}_seasonality")
            spread_q = abs(float(best_q[rev_col]) - float(worst_q[rev_col]))
            relative_spread_q = spread_q / max(abs(float(worst_q[rev_col])), 1e-9) * 100
            chart_candidates.append({
                "path": quarterly_path, "family": "seasonality_quarterly",
                "score": round(min(100.0, relative_spread_q), 1),
                "reason": f"best/worst quarter spread={relative_spread_q:.1f}%",
            })

    dow_col = next((c for c in df.columns if c.endswith("_day_of_week")), None)
    if dow_col:
        day_names = {0:"Mon",1:"Tue",2:"Wed",3:"Thu",4:"Fri",5:"Sat",6:"Sun"}
        dow_avg = df.groupby(dow_col)[rev_col].mean().reset_index()
        dow_avg["day_name"] = dow_avg[dow_col].map(day_names)
        result["day_of_week"] = dow_avg.to_dict(orient="records")

    return result, chart_candidates


# ─────────────────────────────────────────────────────────────────────────────
# 6 — ANOMALY DETECTION (skew-aware: z-score / log-z / IQR)
# ─────────────────────────────────────────────────────────────────────────────

# A plain mean/std z-score assumes a roughly symmetric distribution. Right-skewed
# columns (e.g. per-category spend fields with a long tail of high spenders) blow
# up std enough that z=3.5 either misses real anomalies or, more commonly here,
# flags a large chunk of the legitimate tail as "anomalous". Route skewed columns
# through a transform (log1p) or a robust IQR rule instead.
ANOMALY_SKEW_THRESHOLD = 1.0
# Tukey's "far out" fence (k=3.0), NOT the k=1.5 "outer fence" used for clipping
# in agent_3. On a right-skewed column the 1.5x rule flags a large slice of the
# legitimate long tail (the audit measured ~24% of rows, docs/known_issues.md #6);
# 3.0 keeps this branch a *flag* (surfaced, never removed) while staying far
# enough out to stop over-flagging. Overridable per-dataset via the env var.
ANOMALY_IQR_MULTIPLIER = float(os.getenv("ANOMALY_IQR_MULTIPLIER", "3.0"))


def _impact_columns(df):
    tokens_by_col = {col: set(re.split(r"[^a-z0-9]+", col.lower())) for col in df.columns}
    preferred = {"revenue", "sales", "amount", "total", "value", "price"}
    return [col for col, tokens in tokens_by_col.items() if tokens & preferred]


def _detect_anomalies(df, schema_blueprint, z_threshold=ANOMALY_Z_THRESHOLD):
    result = {}
    all_anomaly_indices = set()
    impact_cols = _impact_columns(df)
    for col in _numeric_cols(df, schema_blueprint):
        s = df[col].dropna()
        if len(s) < 4:
            continue
        std = s.std()
        if std == 0:
            continue

        skewness = float(s.skew())
        method = "zscore"
        if abs(skewness) > ANOMALY_SKEW_THRESHOLD:
            method = "log_zscore" if (s > 0).all() else "iqr"

        if method == "iqr":
            q1, q3 = s.quantile(0.25), s.quantile(0.75)
            iqr = q3 - q1
            if iqr == 0:
                continue
            lower = q1 - ANOMALY_IQR_MULTIPLIER * iqr
            upper = q3 + ANOMALY_IQR_MULTIPLIER * iqr
            anomaly_mask = ((df[col] < lower) | (df[col] > upper)) & df[col].notna()
            col_mean, col_std = float(s.mean()), float(std)
        else:
            if method == "log_zscore":
                transformed = np.log1p(df[col])
                mean, std_calc = np.log1p(s).mean(), np.log1p(s).std()
            else:
                transformed = df[col]
                mean, std_calc = s.mean(), std
            if std_calc == 0:
                continue
            z_scores = (transformed - mean) / std_calc
            anomaly_mask = z_scores.abs() > z_threshold
            anomaly_mask = anomaly_mask.fillna(False)
            col_mean, col_std = float(mean), float(std_calc)

        anomaly_indices = df.index[anomaly_mask].tolist()
        if anomaly_indices:
            all_anomaly_indices.update(anomaly_indices)
            result[col] = {
                "count":           len(anomaly_indices),
                "classification": "statistical_outlier",
                "method":          method,
                "z_threshold":     z_threshold if method != "iqr" else None,
                "skewness":        round(skewness, 4),
                "anomaly_indices": anomaly_indices,
                "anomaly_values":  df.loc[anomaly_indices, col].round(4).tolist(),
                "col_mean":        round(col_mean, 4),
                "col_std":         round(col_std, 4),
            }
            impact_values = df.loc[anomaly_indices, impact_cols].apply(pd.to_numeric, errors="coerce") if impact_cols else df.loc[anomaly_indices, [col]].apply(pd.to_numeric, errors="coerce")
            result[col]["business_impact"] = round(float(impact_values.abs().sum().sum()), 2)

    prioritized = []
    for col, details in result.items():
        prioritized.append({
            "column": col,
            "count": details["count"],
            "business_impact": details["business_impact"],
            "method": details["method"],
            "anomaly_indices": details["anomaly_indices"],
        })
    prioritized.sort(key=lambda item: item["business_impact"], reverse=True)
    summary = {
        "z_threshold": z_threshold,
        "iqr_multiplier": ANOMALY_IQR_MULTIPLIER,
        "flagged_columns": len(result),
        "total_flagged_values": int(sum(v["count"] for v in result.values())),
        "unique_flagged_rows": int(len(all_anomaly_indices)),
        "unique_flagged_row_pct": round((len(all_anomaly_indices) / max(len(df), 1)) * 100, 2),
        "statistical_outlier_rows": int(len(all_anomaly_indices)),
        "statistical_outlier_row_pct": round((len(all_anomaly_indices) / max(len(df), 1)) * 100, 2),
        "prioritized_anomalies": prioritized,
        "business_impact_total": round(sum(item["business_impact"] for item in prioritized), 2),
        "business_impact_columns": impact_cols,
        "rule_manifest": rule_manifest(),
    }
    return result, summary


# ─────────────────────────────────────────────────────────────────────────────
# 6b — STRUCTURAL DATA-QUALITY ISSUES (distinct from statistical outliers)
# ─────────────────────────────────────────────────────────────────────────────
# A statistical outlier (e.g. one very large but legitimate transaction) is NOT
# a data-quality defect; a structural violation (negative quantity, discount
# > 100%, returns exceeding the order) IS. These are counted separately so the
# Data Quality Score can penalize genuine defects without punishing legitimate
# long-tail values (docs/known_issues.md #6, Bug 4).

# Agent 3 already computed these boolean validation flags on the true
# (pre-scaling) values - reuse them instead of re-deriving thresholds on scaled
# columns. See agent_3._validate_count_ranges / _validate_financial_constraints.
_STRUCTURAL_FLAG_SUFFIXES = ("_range_failed", "_rate_failed", "_reconciliation_failed")
STRUCTURAL_RULE_REVIEW_PCT = 90.0


def _percentage_bounds(values, meta=None):
    """Return externally defined bounds; never infer them from the data."""
    meta = meta or {}
    configured_scale = meta.get("unit_scale")
    if configured_scale == "ratio":
        return 0.0, 1.0
    if configured_scale == "percent":
        return 0.0, 100.0
    return 0.0, 100.0


def _detect_data_quality_issues(df, schema_blueprint):
    """Flag rows that violate structural/domain constraints (not mere statistical
    extremes). Returns the unique-row count and a per-rule breakdown."""
    schema_blueprint = schema_blueprint or {}
    issue_rows = set()
    issues_by_rule = {}
    rule_details = {}
    reviewed_rows = set()
    rules_checked = set()

    def _record(mask, rule):
        if mask is None:
            return
        idx = df.index[mask.fillna(False)].tolist()
        if idx:
            pct = round(len(idx) / max(len(df), 1) * 100, 2)
            examples = df.loc[idx[:5]].copy().where(lambda values: values.notna(), None).to_dict(orient="records")
            review_required = pct > STRUCTURAL_RULE_REVIEW_PCT
            issues_by_rule[rule] = issues_by_rule.get(rule, 0) + len(idx)
            rule_details[rule] = {
                "count": len(idx),
                "pct": pct,
                "review_required": review_required,
                "example_rows": examples,
            }
            issue_rows.update(idx)
            if review_required:
                reviewed_rows.update(idx)

    def _num(col):
        return pd.to_numeric(df[col], errors="coerce")

    def _tokens(col):
        return set(re.split(r"[^a-z0-9]+", col.lower()))

    # 1. Agent 3's structural validation flags (count<0/non-int, tax-rate,
    #    reconciliation mismatch, profit-margin out of range).
    for col in df.columns:
        if col.endswith(_STRUCTURAL_FLAG_SUFFIXES):
            _record(_num(col).fillna(0) > 0, col)

    # 2. Domain rules the Agent 3 flags don't already cover, evaluated on each
    #    column's own values.
    for col, meta in schema_blueprint.items():
        if col in df.columns and _is_count_field(col, meta):
            rules_checked.add(f"{col} non-negative count")
            # negative quantity (skip if agent_3 already flagged this column)
            if f"{col}_range_failed" not in df.columns:
                _record(_num(col) < 0, f"{col} < 0")

    for col in df.columns:
        tokens = _tokens(col)
        meta = schema_blueprint.get(col, {}) if isinstance(schema_blueprint, dict) else {}
        if meta.get("semantic_tag") == "percentage" and col not in {
            key.split(" out of ")[0] for key in issues_by_rule
        }:
            rules_checked.add(f"{col} percentage bounds")
            lower, upper = _percentage_bounds(_num(col), meta)
            _record((_num(col) < lower) | (_num(col) > upper), f"{col} out of [{lower:g}, {upper:g}]")
        if "discount" in tokens and meta.get("semantic_tag") != "percentage":
            rules_checked.add(f"{col} discount bounds")
            d = _num(col)
            if "amount" in tokens:
                _record(d < 0, f"{col} < 0")
            else:
                lower, upper = _percentage_bounds(d, meta)
                if not meta.get("unit_scale") and meta.get("semantic_tag") not in {"percentage", "discount"} and upper == 1.0:
                    upper = 100.0
                _record((d < lower) | (d > upper), f"{col} out of [{lower:g}, {upper:g}]")

    # returns exceeding the order quantity, or negative returns
    return_col = next(
        (c for c in df.columns if {"return", "returns", "returned"} & _tokens(c)
         and ({"quantity", "qty", "count", "units"} & _tokens(c) or _tokens(c) <= {"returns", "return", "returned"})),
        None,
    )
    order_col = next(
        (c for c in df.columns if ({"order", "ordered"} & _tokens(c)) and ({"quantity", "qty", "units"} & _tokens(c))),
        None,
    )
    if return_col is not None:
        rules_checked.add(f"{return_col} non-negative")
        r = _num(return_col)
        _record(r < 0, f"{return_col} < 0")
        if order_col is not None and order_col != return_col:
            rules_checked.add(f"{return_col} <= {order_col}")
            _record(r > _num(order_col), f"{return_col} > {order_col}")

    n = max(len(df), 1)
    return {
        "data_quality_issue_rows": len(issue_rows),
        "data_quality_issue_row_pct": round(len(issue_rows) / n * 100, 2),
        "confident_issue_rows": len(issue_rows - reviewed_rows),
        "confident_issue_row_pct": round(len(issue_rows - reviewed_rows) / n * 100, 2),
        "review_required": bool(rule_details and any(item["review_required"] for item in rule_details.values())),
        "issues_by_rule": issues_by_rule,
        "rule_details": rule_details,
        "rules_checked": sorted(rules_checked | set(issues_by_rule)),
        "rule_manifest": rule_manifest(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7 — CATEGORY DISTRIBUTIONS
# ─────────────────────────────────────────────────────────────────────────────

def _category_distributions(df, schema_blueprint):
    result = {}
    chart_candidates = []

    for col in _categorical_cols(df, schema_blueprint):
        counts = df[col].value_counts(dropna=False)
        pct    = (counts / len(df) * 100).round(2)
        dist   = pd.DataFrame({"count": counts, "pct": pct}).reset_index()
        dist.columns = [col, "count", "pct"]
        result[col] = dist.to_dict(orient="records")

        if len(counts) <= 15:
            # Use explicit Python str() to avoid pandas 3.x StringDtype / pd.NA
            # values reaching matplotlib's category converter as floats.
            x_labels = [str(v) for v in counts.index]
            fig, ax = plt.subplots(figsize=(max(6, len(counts)), 4))
            bars = ax.bar(
                x_labels, counts.values,
                color=COLORS["bars"][:len(counts)], alpha=0.88
            )
            for bar, p in zip(bars, pct.values):
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                        f"{p:.1f}%", ha="center", va="bottom", fontsize=9)
            ax.set_title(f"Distribution of {col}", fontsize=13, fontweight="bold")
            ax.set_ylabel("Count", fontsize=10)
            plt.xticks(rotation=30, ha="right")
            fig.tight_layout()
            dist_path = _save(fig, f"dist_{col.lower()}")
            # A distribution that's far from uniform (one category dominating
            # or a long tail) is more worth showing than a near-even split.
            uniform_pct = 100.0 / len(counts)
            imbalance = float(pct.max()) - uniform_pct
            chart_candidates.append({
                "path": dist_path, "family": "category_distribution",
                "score": round(max(15.0, min(100.0, imbalance)), 1),
                "reason": f"{col} top share={pct.max():.1f}% vs uniform={uniform_pct:.1f}%",
            })

    return result, chart_candidates


# ─────────────────────────────────────────────────────────────────────────────
# 8 — LINEAR REGRESSION (time-series trend)
# ─────────────────────────────────────────────────────────────────────────────

def _regression_trends(df, schema_blueprint):
    result = {}
    chart_candidates = []

    # Build a monotonic time index from year+month (if available) so that the
    # regression x-axis increases across years rather than cycling 1-12.
    year_col  = next((c for c in df.columns if c.endswith("_year")),  None)
    month_col = next((c for c in df.columns if c.endswith("_month")), None)

    if year_col and month_col:
        time_index = (
            pd.to_numeric(df[year_col],  errors="coerce") * 12
            + pd.to_numeric(df[month_col], errors="coerce")
        )
        time_label = f"{year_col[:-5]}_year_month_index"  # e.g. order_date_year_month_index
    elif month_col:
        time_index = pd.Series(range(len(df)), index=df.index, dtype="float64")
        time_label = "row_index"
    else:
        # Fall back to row position (original ingestion order)
        time_index = pd.Series(range(len(df)), index=df.index, dtype="float64")
        time_label = "row_index"

    if time_index is None or time_index.dropna().empty:
        return result, chart_candidates

    # Columns eligible for regression: exclude date-derived columns entirely
    # (they are trivially correlated with the time axis itself), and exclude
    # the time index columns to prevent self-regression (r²=1.0).
    _date_col_names = {year_col, month_col} if year_col else {month_col}
    _date_col_names = {c for c in _date_col_names if c}  # drop None

    eligible_cols = [
        col for col in _numeric_cols(df, schema_blueprint)
        if not _is_date_derived(col)
        and col not in _date_col_names
    ]

    for col in eligible_cols:
        if not pd.api.types.is_numeric_dtype(df[col]):
            continue
        pair = pd.DataFrame({"_x": time_index, "_y": pd.to_numeric(df[col], errors="coerce")}).dropna()
        if len(pair) < 3:
            continue
        x = pair["_x"].to_numpy(dtype="float64")
        y = pair["_y"].to_numpy(dtype="float64")
        mask = ~(np.isnan(x) | np.isnan(y))
        x, y = x[mask], y[mask]
        if len(x) < 3:
            continue
        try:
            slope, intercept, r_value, p_value, std_err = scipy_stats.linregress(x, y)
            slope     = float(np.atleast_1d(slope)[0])
            intercept = float(np.atleast_1d(intercept)[0])
            r_value   = float(np.atleast_1d(r_value)[0])
            p_value   = float(np.atleast_1d(p_value)[0])
            std_err   = float(np.atleast_1d(std_err)[0])
        except Exception:
            continue

        result[col] = {
            "slope":       round(slope, 6),
            "intercept":   round(intercept, 4),
            "r_squared":   round(r_value ** 2, 4),
            "p_value":     round(p_value, 4),
            "std_err":     round(std_err, 6),
            "trend":       "upward" if slope > 0 else "downward",
            "significant": p_value < 0.05,
            "x_axis":      time_label,
            "n":           int(len(x)),
        }

    # Revenue trend line chart — only draw it when the trend is statistically
    # significant. A regression line fit to noise (p >= 0.05) isn't a meaningful
    # insight and misleads readers into seeing a trend that isn't really there.
    rev_col = _find_revenue_col(df, schema_blueprint)
    if (
        rev_col
        and rev_col in result
        and result[rev_col]["significant"]
        and pd.api.types.is_numeric_dtype(df[rev_col])
    ):
        pair = pd.DataFrame({"_x": time_index, "_y": pd.to_numeric(df[rev_col], errors="coerce")}).dropna()
        pair = pair.sort_values("_x")
        x = pair["_x"].to_numpy(dtype="float64")
        y = pair["_y"].to_numpy(dtype="float64")
        if len(x) >= 3:
            slope     = result[rev_col]["slope"]
            intercept = result[rev_col]["intercept"]
            y_pred    = slope * x + intercept
            label = _revenue_label(rev_col)

            fig, ax = plt.subplots(figsize=(8, 4))
            ax.scatter(x, y, color=COLORS["primary"], s=60, zorder=5, label="Actual")
            ax.plot(x, y_pred, color=COLORS["accent"], linewidth=2,
                    linestyle="--", label=f"Trend (R²={result[rev_col]['r_squared']:.3f})")
            ax.set_xlabel(time_label, fontsize=10)
            ax.set_ylabel(label, fontsize=10)
            ax.set_title(f"{label} Linear Trend", fontsize=13, fontweight="bold")
            ax.legend(fontsize=9)
            ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
            fig.tight_layout()
            trend_path = _save(fig, f"{_slug(label)}_trend_regression")
            chart_candidates.append({
                "path": trend_path, "family": "regression_trend",
                "score": round(result[rev_col]["r_squared"] * 100, 1),
                "reason": f"R²={result[rev_col]['r_squared']:.3f}",
            })

    return result, chart_candidates


# ─────────────────────────────────────────────────────────────────────────────
# 9 — DISTRIBUTION CHARTS (box + histogram for key numeric cols)
# ─────────────────────────────────────────────────────────────────────────────

def _distribution_charts(df, schema_blueprint):
    chart_candidates = []
    num_cols = _numeric_cols(df, schema_blueprint)[:6]

    if not num_cols:
        return chart_candidates

    # Standardize each column (z-score) before combining them on one boxplot.
    # Numeric columns are rarely on the same scale (e.g. price in currency vs.
    # a percentage vs. a raw count) - plotting raw values together lets the
    # largest-magnitude column dominate the axis and flattens the rest into
    # invisible lines. Standardizing puts every column's spread/skew on a
    # comparable footing so the chart is actually readable.
    data = []
    for col in num_cols:
        s = df[col].dropna()
        std = s.std()
        data.append(((s - s.mean()) / std).values if std else (s - s.mean()).values)

    fig, ax = plt.subplots(figsize=(max(8, len(num_cols)*1.5), 5))
    bp = ax.boxplot(data, patch_artist=True, notch=False)
    for patch, color in zip(bp["boxes"], COLORS["bars"]):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
    ax.axhline(0, color="gray", linewidth=0.8, linestyle="--")
    ax.set_xticks(range(1, len(num_cols)+1))
    ax.set_xticklabels(num_cols, rotation=30, ha="right", fontsize=9)
    ax.set_ylabel("Standardized value (z-score)", fontsize=10)
    ax.set_title("Numeric Columns — Distribution Comparison (standardized)", fontsize=13, fontweight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    fig.tight_layout()
    boxplot_path = _save(fig, "boxplot_numeric_cols")
    chart_candidates.append({
        "path": boxplot_path, "family": "distribution_boxplot",
        "score": 55.0,
        "reason": f"overview across {len(num_cols)} numeric columns",
    })

    rev_col = _find_revenue_col(df, schema_blueprint)
    if rev_col and pd.api.types.is_numeric_dtype(df[rev_col]):
        s = df[rev_col].dropna()
        label = _revenue_label(rev_col)
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.hist(s, bins=min(20, len(s)), color=COLORS["primary"], alpha=0.8, edgecolor="white")
        ax.axvline(s.mean(),   color=COLORS["accent"],  linewidth=2, linestyle="--", label=f"Mean: {s.mean():,.0f}")
        ax.axvline(s.median(), color=COLORS["warning"], linewidth=2, linestyle="-",  label=f"Median: {s.median():,.0f}")
        ax.set_title(f"{label} Distribution", fontsize=13, fontweight="bold")
        ax.set_xlabel(label, fontsize=10)
        ax.set_ylabel("Frequency", fontsize=10)
        ax.legend(fontsize=9)
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        fig.tight_layout()
        hist_path = _save(fig, f"{_slug(label)}_histogram")
        # A skewed distribution (long tail of high/low values) is more worth
        # showing than a plain, roughly-symmetric bell curve.
        skew_score = min(100.0, abs(float(s.skew())) * 15 + 35)
        chart_candidates.append({
            "path": hist_path, "family": "revenue_histogram",
            "score": round(skew_score, 1),
            "reason": f"{label} skewness={s.skew():.2f}",
        })

    return chart_candidates


# ─────────────────────────────────────────────────────────────────────────────
# 10 — DERIVED METRICS CHARTS
# ─────────────────────────────────────────────────────────────────────────────

def _derived_metrics_charts(df):
    chart_candidates = []

    derived_cols = [c for c in df.columns if c.startswith("derived_")
                    and pd.api.types.is_numeric_dtype(df[c])]

    if not derived_cols:
        return chart_candidates

    margin_col = next((c for c in derived_cols if "margin" in c), None)
    month_col  = next((c for c in df.columns if c.endswith("_month")), None)

    if margin_col and month_col:
        monthly = df.groupby(month_col)[margin_col].mean().reset_index()
        if len(monthly) >= 2:
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.plot(monthly[month_col].astype(str), monthly[margin_col],
                    marker="o", color=COLORS["purple"], linewidth=2.5, markersize=7)
            ax.axhline(monthly[margin_col].mean(), color="gray",
                       linestyle="--", linewidth=1, label=f"Avg: {monthly[margin_col].mean():.1f}%")
            ax.set_title("Profit Margin % Over Time", fontsize=13, fontweight="bold")
            ax.set_xlabel("Month")
            ax.set_ylabel("Profit Margin %")
            ax.legend(fontsize=9)
            ax.grid(axis="y", linestyle="--", alpha=0.4)
            fig.tight_layout()
            margin_path = _save(fig, "profit_margin_trend")
            margin_mean = monthly[margin_col].mean()
            cv = float(monthly[margin_col].std() / abs(margin_mean)) if margin_mean else 0.0
            chart_candidates.append({
                "path": margin_path, "family": "derived_margin_trend",
                "score": round(min(100.0, cv * 200 + 30), 1),
                "reason": f"margin CV={cv:.2f}",
            })

    if len(derived_cols) >= 2:
        # Each derived metric can be on a wildly different unit (currency profit
        # vs. a percentage margin vs. a raw quantity), so a single shared y-axis
        # bar chart is misleading - one metric's scale swamps the others. Give
        # each metric its own small subplot instead; actual values stay visible
        # and comparable within their own scale.
        cols_to_plot = derived_cols[:6]
        fig, axes = plt.subplots(1, len(cols_to_plot),
                                  figsize=(max(7, len(cols_to_plot) * 2.2), 4))
        if len(cols_to_plot) == 1:
            axes = [axes]
        for ax, col, color in zip(axes, cols_to_plot, COLORS["bars"]):
            val = df[col].mean()
            label = col.replace("derived_", "").replace("_", " ").title()
            ax.bar([label], [val], color=color, alpha=0.88, width=0.5)
            ax.text(0, val, f"{val:,.1f}", ha="center", va="bottom", fontsize=9)
            ax.set_title(label, fontsize=10)
            ax.tick_params(axis="x", labelsize=8)
        fig.suptitle("Derived Business Metrics — Averages", fontsize=13, fontweight="bold")
        fig.tight_layout()
        summary_path = _save(fig, "derived_metrics_summary")
        chart_candidates.append({
            "path": summary_path, "family": "derived_metrics_summary",
            "score": 40.0,
            "reason": f"averages across {len(cols_to_plot)} derived metrics",
        })

    return chart_candidates


# ─────────────────────────────────────────────────────────────────────────────
# 11 — CROSS-DIMENSIONAL ANALYSIS (docs/known_issues.md #3)
# ─────────────────────────────────────────────────────────────────────────────
# Generic name-based column finders (not hardcoded exact column names) so
# these analyses work on any dataset shaped like this one, not just the
# specific fixture that motivated them. Word-boundary matching alone
# (`_find_col`'s `\b{kw}\b` regex) doesn't work for underscore-joined column
# names like "Discount_Percentage" - regex `\b` treats "_" as a word
# character, so there's no boundary between "discount" and "_". These finders
# tokenize on any non-alphanumeric separator instead.

def _tokenize_col_name(col):
    return re.findall(r"[a-z0-9]+", col.lower())


def _find_numeric_col_by_phrases(df, schema_blueprint, phrases):
    """First phrase (list of tokens) with a numeric column containing all its
    tokens wins; phrases are tried in priority order."""
    numeric_cols = _numeric_cols(df, schema_blueprint)
    for phrase in phrases:
        phrase_tokens = phrase.split()
        for col in numeric_cols:
            tokens = _tokenize_col_name(col)
            if all(t in tokens for t in phrase_tokens):
                return col
    return None


def _find_categorical_col_by_phrases(df, schema_blueprint, phrases):
    """Exact (case-insensitive) column name match first - disambiguates e.g.
    "Region" from "Customer_Region" - then a whole-token phrase match."""
    cat_cols = _categorical_cols(df, schema_blueprint)
    exact = {c.lower(): c for c in cat_cols}
    for phrase in phrases:
        if phrase.lower() in exact:
            return exact[phrase.lower()]
    for phrase in phrases:
        phrase_tokens = phrase.split()
        for col in cat_cols:
            tokens = _tokenize_col_name(col)
            if all(t in tokens for t in phrase_tokens):
                return col
    return None


def _find_boolean_col_by_phrases(df, phrases):
    for phrase in phrases:
        phrase_tokens = phrase.split()
        for col in df.columns:
            if not pd.api.types.is_bool_dtype(df[col]):
                continue
            tokens = _tokenize_col_name(col)
            if all(t in tokens for t in phrase_tokens):
                return col
    return None


def _discount_vs_return_rate(df, schema_blueprint, quartiles=4):
    """Return rate by discount-percentage quartile bucket."""
    result = {}
    chart_candidates = []

    discount_col = _find_numeric_col_by_phrases(
        df, schema_blueprint, ["discount percentage", "discount pct", "discount rate", "discount"]
    )
    returned_col = _find_boolean_col_by_phrases(df, ["returned", "is returned", "return flag"])
    if not discount_col or not returned_col:
        return result, chart_candidates

    working = df[[discount_col, returned_col]].dropna()
    if working.empty or working[discount_col].nunique() < 2:
        return result, chart_candidates

    try:
        buckets = pd.qcut(working[discount_col], q=quartiles, duplicates="drop")
    except ValueError:
        return result, chart_candidates

    grouped = working[returned_col].groupby(buckets, observed=True).agg(["mean", "count"])
    if grouped.empty:
        return result, chart_candidates

    records = []
    for interval, row in grouped.iterrows():
        records.append({
            "discount_range": f"{interval.left:.3g}-{interval.right:.3g}",
            "return_rate_pct": round(float(row["mean"]) * 100, 2),
            "records": int(row["count"]),
        })

    result = {
        "discount_column": discount_col,
        "returned_column": returned_col,
        "buckets": records,
    }

    labels = [r["discount_range"] for r in records]
    values = [r["return_rate_pct"] for r in records]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(labels, values, color=COLORS["bars"][:len(records)], alpha=0.88)
    ax.set_xlabel(f"{discount_col} (quartile bucket)", fontsize=10)
    ax.set_ylabel("Return Rate (%)", fontsize=10)
    ax.set_title("Return Rate by Discount Quartile", fontsize=13, fontweight="bold")
    ax.tick_params(axis="x", labelsize=9)
    fig.tight_layout()
    chart_path = _save(fig, "return_rate_by_discount_quartile")
    spread = float(max(values) - min(values)) if values else 0.0
    chart_candidates.append({
        "path": chart_path, "family": "discount_return_rate",
        "score": round(min(100.0, spread * 4), 1),
        "reason": f"return rate spread across discount quartiles={spread:.1f}pp",
    })

    return result, chart_candidates


def _margin_by_category_over_time(df, schema_blueprint, max_categories=8):
    """Average profit margin % per Product_Category-style column, by month."""
    result = {}
    chart_candidates = []

    margin_col = _find_numeric_col_by_phrases(df, schema_blueprint, ["profit margin", "margin pct", "margin"])
    category_col = _find_categorical_col_by_phrases(df, schema_blueprint, ["product category", "category"])
    month_col = next((c for c in df.columns if c.endswith("_month")), None)
    if not margin_col or not category_col or not month_col:
        return result, chart_candidates

    working = df[[category_col, month_col, margin_col]].dropna()
    if working.empty:
        return result, chart_candidates

    grouped = working.groupby([category_col, month_col])[margin_col].mean().reset_index()
    if grouped.empty:
        return result, chart_candidates

    categories = list(grouped[category_col].unique())
    for cat in categories:
        rows = (
            grouped[grouped[category_col] == cat][[month_col, margin_col]]
            .rename(columns={month_col: "month", margin_col: "avg_margin_pct"})
            .round(2)
        )
        result[str(cat)] = rows.to_dict(orient="records")

    plotted_categories = categories[:max_categories]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for color, cat in zip(COLORS["bars"], plotted_categories):
        rows = result[str(cat)]
        ax.plot([r["month"] for r in rows], [r["avg_margin_pct"] for r in rows],
                marker="o", label=str(cat), color=color, linewidth=2)
    ax.set_xlabel("Month")
    ax.set_ylabel("Avg Profit Margin %")
    ax.set_title(f"Profit Margin by {category_col} Over Time", fontsize=13, fontweight="bold")
    ax.legend(fontsize=8, ncol=2)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    fig.tight_layout()
    chart_path = _save(fig, f"margin_by_{_slug(category_col)}_over_time")
    chart_candidates.append({
        "path": chart_path, "family": "category_margin_trend",
        "score": 55.0,
        "reason": f"margin trend across {len(plotted_categories)} {category_col} groups",
    })

    return result, chart_candidates


def _discount_and_margin_by_rep(df, schema_blueprint, max_charted=15):
    """Average discount % and profit margin % per Sales_Representative-style column."""
    result = {}
    chart_candidates = []

    rep_col = _find_categorical_col_by_phrases(df, schema_blueprint, ["sales representative", "representative"])
    discount_col = _find_numeric_col_by_phrases(df, schema_blueprint, ["discount percentage", "discount"])
    margin_col = _find_numeric_col_by_phrases(df, schema_blueprint, ["profit margin", "margin"])
    if not rep_col or not discount_col or not margin_col:
        return result, chart_candidates

    nunique = df[rep_col].nunique(dropna=True)
    if nunique < 2 or nunique > 30:
        return result, chart_candidates

    grouped = (
        df.groupby(rep_col)[[discount_col, margin_col]]
        .mean()
        .rename(columns={discount_col: "avg_discount_pct", margin_col: "avg_margin_pct"})
        .reset_index()
        .round(2)
        .sort_values("avg_margin_pct", ascending=False)
    )
    result = {"rep_column": rep_col, "records": grouped.to_dict(orient="records")}

    top = grouped.head(max_charted)
    fig, ax = plt.subplots(figsize=(9, max(3, len(top) * 0.35 + 1)))
    ax.barh(top[rep_col].astype(str), top["avg_margin_pct"], color=COLORS["primary"], alpha=0.85)
    ax.set_xlabel("Avg Profit Margin %")
    ax.set_title(f"Avg Margin by {rep_col}", fontsize=13, fontweight="bold")
    ax.invert_yaxis()
    fig.tight_layout()
    chart_path = _save(fig, f"margin_by_{_slug(rep_col)}")
    spread = float(top["avg_margin_pct"].max() - top["avg_margin_pct"].min()) if not top.empty else 0.0
    chart_candidates.append({
        "path": chart_path, "family": "rep_discount_margin",
        "score": round(min(100.0, spread * 3), 1),
        "reason": f"avg margin spread across {rep_col}={spread:.1f}pp",
    })

    return result, chart_candidates


def _avg_order_value_by_segment(df, schema_blueprint):
    """Average order value (revenue per row) per Customer_Segment-style column."""
    result = {}
    chart_candidates = []

    segment_col = _find_categorical_col_by_phrases(df, schema_blueprint, ["customer segment", "segment"])
    rev_col = _find_revenue_col(df, schema_blueprint)
    if not segment_col or not rev_col:
        return result, chart_candidates

    nunique = df[segment_col].nunique(dropna=True)
    if nunique < 2 or nunique > 20:
        return result, chart_candidates

    grouped = (
        df.groupby(segment_col)[rev_col]
        .mean()
        .reset_index()
        .rename(columns={rev_col: "avg_order_value"})
        .round(2)
        .sort_values("avg_order_value", ascending=False)
    )
    result = {"segment_column": segment_col, "revenue_column": rev_col, "records": grouped.to_dict(orient="records")}

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(grouped[segment_col].astype(str), grouped["avg_order_value"], color=COLORS["bars"][:len(grouped)], alpha=0.88)
    ax.set_ylabel(f"Avg {_revenue_label(rev_col)}")
    ax.set_title(f"Avg Order Value by {segment_col}", fontsize=13, fontweight="bold")
    fig.tight_layout()
    chart_path = _save(fig, f"avg_order_value_by_{_slug(segment_col)}")
    mean_value = float(grouped["avg_order_value"].mean()) if not grouped.empty else 0.0
    spread = float(grouped["avg_order_value"].max() - grouped["avg_order_value"].min()) if not grouped.empty else 0.0
    chart_candidates.append({
        "path": chart_path, "family": "segment_order_value",
        "score": round(min(100.0, (spread / mean_value * 40) if mean_value else 0.0), 1),
        "reason": f"avg order value spread across {segment_col}",
    })

    return result, chart_candidates


def _shipping_cost_by_region(df, schema_blueprint):
    """Average shipping cost per Region-style column."""
    result = {}
    chart_candidates = []

    shipping_col = _find_numeric_col_by_phrases(df, schema_blueprint, ["shipping cost", "shipping"])
    region_col = _find_categorical_col_by_phrases(df, schema_blueprint, ["region"])
    if not shipping_col or not region_col:
        return result, chart_candidates

    nunique = df[region_col].nunique(dropna=True)
    if nunique < 2 or nunique > 20:
        return result, chart_candidates

    grouped = (
        df.groupby(region_col)[shipping_col]
        .mean()
        .reset_index()
        .rename(columns={shipping_col: "avg_shipping_cost"})
        .round(2)
        .sort_values("avg_shipping_cost", ascending=False)
    )
    result = {"region_column": region_col, "shipping_column": shipping_col, "records": grouped.to_dict(orient="records")}

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(grouped[region_col].astype(str), grouped["avg_shipping_cost"], color=COLORS["bars"][:len(grouped)], alpha=0.88)
    ax.set_ylabel("Avg Shipping Cost")
    ax.set_title(f"Avg Shipping Cost by {region_col}", fontsize=13, fontweight="bold")
    fig.tight_layout()
    chart_path = _save(fig, f"avg_shipping_cost_by_{_slug(region_col)}")
    mean_value = float(grouped["avg_shipping_cost"].mean()) if not grouped.empty else 0.0
    spread = float(grouped["avg_shipping_cost"].max() - grouped["avg_shipping_cost"].min()) if not grouped.empty else 0.0
    chart_candidates.append({
        "path": chart_path, "family": "region_shipping_cost",
        "score": round(min(100.0, (spread / mean_value * 40) if mean_value else 0.0), 1),
        "reason": f"avg shipping cost spread across {region_col}",
    })

    return result, chart_candidates


def _shipping_lead_time_analysis(df, schema_blueprint):
    lead_time_col = "derived_days_to_ship"
    if lead_time_col not in df.columns:
        return {}, []

    lead_time = pd.to_numeric(df[lead_time_col], errors="coerce")
    valid = lead_time.dropna()
    if valid.empty:
        return {}, []

    result = {
        "column": lead_time_col,
        "distribution": {
            "count": int(valid.size),
            "mean_days": round(float(valid.mean()), 2),
            "median_days": round(float(valid.median()), 2),
            "min_days": round(float(valid.min()), 2),
            "max_days": round(float(valid.max()), 2),
        },
        "by_dimension": {},
    }
    chart_candidates = []

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(valid, bins=min(20, max(5, valid.nunique())), color=COLORS["primary"], alpha=0.88)
    ax.set_xlabel("Days to Ship")
    ax.set_ylabel("Orders")
    ax.set_title("Shipping Lead-Time Distribution", fontsize=13, fontweight="bold")
    fig.tight_layout()
    chart_path = _save(fig, "shipping_lead_time_distribution")
    chart_candidates.append({
        "path": chart_path,
        "family": "shipping_lead_time",
        "score": round(min(100.0, max(15.0, float(valid.std()) * 10)), 1),
        "reason": "shipping lead-time distribution",
    })

    for dimension in _categorical_cols(df, schema_blueprint):
        if dimension not in df.columns or not 2 <= df[dimension].nunique(dropna=True) <= 20:
            continue
        grouped = (
            pd.DataFrame({dimension: df[dimension], lead_time_col: lead_time})
            .dropna()
            .groupby(dimension)[lead_time_col]
            .agg(["mean", "median", "count"])
            .reset_index()
            .rename(columns={"mean": "mean_days", "median": "median_days", "count": "orders"})
            .sort_values("mean_days", ascending=False)
        )
        result["by_dimension"][dimension] = {
            "top": grouped.head(5).to_dict(orient="records"),
            "bottom": grouped.tail(5).to_dict(orient="records"),
        }

    return result, chart_candidates


# ─────────────────────────────────────────────────────────────────────────────
# MAIN AGENT FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

# Anomaly rates below this are treated as expected noise in any real dataset
# and don't further penalize the quality score computed by Agent 3.
ANOMALY_QUALITY_TOLERANCE_PCT = 3.0
# Statistical outliers may be entirely legitimate long-tail values, so they move
# the Data Quality Score only slightly (small scale, low cap). The score is
# driven primarily by *structural* data-quality issues instead (Bug 4, Task C).
ANOMALY_QUALITY_PENALTY_SCALE = 0.1
ANOMALY_QUALITY_PENALTY_CAP = 5.0
# Structural violations (negative quantities, discount > 100%, impossible
# returns, reconciliation mismatches) are real defects and dominate the penalty.
DQ_ISSUE_PENALTY_SCALE = 1.5
DQ_ISSUE_PENALTY_CAP = 40.0



def _apply_anomaly_quality_penalty(data_quality, anomaly_summary, dq_issue_summary=None):
    """Fold Agent 4's findings into Agent 3's quality score.

    Agent 3 computes `overall_quality_score` before anomaly detection has even
    run (it runs in Agent 4). The adjustment here separates two very different
    signals (docs/known_issues.md #6, Bug 4):

    * statistical outliers  - possibly-legitimate extreme values; penalized
      only lightly so a long-tailed-but-clean dataset isn't punished.
    * structural data-quality issues - actual constraint violations; these
      drive the bulk of the penalty.

    The pre-adjustment score is kept around for auditability.
    """
    if not isinstance(data_quality, dict) or "overall_quality_score" not in data_quality:
        return data_quality

    data_quality = dict(data_quality)
    pre_anomaly_score = float(data_quality["overall_quality_score"])
    stat_pct = float(anomaly_summary.get("unique_flagged_row_pct", 0.0) or 0.0)
    dq_issue_summary = dq_issue_summary or {}
    struct_pct = float(dq_issue_summary.get("confident_issue_row_pct", dq_issue_summary.get("data_quality_issue_row_pct", 0.0)) or 0.0)

    statistical_penalty = min(
        ANOMALY_QUALITY_PENALTY_CAP,
        max(0.0, stat_pct - ANOMALY_QUALITY_TOLERANCE_PCT) * ANOMALY_QUALITY_PENALTY_SCALE,
    )
    structural_penalty = min(
        DQ_ISSUE_PENALTY_CAP,
        struct_pct * DQ_ISSUE_PENALTY_SCALE,
    )
    total_penalty = round(statistical_penalty + structural_penalty, 2)
    adjusted_score = max(0.0, round(pre_anomaly_score - total_penalty, 2))

    data_quality["overall_quality_score_pre_anomaly"] = round(pre_anomaly_score, 2)
    data_quality["statistical_outlier_row_pct"] = stat_pct
    data_quality["data_quality_issue_row_pct"] = struct_pct
    data_quality["statistical_outlier_penalty"] = round(statistical_penalty, 2)
    data_quality["data_quality_issue_penalty"] = round(structural_penalty, 2)
    data_quality["data_quality_issues_by_rule"] = dq_issue_summary.get("issues_by_rule", {})
    # `anomaly_*` keys retain their historical meaning (statistical-outlier
    # component only) for backward compatibility with existing report facts.
    data_quality["anomaly_flagged_row_pct"] = stat_pct
    data_quality["anomaly_quality_penalty"] = round(statistical_penalty, 2)
    data_quality["total_quality_penalty"] = total_penalty
    data_quality["overall_quality_score"] = adjusted_score
    return data_quality


def agent4_analysis(state: GraphState) -> GraphState:
    errors = state.get("errors", [])
    schema_blueprint = state.get("schema_blueprint", {})
    df = state.get("cleaned_df")

    if df is None:
        errors.append("Agent4: No cleaned_df in state. Agent 3 failed.")
        return {**state, "errors": errors}

    _clear_chart_dir()

    print(f"[Agent 4] Starting analysis: {df.shape[0]} rows × {df.shape[1]} cols")

    chart_plan = _build_chart_plan(df, schema_blueprint)
    print(
        f"[Agent 4] Dataset type: {chart_plan['dataset_type']} | "
        f"numeric={len(chart_plan['numeric_columns'])} | "
        f"categorical={len(chart_plan['categorical_columns'])} | "
        f"time_axis={chart_plan['has_time_axis']}"
    )

    all_chart_candidates = []
    stats = {}
    stats["chart_plan"] = chart_plan

    stats["descriptive"] = _descriptive_stats(df, schema_blueprint)
    print(f"[Agent 4] Step 1 — Descriptive stats: {len(stats['descriptive'])} columns")

    if chart_plan["chart_families"]["correlation"]:
        stats["correlation"], candidates = _correlation(df, schema_blueprint)
        all_chart_candidates.extend(candidates)
        print(f"[Agent 4] Step 2 — Correlation done, strong pairs: {len(stats['correlation'].get('strong_pairs', []))}")
    else:
        stats["correlation"] = {}
        print("[Agent 4] Step 2 — Correlation skipped (fewer than 2 numeric columns)")

    if chart_plan["chart_families"]["growth_rates"]:
        stats["growth_rates"], candidates = _growth_rates(df, schema_blueprint)
        all_chart_candidates.extend(candidates)
        if stats["growth_rates"] or candidates:
            print(f"[Agent 4] Step 3 — Growth rates done ({len(candidates)} charts)")
        else:
            print("[Agent 4] Step 3 — Growth rates skipped (no usable revenue/time axis after filtering)")
    else:
        stats["growth_rates"] = {}
        print("[Agent 4] Step 3 — Growth rates skipped (no revenue/time axis)")

    if chart_plan["chart_families"]["top_bottom"]:
        stats["top_bottom"], candidates = _top_bottom_rankings(df, schema_blueprint)
        all_chart_candidates.extend(candidates)
        if stats["top_bottom"] or candidates:
            print(f"[Agent 4] Step 4 — Rankings done ({len(candidates)} charts)")
        else:
            print("[Agent 4] Step 4 — Rankings skipped (no usable categorical ranking columns)")
    else:
        stats["top_bottom"] = {}
        print("[Agent 4] Step 4 — Rankings skipped (no revenue/category pairing)")

    if chart_plan["chart_families"]["seasonality"]:
        stats["seasonality"], candidates = _seasonality(df, schema_blueprint)
        all_chart_candidates.extend(candidates)
        if stats["seasonality"] or candidates:
            print(f"[Agent 4] Step 5 — Seasonality done ({len(candidates)} charts)")
        else:
            print("[Agent 4] Step 5 — Seasonality skipped (no usable time axis after filtering)")
    else:
        stats["seasonality"] = {}
        print("[Agent 4] Step 5 — Seasonality skipped (no time axis)")

    if chart_plan["chart_families"]["anomalies"]:
        stats["anomalies"], anomaly_summary = _detect_anomalies(df, schema_blueprint)
        stats["anomaly_summary"] = anomaly_summary
        print(
            f"[Agent 4] Step 6 — Anomalies: {anomaly_summary['unique_flagged_rows']} unique rows "
            f"({anomaly_summary['unique_flagged_row_pct']}%) across {anomaly_summary['flagged_columns']} columns"
        )
    else:
        stats["anomalies"] = {}
        stats["anomaly_summary"] = {
            "z_threshold": ANOMALY_Z_THRESHOLD,
            "iqr_multiplier": ANOMALY_IQR_MULTIPLIER,
            "flagged_columns": 0,
            "total_flagged_values": 0,
            "unique_flagged_rows": 0,
            "unique_flagged_row_pct": 0.0,
            "prioritized_anomalies": [],
            "business_impact_total": 0.0,
            "rule_manifest": rule_manifest(),
        }
        print("[Agent 4] Step 6 — Anomalies skipped (no numeric columns)")

    # Structural data-quality issues are computed independently of the
    # statistical anomaly pass so the two can penalize the score differently.
    stats["data_quality_issues"] = _detect_data_quality_issues(df, schema_blueprint)
    print(
        f"[Agent 4] Step 6b — Structural data-quality issues: "
        f"{stats['data_quality_issues']['data_quality_issue_rows']} rows "
        f"({stats['data_quality_issues']['data_quality_issue_row_pct']}%) across "
        f"{len(stats['data_quality_issues']['rules_checked'])} rule(s)"
    )

    if chart_plan["chart_families"]["distributions"]:
        stats["distributions"], candidates = _category_distributions(df, schema_blueprint)
        all_chart_candidates.extend(candidates)
        print(f"[Agent 4] Step 7 — Distributions done ({len(candidates)} charts)")
    else:
        stats["distributions"] = {}
        print("[Agent 4] Step 7 — Distributions skipped (no categorical columns)")

    if chart_plan["chart_families"]["regression"]:
        stats["regression"], candidates = _regression_trends(df, schema_blueprint)
        all_chart_candidates.extend(candidates)
        if stats["regression"] or candidates:
            print(f"[Agent 4] Step 8 — Regression done ({len(stats['regression'])} columns, {len(candidates)} charts)")
        else:
            print("[Agent 4] Step 8 — Regression skipped (no usable time axis after filtering)")
    else:
        stats["regression"] = {}
        print("[Agent 4] Step 8 — Regression skipped (no time axis)")

    if chart_plan["chart_families"]["distribution_charts"]:
        candidates = _distribution_charts(df, schema_blueprint)
        all_chart_candidates.extend(candidates)
        print(f"[Agent 4] Step 9 — Distribution charts done ({len(candidates)} charts)")
    else:
        candidates = []
        print("[Agent 4] Step 9 — Distribution charts skipped (no numeric columns)")

    if chart_plan["chart_families"]["derived_metrics"]:
        candidates = _derived_metrics_charts(df)
        all_chart_candidates.extend(candidates)
        if candidates:
            print(f"[Agent 4] Step 10 — Derived metrics charts done ({len(candidates)} charts)")
        else:
            print("[Agent 4] Step 10 — Derived metrics skipped (derived columns present but no useful chart pairing)")
    else:
        candidates = []
        print("[Agent 4] Step 10 — Derived metrics skipped (no derived metrics)")

    if chart_plan["chart_families"]["profit_breakdown"]:
        stats["profit_breakdown"], candidates = _profit_breakdown_by_dimension(df, schema_blueprint)
        all_chart_candidates.extend(candidates)
        print(f"[Agent 4] Step 11 — Profit breakdown done ({len(candidates)} charts)")
    else:
        stats["profit_breakdown"] = {}
        print("[Agent 4] Step 11 — Profit breakdown skipped (no profit column or categorical dims)")

    if chart_plan["chart_families"]["discount_return_rate"]:
        stats["discount_return_rate"], candidates = _discount_vs_return_rate(df, schema_blueprint)
        all_chart_candidates.extend(candidates)
        print(f"[Agent 4] Step 12 — Discount vs return rate done ({len(candidates)} charts)")
    else:
        stats["discount_return_rate"] = {}
        print("[Agent 4] Step 12 — Discount vs return rate skipped (no discount/returned columns)")

    if chart_plan["chart_families"]["category_margin_trend"]:
        stats["category_margin_trend"], candidates = _margin_by_category_over_time(df, schema_blueprint)
        all_chart_candidates.extend(candidates)
        print(f"[Agent 4] Step 13 — Margin by category over time done ({len(candidates)} charts)")
    else:
        stats["category_margin_trend"] = {}
        print("[Agent 4] Step 13 — Margin by category over time skipped (missing margin/category/month columns)")

    if chart_plan["chart_families"]["rep_discount_margin"]:
        stats["rep_discount_margin"], candidates = _discount_and_margin_by_rep(df, schema_blueprint)
        all_chart_candidates.extend(candidates)
        print(f"[Agent 4] Step 14 — Discount/margin by rep done ({len(candidates)} charts)")
    else:
        stats["rep_discount_margin"] = {}
        print("[Agent 4] Step 14 — Discount/margin by rep skipped (missing rep/discount/margin columns)")

    if chart_plan["chart_families"]["segment_order_value"]:
        stats["segment_order_value"], candidates = _avg_order_value_by_segment(df, schema_blueprint)
        all_chart_candidates.extend(candidates)
        print(f"[Agent 4] Step 15 — Avg order value by segment done ({len(candidates)} charts)")
    else:
        stats["segment_order_value"] = {}
        print("[Agent 4] Step 15 — Avg order value by segment skipped (missing segment/revenue columns)")

    if chart_plan["chart_families"]["region_shipping_cost"]:
        stats["region_shipping_cost"], candidates = _shipping_cost_by_region(df, schema_blueprint)
        all_chart_candidates.extend(candidates)
        print(f"[Agent 4] Step 16 — Shipping cost by region done ({len(candidates)} charts)")
    else:
        stats["region_shipping_cost"] = {}
        print("[Agent 4] Step 16 — Shipping cost by region skipped (missing shipping/region columns)")

    if chart_plan["chart_families"]["shipping_lead_time"]:
        stats["shipping_lead_time"], candidates = _shipping_lead_time_analysis(df, schema_blueprint)
        all_chart_candidates.extend(candidates)
        print(f"[Agent 4] Step 17 — Shipping lead-time analysis done ({len(candidates)} charts)")
    else:
        stats["shipping_lead_time"] = {}
        print("[Agent 4] Step 17 — Shipping lead-time analysis skipped (missing derived lead-time metric)")

    data_quality = _apply_anomaly_quality_penalty(
        state.get("data_quality"),
        stats.get("anomaly_summary", {}),
        stats.get("data_quality_issues", {}),
    )
    if data_quality is not None:
        print(
            f"[Agent 4] Step 17 — Quality score adjusted: "
            f"{data_quality.get('overall_quality_score_pre_anomaly')} -> {data_quality.get('overall_quality_score')} "
            f"(structural={data_quality.get('data_quality_issue_penalty')}, "
            f"statistical={data_quality.get('anomaly_quality_penalty')})"
        )
    # Rank all chart candidates across every family by informativeness score
    # and keep only the top MAX_CHARTS_PER_REPORT. Without this cap, a wide
    # dataset with many numeric/categorical columns produces dozens of charts
    # of wildly uneven value (e.g. a near-uniform category bar chart next to a
    # strong correlation heatmap), which buries the genuinely useful ones and
    # makes every report look the same regardless of what the data says.
    ranked = sorted(all_chart_candidates, key=lambda c: c["score"], reverse=True)
    kept_paths = {c["path"] for c in ranked[:MAX_CHARTS_PER_REPORT]}
    dropped = [c for c in all_chart_candidates if c["path"] not in kept_paths]
    for c in dropped:
        try:
            os.remove(c["path"])
        except OSError:
            pass
    # Preserve original generation order among the kept charts so the report
    # gallery still reads top-to-bottom the way the pipeline produced it,
    # rather than jumping around in score order.
    all_chart_paths = [c["path"] for c in all_chart_candidates if c["path"] in kept_paths]

    stats["chart_selection"] = {
        "candidates": all_chart_candidates,
        "kept_count": len(all_chart_paths),
        "dropped_count": len(dropped),
        "max_charts_per_report": MAX_CHARTS_PER_REPORT,
    }
    print(
        f"[Agent 4] Step 12 — Chart selection: {len(all_chart_candidates)} candidates -> "
        f"kept {len(all_chart_paths)} (dropped {len(dropped)} low-informativeness charts)"
    )

    print(f"[Agent 4] Done — {len(all_chart_paths)} charts saved to {CHARTS_DIR}/")

    state_with_reliability = update_reliability(
        state,
        "agent4",
        0.9 if stats else 0.4,
        evidence=[f"stat_sections={len(stats)}", f"charts={len(all_chart_paths)}"],
        decision_readiness="ready" if stats else "blocked",
    )

    return {
        **state_with_reliability,
        "stats":        stats,
        "chart_paths":  all_chart_paths,
        "data_quality": data_quality if data_quality is not None else state.get("data_quality"),
        "errors":       errors,
    }