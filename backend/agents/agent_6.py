"""Agent 6: Insight Report Generator.

Final pipeline node. Synthesizes the outputs of Agents 1-5 (data quality,
statistics, charts, validation) into a single grounded document:

  1. Deterministic fact extraction (no LLM) - pulls concrete numbers out of
     `stats`, `data_quality`, `validation_report`, and `reliability` so the
     narrative step below has nothing to hallucinate from thin air.
  2. LLM narrative generation (Groq, falling back to Gemini, same provider
     chain as Agent 2) - asked to write an executive summary, key findings,
     risks/caveats, and recommendations using ONLY the extracted facts.
  3. A deterministic bullet-list fallback narrative if both LLM providers
     fail, so this agent never hard-fails the pipeline.
  4. Jinja2 HTML rendering + WeasyPrint PDF conversion. If PDF conversion
     itself fails (e.g. missing system libs), the HTML file is kept as the
     report so a document is still produced.
"""

import json
import base64
from io import BytesIO
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from agents.agent_1 import GraphState
from agents.agent_2 import (
    GROQ_MODEL,
    GROQ_REASONING_EFFORT,
    _call_gemini_json_with_failover,
    _get_groq_client,
    _parse_schema_blueprint_response,
)
from agents.chart_render_static import render_spec_png
from agents.chart_spec import SECTION_BY_FAMILY
from agents.echarts_options import option_json as echarts_option_json
from agents.report_style import (
    humanize_currency,
    humanize_number,
    humanize_pct,
    humanize_ratio,
    titleize,
)
from main import update_reliability

REPORTS_DIR = "outputs/reports"
TEMPLATE_DIR = str(Path(__file__).resolve().parent.parent / "templates")
TEMPLATE_NAME = "insight_report.html.jinja"
ECHARTS_LIB_PATH = Path(TEMPLATE_DIR) / "assets" / "echarts.min.js"

TOP_CORRELATIONS_LIMIT = 5
TOP_RANKING_LIMIT = 3
TOP_REGRESSION_LIMIT = 5
MIN_TREND_SAMPLE_SIZE = 10       # matches agents.agent_5; trends below this aren't cited as fact
CLAIM_GROUNDING_TOLERANCE = 1.0  # absolute tolerance (also scaled by 5% of the known value)
# Gemini 3.x models spend part of this budget on internal "thinking" tokens before
# emitting the JSON body; 1200 was too tight and routinely truncated the response
# mid-JSON (silent fallback to the deterministic narrative). Bumped with headroom
# for the ~20-25 bullet points the narrative prompt asks for plus thinking overhead.
AGENT6_MAX_OUTPUT_TOKENS = 3000  # enough room for the compact narrative contract
MAX_CHART_CAPTIONS_FROM_LLM = 4
# Keep the facts payload well below Groq's 8,000 TPM request ceiling after the
# system prompt and reserved completion tokens are included.
MAX_NARRATIVE_PROMPT_CHARS = 7000


# Terms a non-technical reader shouldn't have to decode unaided. Used two ways:
# the prompt forbids them in plain-language sections, and the linter below
# double-checks the LLM's actual output (prompts alone don't enforce anything).
_JARGON_PATTERNS = [
    r"r-?squared", r"r\u00b2", r"p-value", r"z-score", r"standard deviation",
    r"correlation coefficient", r"regression", r"\biqr\b", r"pearson",
    r"quartile", r"kappa", r"variance", r"\boutlier", r"coefficient",
]

# Always-available tooltips so even a fallback-only report explains its terms.
DEFAULT_GLOSSARY = {
    "average": "The value you get by adding every record up and dividing by how many there are.",
    "median": "The middle value when all records are lined up in order — half sit above it, half below.",
    "skewed": "Lopsided: most records bunch at one end with a long tail stretching the other way.",
    "unusual records": "Entries far outside the typical range — sometimes mistakes, sometimes genuinely rare events.",
    "link strength": "How dependably two things move together; closer to 100% means a tighter relationship.",
    "quality score": "A 0–100 health check on the data itself — missing values, duplicates and rule violations lower it.",
}

# Definitions for every term the jargon linter (`_JARGON_PATTERNS`) can catch, so a
# glossary entry exists whenever one of these slips through into the final text.
EXTENDED_GLOSSARY = {
    "r-squared": "A 0-1 score showing how much of the change in one number is explained by another — closer to 1 means a tighter fit.",
    "p-value": "A statistical check for whether a pattern is likely real or just chance — the smaller it is, the more confident we are it's real.",
    "z-score": "How many typical steps away from average a value is — a large one flags an unusually high or low record.",
    "standard deviation": "A measure of how spread out the numbers are around the average — bigger means more variation record-to-record.",
    "correlation coefficient": "A number from -1 to 1 showing how closely two things move together; near 0 means little relationship.",
    "regression": "A statistical technique for describing how one number tends to change as another one does.",
    "iqr": "The range covering the middle 50% of records, used to judge what counts as typical versus unusual.",
    "pearson": "The standard method used here to measure how closely two numeric columns move together.",
    "quartile": "One of four equal groups the data falls into when sorted from lowest to highest.",
    "kappa": "A score showing how much two independent checks agree, beyond what chance alone would produce.",
    "variance": "A measure of how much the numbers differ from the average — the basis for standard deviation.",
    "outlier": "A record whose value sits far outside the typical range for that column.",
    "coefficient": "A number in a formula that measures how strongly one thing influences another.",
}


def _verbose_logging_enabled():
    val = os.getenv("PIPELINE_VERBOSE", "0").strip().lower()
    return val in {"1", "true", "yes", "on"}


# ─────────────────────────────────────────────────────────────────────────────
# 1 — DETERMINISTIC FACT EXTRACTION (no LLM)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_dataset_facts(state):
    # `raw_shape` is captured once by Agent 1, immediately on ingestion, before any
    # transform touches the dataframe (see agent_1.agent1_structural_profiler) and
    # passed through the state unchanged - it is the single source of truth for
    # "raw" row/column counts. Fall back to raw_profile.shape (same numbers) only
    # for states produced before raw_shape existed, e.g. older tests/fixtures.
    raw_shape = state.get("raw_shape") or {}
    if not raw_shape:
        raw_shape = (state.get("raw_profile", {}) or {}).get("shape", {}) or {}
    cleaned_df = state.get("cleaned_df")
    return {
        "csv_path": state.get("csv_path", ""),
        "raw_rows": raw_shape.get("rows"),
        "raw_cols": raw_shape.get("cols"),
        "cleaned_rows": int(cleaned_df.shape[0]) if cleaned_df is not None else None,
        "cleaned_cols": int(cleaned_df.shape[1]) if cleaned_df is not None else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1c — SHAPE-CHANGE TRANSPARENCY (why row/column counts differ from the raw file)
# ─────────────────────────────────────────────────────────────────────────────
# Every category below is driven by columns/log entries the pipeline actually
# produced (schema_blueprint per-column notes, column suffixes, row_accounting
# ledger) - never a per-dataset hardcoded explanation - so it generalizes to
# any CSV regardless of what transforms actually ran on it.
_DATE_FEATURE_SUFFIXES = (
    "_year", "_month", "_quarter", "_day", "_day_of_week", "_is_weekend", "_week_of_year",
)
_AUDIT_TRAIL_SUFFIXES = ("_raw", "_scaled", "_was_clipped")
_VALIDATION_FLAG_SUFFIXES = ("_range_failed", "_rate_failed", "_reconciliation_failed", "_parse_failed")


def _categorize_added_column(col, schema_blueprint):
    meta = schema_blueprint.get(col, {}) if isinstance(schema_blueprint, dict) else {}
    note = meta.get("notes", "") if isinstance(meta, dict) else ""
    if isinstance(note, str) and ("one-hot encoded from" in note or "+Other encoded from" in note):
        source = note.split(" from ", 1)[-1].split(" (")[0].strip()
        return "one_hot_encoding", source
    if isinstance(note, str) and "ordinal encoded into" in note:
        return "ordinal_encoding", None
    if col.startswith("derived_"):
        return "derived_metric", None
    if col.endswith(_DATE_FEATURE_SUFFIXES):
        for suffix in _DATE_FEATURE_SUFFIXES:
            if col.endswith(suffix):
                return "date_feature_extraction", col[: -len(suffix)]
    if col.endswith(_AUDIT_TRAIL_SUFFIXES):
        return "audit_trail", None
    if col.endswith(_VALIDATION_FLAG_SUFFIXES):
        return "validation_flag", None
    return "other", None


_SHAPE_EXPLANATION_LABELS = {
    "one_hot_encoding": "one-hot/category encoding of",
    "ordinal_encoding": "ordinal encoding of categorical columns",
    "derived_metric": "derived business metrics computed from existing columns",
    "date_feature_extraction": "date-part features (year/month/quarter/etc.) extracted from",
    "audit_trail": "internal audit-trail columns (raw/scaled/clip-flag copies) kept for transparency",
    "validation_flag": "structural validation flag columns",
    "other": "additional columns",
}


def _extract_shape_explanation(state):
    """Explain WHY the cleaned shape differs from the raw file's shape, sourced
    from the actual columns the pipeline added/removed and Agent 3's
    row_accounting ledger - not written per-dataset."""
    raw_shape = state.get("raw_shape") or {}
    if not raw_shape:
        raw_shape = (state.get("raw_profile", {}) or {}).get("shape", {}) or {}
    raw_cols = raw_shape.get("cols")
    raw_rows = raw_shape.get("rows")
    cleaned_df = state.get("cleaned_df")
    if cleaned_df is None:
        return {}

    raw_profile = state.get("raw_profile", {}) or {}
    raw_col_names = set((raw_profile.get("columns", {}) or {}).keys())
    schema_blueprint = state.get("schema_blueprint", {}) or {}
    cleaned_cols = int(cleaned_df.shape[1])
    cleaned_rows = int(cleaned_df.shape[0])

    added_cols = [c for c in cleaned_df.columns if raw_col_names and c not in raw_col_names]
    removed_cols = [c for c in raw_col_names if c not in cleaned_df.columns]

    groups = {}
    sources_by_group = {}
    for col in added_cols:
        group, source = _categorize_added_column(col, schema_blueprint)
        groups.setdefault(group, []).append(col)
        if source:
            sources_by_group.setdefault(group, set()).add(source)

    column_explanations = []
    for group, cols in groups.items():
        label = _SHAPE_EXPLANATION_LABELS.get(group, group)
        sources = sorted(sources_by_group.get(group, set()))
        if sources:
            column_explanations.append(f"{len(cols)} column(s) added via {label} {', '.join(sources)}")
        else:
            column_explanations.append(f"{len(cols)} column(s) added: {label}")
    if removed_cols:
        column_explanations.append(f"{len(removed_cols)} column(s) dropped: {', '.join(sorted(removed_cols))}")

    column_ledger = state.get("column_ledger", {}) or {}
    row_accounting = column_ledger.get("row_accounting", {}) if isinstance(column_ledger, dict) else {}
    row_accounting = row_accounting or {}
    row_explanations = []
    exact = int(row_accounting.get("exact_duplicates_removed", 0) or 0)
    canonical = int(row_accounting.get("rows_dropped_by_canonical_dedup", 0) or 0)
    imputation_drop = int(row_accounting.get("rows_dropped_by_imputation", 0) or 0)
    if exact:
        row_explanations.append(f"{exact} row(s) removed as exact duplicates")
    if canonical:
        row_explanations.append(f"{canonical} row(s) removed as near-duplicates after category normalization")
    if imputation_drop:
        row_explanations.append(f"{imputation_drop} row(s) dropped per missing-value/identifier policy")

    return {
        "raw_rows": raw_rows,
        "raw_cols": raw_cols,
        "cleaned_rows": cleaned_rows,
        "cleaned_cols": cleaned_cols,
        "column_delta": (cleaned_cols - raw_cols) if raw_cols is not None else None,
        "row_delta": (cleaned_rows - raw_rows) if raw_rows is not None else None,
        "column_explanations": column_explanations,
        "row_explanations": row_explanations,
    }


def _extract_quality_facts(state):
    data_quality = state.get("data_quality", {}) or {}
    raw_profile = state.get("raw_profile", {}) or {}
    schema_blueprint = state.get("schema_blueprint", {}) or {}
    column_profile = raw_profile.get("columns", {}) or {}
    missing_values = []
    for col, profile in column_profile.items():
        if not isinstance(profile, dict):
            continue
        missing_count = int(profile.get("missing_count", 0) or 0)
        missing_pct = profile.get(
            "missing_rate_pct",
            profile.get("missing_pct", profile.get("missing_percentage", 0.0)),
        )
        meta = schema_blueprint.get(col, {}) if isinstance(schema_blueprint, dict) else {}
        null_policy = meta.get("null_policy", {}) if isinstance(meta, dict) else {}
        action = null_policy.get("action") if isinstance(null_policy, dict) else None
        if not action and isinstance(meta, dict):
            action = meta.get("imputation_strategy", "none")
        if action == "none":
            action = "left as null"
        missing_values.append({
            "column": col,
            "count": missing_count,
            "pct": round(float(missing_pct or 0.0), 2),
            "action": action or "left as null",
        })

    column_ledger = state.get("column_ledger", {}) or {}
    row_accounting = column_ledger.get("row_accounting", {}) if isinstance(column_ledger, dict) else {}
    exact_duplicates = int(row_accounting.get("exact_duplicates_removed", 0) or 0)
    canonical_duplicates = int(row_accounting.get("rows_dropped_by_canonical_dedup", 0) or 0)
    imputation_rows = int(row_accounting.get("rows_dropped_by_imputation", 0) or 0)
    return {
        "overall_quality_score": data_quality.get("overall_quality_score"),
        "overall_quality_score_pre_anomaly": data_quality.get("overall_quality_score_pre_anomaly"),
        "anomaly_quality_penalty": data_quality.get("anomaly_quality_penalty"),
        "raw_completeness_pct": data_quality.get("raw_completeness_pct"),
        "raw_missing_pct": data_quality.get("raw_missing_pct"),
        "remaining_null_pct": data_quality.get("remaining_null_pct"),
        "rule_manifest": data_quality.get("rule_manifest") or state.get("rule_manifest", {}),
        "completeness_pct": data_quality.get("raw_completeness_pct"),
        "duplicates": {
            "exact_count": exact_duplicates,
            "near_duplicate_count": canonical_duplicates,
            "rows_dropped_for_missing_values": imputation_rows,
            "action": "exact duplicates removed; canonical near-duplicates collapsed; missing-value rows dropped per policy",
        },
        "duplicates_removed": exact_duplicates + canonical_duplicates,
        "missing_values": missing_values,
        "statistical_outlier_row_pct": data_quality.get("statistical_outlier_row_pct"),
        "data_quality_issue_row_pct": data_quality.get("data_quality_issue_row_pct"),
        "data_quality_issue_penalty": data_quality.get("data_quality_issue_penalty"),
        # Real keys produced by agent_3._compute_enhanced_quality_score (the
        # previously-read completeness_pct/duplicates_removed never existed).
        "duplicate_rate_pct": data_quality.get("duplicate_rate_pct"),
        "raw_missing_pct": data_quality.get("raw_missing_pct"),
        "remaining_null_pct": data_quality.get("remaining_null_pct"),
        # docs known-issue: derived metrics (profit, margin, per-unit, etc.) must
        # agree with any equivalent ground-truth column already in the source
        # data - see agent_3._reconcile_derived_metrics. Only diverged records
        # are surfaced here; the full audit trail also lives in preprocessing_log.
        "derived_metric_reconciliation": [
            r for r in (data_quality.get("derived_metric_reconciliation") or []) if r.get("diverged")
        ],
    }


# Human-readable labels for Agent 3's null_policy actions (agents.agent_3._impute).
_NULL_ACTION_LABELS = {
    "impute_mean": "mean imputation",
    "impute_median": "median imputation",
    "impute_mode": "mode imputation",
    "impute_unknown_label": "constant value (Unknown)",
    "impute_forward_fill": "forward fill",
    "impute_knn": "model-based imputation (knn)",
    "impute_iterative": "model-based imputation (iterative)",
    "drop_rows": "rows dropped",
    "drop_column": "column dropped",
    "flag_only": "left as null",
    "none": "left as null",
}


def _missing_value_action_label(meta, raw_missing, remaining_missing):
    """Report the action the pipeline ACTUALLY took for a column's missing
    values, not merely what the schema requested.

    Agent 3 blocks imputation on currency/financial columns and silently skips
    it when a strategy can't run, so the blueprint may say "impute_median"
    while the nulls survive. We reconcile the intended null_policy action
    against the real null reduction in cleaned_df so the report never claims an
    imputation that didn't happen (docs/known_issues.md #8, Bug 3).
    """
    if raw_missing == 0:
        return "none"

    null_policy = meta.get("null_policy", {}) if isinstance(meta.get("null_policy"), dict) else {}
    null_action = null_policy.get("action")
    if null_action is None:
        null_action = {
            "mean": "impute_mean", "median": "impute_median", "mode": "impute_mode",
            "drop": "drop_rows", "unknown_label": "impute_unknown_label",
        }.get(meta.get("imputation_strategy", "none"), "none")

    # Currency/financial imputation is blocked in agent_3._impute regardless of
    # what the blueprint requested.
    if meta.get("semantic_tag") in {"currency", "financial"} and str(null_action).startswith("impute_"):
        return "left as null"

    # Reconcile intent against reality: if imputation was requested but the
    # column still carries all (or more of) its nulls, it didn't actually run.
    if remaining_missing is not None and str(null_action).startswith("impute_") and remaining_missing >= raw_missing:
        return "left as null"

    return _NULL_ACTION_LABELS.get(null_action, "left as null")


def _extract_data_quality_detail(state):
    """Surface what the preprocessing pipeline actually did about duplicates and
    missing values - previously computed internally but never reported
    (docs/known_issues.md #7/#8, Bug 3).

    Duplicate counts come from Agent 3's row_accounting ledger; missing-value
    counts come from Agent 1's raw profile (pre-cleaning), with the per-column
    action reconciled against cleaned_df so the report reflects reality.
    """
    column_ledger = state.get("column_ledger", {}) or {}
    row_accounting = column_ledger.get("row_accounting", {}) if isinstance(column_ledger, dict) else {}
    row_accounting = row_accounting or {}

    exact_dups = int(row_accounting.get("exact_duplicates_removed", 0) or 0)
    near_dups = int(row_accounting.get("rows_dropped_by_canonical_dedup", 0) or 0)

    duplicates = {
        "exact_duplicates_detected": exact_dups,
        "exact_duplicates_removed": exact_dups,
        "near_duplicates_detected": near_dups,
        "near_duplicates_removed": near_dups,
        # Agent 3 removes exact duplicates unconditionally (Step 0) and
        # near-duplicates after category canonicalization (Step 3b).
        "action": "duplicates removed" if exact_dups > 0 else "no exact duplicates detected",
        "near_duplicate_action": (
            "near-duplicates removed (post-canonicalization)" if near_dups > 0 else "none detected"
        ),
    }

    raw_profile = state.get("raw_profile", {}) or {}
    columns_profile = raw_profile.get("columns", {}) or {}
    total_rows = (raw_profile.get("shape", {}) or {}).get("rows", 0) or 0
    schema_blueprint = state.get("schema_blueprint", {}) or {}
    cleaned_df = state.get("cleaned_df")

    missing_rows = []
    for col, prof in columns_profile.items():
        raw_missing = int((prof or {}).get("missing_count", 0) or 0)
        if raw_missing == 0:
            continue
        missing_pct = (prof or {}).get("missing_rate_pct")
        if missing_pct is None:
            missing_pct = round(raw_missing / max(total_rows, 1) * 100, 2)

        remaining_missing = None
        if cleaned_df is not None and col in getattr(cleaned_df, "columns", []):
            remaining_missing = int(cleaned_df[col].isna().sum())

        meta = schema_blueprint.get(col) if isinstance(schema_blueprint.get(col), dict) else {}
        action = _missing_value_action_label(meta or {}, raw_missing, remaining_missing)

        missing_rows.append({
            "column": col,
            "missing_count": raw_missing,
            "missing_pct": missing_pct,
            "action": action,
        })

    missing_rows.sort(key=lambda r: r["missing_count"], reverse=True)

    return {
        "duplicates": duplicates,
        "missing_values": missing_rows,
        "has_missing": bool(missing_rows),
    }



def _extract_correlation_facts(stats):
    # `strong_pairs` already excludes pairs involving Agent 4's leakage-flagged
    # columns (agent_4.flag_leakage_columns) - flagged columns are surfaced
    # separately via _extract_excluded_columns_facts instead of as findings here.
    correlation = stats.get("correlation", {}) or {}
    strong_pairs = correlation.get("strong_pairs", []) or []
    sample_size = correlation.get("n")  # rows actually used for this pair, for plain-language framing
    ranked = sorted(strong_pairs, key=lambda p: abs(p.get("pearson_r", 0)), reverse=True)
    return [{**pair, "n": sample_size} for pair in ranked[:TOP_CORRELATIONS_LIMIT]]


def _extract_excluded_columns_facts(stats):
    """Columns Agent 4 flagged as likely IDs/leakage artifacts, plus the correlation
    pairs involving them - kept out of headline findings but still surfaced as an
    appendix so nothing is silently dropped without explanation."""
    correlation = stats.get("correlation", {}) or {}
    return {
        "flagged_columns": correlation.get("flagged_columns", []) or [],
        "excluded_pairs": (correlation.get("excluded_pairs", []) or [])[:TOP_CORRELATIONS_LIMIT],
    }


def _extract_formulaic_pairs_facts(stats):
    """Pairs excluded from Top Correlations because one column is a known
    direct formula of the other (docs/known_issues.md #5), e.g. derived_profit
    vs. its own revenue/cost inputs - distinct from the ID/leakage exclusions
    above, so surfaced as its own appendix."""
    correlation = stats.get("correlation", {}) or {}
    return (correlation.get("formulaic_pairs", []) or [])[:TOP_CORRELATIONS_LIMIT]


def _extract_growth_facts(stats):
    growth_rates = stats.get("growth_rates", {}) or {}
    facts = {}

    monthly = growth_rates.get("monthly", [])
    if monthly:
        latest = monthly[-1]
        facts["latest_month"] = {
            "label": latest.get("label"),
            "mom_growth_pct": latest.get("mom_growth_pct"),
        }

    quarterly = growth_rates.get("quarterly", [])
    if quarterly:
        latest_q = quarterly[-1]
        facts["latest_quarter"] = {
            "label": latest_q.get("label"),
            "qoq_growth_pct": latest_q.get("qoq_growth_pct"),
        }

    seasonality = stats.get("seasonality", {}) or {}
    if "monthly" in seasonality:
        facts["best_month"] = seasonality["monthly"].get("best_month")
        facts["worst_month"] = seasonality["monthly"].get("worst_month")
    if "quarterly" in seasonality:
        facts["best_quarter"] = seasonality["quarterly"].get("best_quarter")
        facts["worst_quarter"] = seasonality["quarterly"].get("worst_quarter")

    return facts


def _slice_top_bottom_rows(cat_col, data, limit=TOP_RANKING_LIMIT):
    """Slice a ranking/profit-breakdown dict's top/bottom lists for display.

    Agent 4's `top`/`bottom` lists are independently computed (head(n)/tail(n)
    of the same descending-sorted groupby) and overlap whenever
    `total_categories <= n` - in that case they're literally identical lists.
    Independently truncating each to `limit` (as this used to do) then shows
    the same top-ranked rows twice under "Top" and "Bottom" labels, and the
    true worst performer never appears anywhere - a real category silently
    missing despite the header's (correct) total_categories count
    (docs/known_issues.md #4). Reversing `bottom` (so it reads worst-first)
    and excluding any category already shown in `top` guarantees every
    distinct category appears at least once whenever total_categories <= 2*limit.
    """
    top_rows = (data.get("top") or [])[:limit]
    shown_keys = {row.get(cat_col) for row in top_rows}

    bottom_sliced = []
    for row in reversed(data.get("bottom") or []):
        if row.get(cat_col) in shown_keys:
            continue
        bottom_sliced.append(row)
        shown_keys.add(row.get(cat_col))
        if len(bottom_sliced) >= limit:
            break

    return {
        "top": top_rows,
        "bottom": bottom_sliced,
        "total_categories": data.get("total_categories"),
        "metric_label": data.get("metric_label"),
    }


def _extract_ranking_facts(stats):
    top_bottom = stats.get("top_bottom", {}) or {}
    return {cat_col: _slice_top_bottom_rows(cat_col, data) for cat_col, data in top_bottom.items()}


def _extract_profit_facts(stats):
    profit_breakdown = stats.get("profit_breakdown", {}) or {}
    return {cat_col: _slice_top_bottom_rows(cat_col, data) for cat_col, data in profit_breakdown.items()}


def _extract_cross_dimensional_facts(stats):
    """The 5 cross-dimensional analyses added alongside Part B's ranking fix
    (discount-vs-return-rate, margin-by-category-over-time, discount/margin by
    rep, order value by segment, shipping cost by region) - each is already
    empty-safe (agent_4 returns {} when its required columns aren't present)."""
    return {
        "discount_return_rate": stats.get("discount_return_rate", {}) or {},
        "category_margin_trend": stats.get("category_margin_trend", {}) or {},
        "rep_discount_margin": stats.get("rep_discount_margin", {}) or {},
        "segment_order_value": stats.get("segment_order_value", {}) or {},
        "region_shipping_cost": stats.get("region_shipping_cost", {}) or {},
        "shipping_lead_time": stats.get("shipping_lead_time", {}) or {},
    }


def _extract_normalization_facts(state):
    """Flatten Agent 3's per-column fuzzy category merges (docs/known_issues.md
    #2) into report-ready rows: column, raw spelling, canonical spelling, and
    how many rows had the raw spelling."""
    category_normalization = state.get("category_normalization", {}) or {}
    rows = []
    for col, merges in category_normalization.items():
        for merge in merges or []:
            rows.append({
                "column": col,
                "raw": merge.get("raw"),
                "canonical": merge.get("canonical"),
                "row_count": merge.get("row_count"),
            })
    return rows


def _jsonable_example_rows(rows) -> list:
    """Coerce example-row values (pandas Timestamps, numpy scalars, NaN…) into
    JSON-safe primitives so the template's `| tojson` never explodes."""
    import math

    def convert(value):
        if isinstance(value, dict):
            return {str(k): convert(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [convert(v) for v in value]
        if isinstance(value, (bool, str)) or value is None:
            return value
        if hasattr(value, "isoformat"):  # datetime / Timestamp
            return str(value)
        if isinstance(value, (int, float)):
            try:
                f = float(value)
                return None if math.isnan(f) else value
            except (TypeError, ValueError):
                return str(value)
        return str(value)

    if not isinstance(rows, list):
        return []
    return [convert(row) for row in rows]


def _extract_anomaly_facts(stats):
    summary = dict(stats.get("anomaly_summary", {}) or {})
    # Surface the structural data-quality issues alongside the statistical
    # anomalies so the report can tell the two apart (Bug 4, Task B/C).
    dq_issues = stats.get("data_quality_issues", {}) or {}
    summary["data_quality_issue_rows"] = dq_issues.get("data_quality_issue_rows", 0)
    summary["data_quality_issue_row_pct"] = dq_issues.get("data_quality_issue_row_pct", 0.0)
    summary["confident_issue_row_pct"] = dq_issues.get("confident_issue_row_pct", summary["data_quality_issue_row_pct"])
    summary["review_required"] = bool(dq_issues.get("review_required"))
    summary["issues_by_rule"] = dq_issues.get("issues_by_rule", {})
    rule_details = {}
    for rule, detail in (dq_issues.get("rule_details", {}) or {}).items():
        if isinstance(detail, dict) and detail.get("example_rows"):
            detail = {**detail, "example_rows": _jsonable_example_rows(detail["example_rows"])}
        rule_details[rule] = detail
    summary["rule_details"] = rule_details
    summary["rules_checked"] = dq_issues.get("rules_checked", [])
    summary["prioritized_anomalies"] = summary.get("prioritized_anomalies", [])
    summary["business_impact_total"] = summary.get("business_impact_total", 0.0)
    summary["rule_manifest"] = summary.get("rule_manifest") or dq_issues.get("rule_manifest", {})
    return summary


def _extract_regression_facts(stats):
    regression = stats.get("regression", {}) or {}
    significant = [
        {"column": col, **metrics}
        for col, metrics in regression.items()
        if isinstance(metrics, dict)
        and metrics.get("significant")
        # A missing "n" (older/mocked stats) is treated as unknown, not insufficient.
        and (metrics.get("n") is None or int(metrics["n"]) >= MIN_TREND_SAMPLE_SIZE)
    ]
    significant.sort(key=lambda r: r.get("r_squared", 0), reverse=True)
    return significant[:TOP_REGRESSION_LIMIT]


def _extract_validation_facts(state):
    validation_report = state.get("validation_report", {}) or {}
    semantic_agreement = validation_report.get("semantic_tagging_agreement", {}) or {}
    # Agent 5's deterministic reconciliation of pipeline output against the
    # source ledger/dataset - a different check from the narrative self-check,
    # and the runtime analog of the Phase 1 ground-truth test harness
    # (tests/test_ground_truth_reconciliation.py).
    tier1_checks = validation_report.get("tier1_checks", {}) or {}
    row_reconciliation = tier1_checks.get("row_reconciliation") if isinstance(tier1_checks, dict) else None
    return {
        "overall_validation_score": validation_report.get("overall_validation_score"),
        "confidence_in_score": validation_report.get("confidence_in_score"),
        "rule_review_required": validation_report.get("rule_review_required", False),
        "passed": validation_report.get("passed"),
        "flagged_issue_count": len(validation_report.get("flagged_issues", []) or []),
        "cohen_kappa": semantic_agreement.get("cohen_kappa"),
        "ground_truth_reconciliation": row_reconciliation,
    }


def _extract_reliability_facts(state):
    reliability = state.get("reliability", {}) or {}
    return {
        "overall_confidence": reliability.get("overall_confidence"),
        "decision_readiness": reliability.get("decision_readiness"),
    }


def _extract_chart_summaries(state, limit: int = 12) -> list[dict]:
    """Compact chart inventory handed to the LLM so captions can reference
    real charts by id (hallproofed: unknown ids are dropped at merge time)."""
    out = []
    for spec in (state.get("chart_specs") or [])[:limit]:
        if not isinstance(spec, dict):
            continue
        out.append({
            "id": spec.get("id"),
            "title": spec.get("title"),
            "what_it_shows": spec.get("descriptive") or spec.get("plain_summary") or spec.get("why_it_matters") or "",
            "why_it_looks_that_way": spec.get("diagnostic") or "",
        })
    return out


def _extract_insight_facts(state):
    """Pure-Python fact extraction. No LLM calls, no hallucination risk."""
    stats = state.get("stats", {}) or {}
    return {
        "dataset": _extract_dataset_facts(state),
        "shape_explanation": _extract_shape_explanation(state),
        "data_quality": _extract_quality_facts(state),
        "data_quality_detail": _extract_data_quality_detail(state),
        "top_correlations": _extract_correlation_facts(stats),
        "excluded_columns": _extract_excluded_columns_facts(stats),
        "formulaic_pairs": _extract_formulaic_pairs_facts(stats),
        "growth": _extract_growth_facts(stats),
        "rankings": _extract_ranking_facts(stats),
        "profit_breakdown": _extract_profit_facts(stats),
        "cross_dimensional": _extract_cross_dimensional_facts(stats),
        "category_normalization": _extract_normalization_facts(state),
        "anomalies": _extract_anomaly_facts(stats),
        "significant_trends": _extract_regression_facts(stats),
        "validation": _extract_validation_facts(state),
        "reliability": _extract_reliability_facts(state),
        "charts": _extract_chart_summaries(state),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1b — NARRATIVE CLAIM GROUNDING (self-check, no LLM)
# ─────────────────────────────────────────────────────────────────────────────

_CLAIM_PATTERN = re.compile(r"-?\d[\d,]*\.?\d*%?")


def _flatten_numeric_facts(insight_facts: dict) -> set[float]:
    """Collect every numeric value appearing anywhere in the deterministic facts."""
    values: set[float] = set()

    def _walk(node):
        if isinstance(node, dict):
            for value in node.values():
                _walk(value)
        elif isinstance(node, (list, tuple)):
            for value in node:
                _walk(value)
        elif isinstance(node, bool):
            return
        elif isinstance(node, (int, float)):
            try:
                values.add(round(float(node), 2))
            except (TypeError, ValueError):
                pass

    _walk(insight_facts)
    return values


def _extract_numeric_claims(text: str) -> list[float]:
    """Pull out numbers worth fact-checking, skipping small ordinal-style digits
    (e.g. "top 3") that aren't really claims about the data."""
    if not text:
        return []

    claims = []
    for match in _CLAIM_PATTERN.findall(text):
        has_percent = match.endswith("%")
        cleaned = match.rstrip("%").replace(",", "")
        if not cleaned or cleaned in {"-", "."}:
            continue
        try:
            value = float(cleaned)
        except ValueError:
            continue
        has_decimal = "." in cleaned
        if has_percent or has_decimal or abs(value) >= 10:
            claims.append(value)
    return claims


def _check_narrative_contradictions(narrative: dict) -> dict:
    """Detect contradictory statements within the narrative that may confuse the reader.
    
    Returns a dict with:
    - contradictions_found: bool
    - detected_pairs: list of (text1, text2, reason) tuples
    - recommendation: suggested fix
    """
    contradictions = []
    
    # Keywords indicating opposite claims
    problem_keywords = {"fix", "issue", "problem", "broken", "wrong", "error", "defect", "quality concern"}
    confidence_keywords = {"solid", "reliable", "trustworthy", "high quality", "good quality", "act with confidence"}
    
    sections_to_check = []
    story = narrative.get("story")
    if isinstance(story, dict):
        sections_to_check.extend([
            ("story.what_happened", story.get("what_happened", "")),
            ("story.why_it_matters", story.get("why_it_matters", "")),
            ("story.what_to_do_next", story.get("what_to_do_next", "")),
        ])
    
    sections_to_check.extend([
        ("executive_summary", narrative.get("executive_summary", "")),
        ("plain_language_insights", " ".join(narrative.get("plain_language_insights", []))),
        ("bottom_line", narrative.get("bottom_line", "")),
    ])
    
    # Check for contradictory topic pairs
    for i, (label1, text1) in enumerate(sections_to_check):
        if not text1:
            continue
        text1_lower = str(text1).lower()
        has_problem = any(kw in text1_lower for kw in problem_keywords)
        has_confidence = any(kw in text1_lower for kw in confidence_keywords)
        
        for label2, text2 in sections_to_check[i+1:]:
            if not text2:
                continue
            text2_lower = str(text2).lower()
            has_problem2 = any(kw in text2_lower for kw in problem_keywords)
            has_confidence2 = any(kw in text2_lower for kw in confidence_keywords)
            
            # Contradiction: one says "fix this problem" the other says "data is fine"
            if (has_problem and has_confidence2) or (has_confidence and has_problem2):
                contradictions.append({
                    "section1": label1,
                    "text1": text1[:100] + "..." if len(text1) > 100 else text1,
                    "section2": label2,
                    "text2": text2[:100] + "..." if len(text2) > 100 else text2,
                    "issue": "contradictory claims about data quality/trustworthiness"
                })
    
    return {
        "contradictions_found": bool(contradictions),
        "contradiction_count": len(contradictions),
        "detected_pairs": contradictions,
        "recommendation": "Review reported data quality issues vs. confidence statements for consistency" if contradictions else None,
    }


def _check_narrative_grounding(insight_facts: dict, narrative: dict, tolerance: float = CLAIM_GROUNDING_TOLERANCE) -> dict:
    """Verify that numbers cited in the LLM narrative actually appear in the
    deterministic facts it was given, within a small tolerance for rounding.

    This is a best-effort self-check, not a hard gate: it flags likely
    hallucinated numbers instead of silently trusting free-form LLM prose.
    """
    known_values = _flatten_numeric_facts(insight_facts)

    sections = []
    if narrative.get("executive_summary"):
        sections.append(("executive_summary", narrative["executive_summary"]))
    for index, finding in enumerate(narrative.get("key_findings") or []):
        sections.append((f"key_finding[{index}]", finding))
    story = narrative.get("story")
    if isinstance(story, dict):
        for key in ("what_happened", "why_it_matters", "what_to_do_next"):
            text = story.get(key)
            if isinstance(text, str) and text:
                sections.append((f"story.{key}", text))
    for caption_id, caption in (narrative.get("chart_captions") or {}).items():
        if isinstance(caption, str) and caption:
            sections.append((f"caption[{caption_id}]", caption))

    checked = 0
    grounded = 0
    flagged = []

    for label, text in sections:
        for claim in _extract_numeric_claims(text):
            checked += 1
            is_grounded = any(
                abs(claim - candidate) <= max(tolerance, abs(candidate) * 0.05)
                for known in known_values
                for candidate in ({known, known * 100, known / 100} if known else {known})
            )
            if is_grounded:
                grounded += 1
            else:
                flagged.append({"source": label, "value": claim})

    confidence = round(grounded / checked, 3) if checked else 1.0
    return {
        "claims_checked": checked,
        "claims_grounded": grounded,
        "claims_flagged": len(flagged),
        "flagged_examples": flagged[:5],
        "confidence": confidence,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2 — LLM NARRATIVE GENERATION (Groq -> Gemini fallback)
# ─────────────────────────────────────────────────────────────────────────────

INSIGHT_SYSTEM_PROMPT = """You are a senior data analyst writing the narrative section of an \
automated data analysis report. You will be given a JSON object of facts that have already \
been computed deterministically from the dataset - descriptive stats, correlations, growth \
rates, rankings, anomalies, regression trends, and data-quality/validation scores.

Rules:
- Use ONLY the numbers and facts given in the JSON. Never invent a number, column name, or \
statistic that is not present in the input.
- If a section of the facts is empty or missing, do not mention it.
- Be concise and business-readable, not academic.
- Do not report correlations, distributions, or findings involving columns listed under \
"excluded_columns" (in facts.excluded_columns.flagged_columns / excluded_pairs). These are \
identifiers or external-model artifacts, not business signals - never narrate them as insights.
- "dataset.raw_rows"/"dataset.raw_cols" describe the original file as ingested. \
"dataset.cleaned_rows"/"dataset.cleaned_cols" describe the dataset AFTER cleaning/encoding, \
which can have a different (often larger, due to one-hot encoding and feature engineering) \
column count. When the executive summary states "the dataset contains X rows and Y columns", \
X and Y MUST be raw_rows/raw_cols. If you also mention the post-processing column count, label \
it explicitly (e.g. "expanded to N features for analysis") - never present it as the raw shape.

You must also write a "plain_language_insights" section aimed at a completely non-technical \
reader (e.g. a small business owner or manager with no statistics background). This is the \
most important section of the report for that audience, so it must surface things they would \
genuinely struggle to notice just by glancing at a spreadsheet - e.g. which category quietly \
drives most of the revenue, which month/quarter is unexpectedly strong or weak, which two \
things move together in a way that has a real business consequence, or which rows look wrong \
and are worth double-checking.
Strict rules for "plain_language_insights" and "bottom_line":
- NEVER use statistical jargon or symbols: no "r=", "p-value", "r-squared", "z-score", \
"standard deviation", "correlation coefficient", "regression", "outlier" (say "unusual entries" \
instead), etc.
- Every bullet must be a real-world, actionable observation phrased the way you'd explain it to \
a colleague over coffee, e.g. "Your top 3 regions bring in 68% of all revenue - the rest barely \
move the needle" or "Sales quietly dip every February - worth planning a promotion around then".
- Still ground every bullet in the actual numbers/columns from the facts JSON - just express \
them in plain English instead of statistical language.
- Do not repeat the same point already phrased differently; each bullet should be a distinct, \
useful takeaway.
- Never write the literal phrase "plain English", "in simple terms", "in layman's terms", "in \
other words", or any other meta-comment announcing that you're simplifying - just write the \
explanation directly, in plain language, without narrating that you're doing so.

Return ONLY a JSON object with exactly these keys:
{
  "executive_summary": "2-4 sentence overview of the dataset and its most important signal",
  "key_findings": ["4-6 bullet strings, each citing a concrete number from the facts"],
  "story": {
    "what_happened": "2-3 plain sentences describing the main movements in the data",
    "why_it_matters": "1-3 sentences on the business consequence of those movements",
    "what_to_do_next": "1-3 sentences of the single most sensible next action"
  },
  "chart_captions": {
    "<chart id from facts.charts>": "ONE extra sentence, plain English, that reader should notice in that chart"
  },
  "glossary_terms": [
    {"term": "a technical term you were forced to use elsewhere", "plain_explanation": "one-sentence explanation a non-technical reader understands"}
  ],
  "plain_language_insights": ["4-6 bullet strings for non-technical readers, following the rules above"],
  "bottom_line": "1 sentence, plain English, the single most useful takeaway for a non-technical reader",
  "risks_and_caveats": ["1-3 bullet strings about data quality/validation concerns, if any"],
  "recommendations": ["3-5 concrete, actionable bullet strings grounded in the findings"]
}

Rules for the new keys:
- "story" must read like three short paragraphs of one continuous explanation - no jargon, no bullet lists inside.
- Only include ids that appear in facts.charts under "chart_captions"; at most 4.
- "glossary_terms" only for terms you genuinely used; never define everyday words.
"""


_MAX_LIST_ITEMS_FOR_PROMPT = 8
# `rule_details.<rule>.example_rows` (agent_4._detect_data_quality_issues) holds full
# raw-dataframe rows for manual inspection in the HTML report - on a one-hot-encoded
# dataset that's dozens of columns per example row, and being a dict-of-dicts (not a
# bare list) it isn't shrunk by the list-length cap below. The narrative never cites
# individual example rows (only counts/pct), so it's dropped from the LLM prompt copy
# entirely - this was the actual cause of a 17863-token 413 on Groq even after list
# truncation, and the same bloat also risks tripping Gemini's output-token budget.
_PROMPT_EXCLUDED_KEYS = {"example_rows"}


def _truncate_lists_for_prompt(node, max_items: int = _MAX_LIST_ITEMS_FOR_PROMPT):
    """Recursively cap list lengths so unbounded facts (e.g. per-category monthly
    trend series) can't blow the narrative prompt past Groq's per-request TPM cap."""
    if isinstance(node, dict):
        return {
            key: _truncate_lists_for_prompt(value, max_items)
            for key, value in node.items()
            if key not in _PROMPT_EXCLUDED_KEYS
        }
    if isinstance(node, list):
        truncated = [_truncate_lists_for_prompt(item, max_items) for item in node[:max_items]]
        if len(node) > max_items:
            truncated.append(f"...{len(node) - max_items} more rows omitted for brevity")
        return truncated
    return node


def _compact_dimension_sections(sections: dict, max_sections: int = 4, max_rows: int = 3) -> dict:
    """Keep the strongest bounded slice of each dimension-oriented analysis."""
    compact = {}
    for section_name, section in list((sections or {}).items())[:max_sections]:
        if not isinstance(section, dict):
            compact[section_name] = section
            continue
        reduced = {}
        for key, value in section.items():
            if key in {"top", "bottom", "records", "buckets"} and isinstance(value, list):
                reduced[key] = value[:max_rows]
            elif key not in {"series", "distribution", "anomaly_indices", "anomaly_values"}:
                reduced[key] = value
        compact[section_name] = reduced
    return compact


def _compact_cross_dimensional_facts(analyses: dict) -> dict:
    """Retain labels and representative values, dropping full time series."""
    compact = {}
    for analysis_name, analysis in (analyses or {}).items():
        if not isinstance(analysis, dict):
            compact[analysis_name] = analysis
            continue
        reduced = {}
        for key, value in analysis.items():
            if isinstance(value, list):
                reduced[key] = value[:4]
            elif isinstance(value, dict):
                reduced[key] = {
                    name: rows[:4] if isinstance(rows, list) else rows
                    for name, rows in list(value.items())[:4]
                }
            else:
                reduced[key] = value
        compact[analysis_name] = reduced
    return compact


def _build_narrative_prompt_facts(insight_facts: dict) -> dict:
    """Build a compact, narrative-only view of the deterministic facts.

    The full facts remain available to report rendering and grounding checks;
    the LLM only needs the decision-bearing summaries, not appendix data or
    repeated quality/detail fields.
    """
    quality = insight_facts.get("data_quality", {}) or {}
    quality_detail = insight_facts.get("data_quality_detail", {}) or {}
    anomalies = insight_facts.get("anomalies", {}) or {}
    compact_quality = {
        key: quality.get(key)
        for key in (
            "overall_quality_score", "overall_quality_score_pre_anomaly",
            "anomaly_quality_penalty", "raw_completeness_pct", "raw_missing_pct",
            "remaining_null_pct", "statistical_outlier_row_pct",
            "data_quality_issue_row_pct", "data_quality_issue_penalty",
            "duplicate_rate_pct", "derived_metric_reconciliation",
        )
        if key in quality
    }
    compact_quality_detail = {
        "duplicates": quality_detail.get("duplicates", {}),
        "missing_values": (quality_detail.get("missing_values", []) or [])[:5],
        "has_missing": quality_detail.get("has_missing", False),
    }
    compact_anomalies = {
        key: anomalies.get(key)
        for key in (
            "unique_flagged_rows", "unique_flagged_row_pct", "data_quality_issue_rows",
            "data_quality_issue_row_pct", "confident_issue_row_pct", "review_required",
            "issues_by_rule", "rules_checked", "prioritized_anomalies", "business_impact_total",
        )
        if key in anomalies
    }
    compact_anomalies["rule_details"] = {
        rule: {
            key: detail.get(key)
            for key in ("count", "pct", "review_required", "severity", "impact")
            if key in detail
        }
        for rule, detail in (anomalies.get("rule_details", {}) or {}).items()
        if isinstance(detail, dict)
    }
    prompt_facts = {
        "dataset": insight_facts.get("dataset", {}),
        "shape_explanation": insight_facts.get("shape_explanation", {}),
        "data_quality": compact_quality,
        "data_quality_detail": compact_quality_detail,
        "top_correlations": insight_facts.get("top_correlations", []),
        "excluded_columns": insight_facts.get("excluded_columns", {}),
        "formulaic_pairs": insight_facts.get("formulaic_pairs", []),
        "growth": insight_facts.get("growth", {}),
        "rankings": _compact_dimension_sections(insight_facts.get("rankings", {})),
        "profit_breakdown": _compact_dimension_sections(insight_facts.get("profit_breakdown", {})),
        "cross_dimensional": _compact_cross_dimensional_facts(insight_facts.get("cross_dimensional", {})),
        "category_normalization": insight_facts.get("category_normalization", []),
        "anomalies": compact_anomalies,
        "significant_trends": insight_facts.get("significant_trends", []),
        "validation": insight_facts.get("validation", {}),
        "reliability": insight_facts.get("reliability", {}),
        "charts": insight_facts.get("charts", []),
    }
    prompt_facts = _truncate_lists_for_prompt(prompt_facts, max_items=4)

    def _serialized_size():
        return len(json.dumps(prompt_facts, separators=(",", ":"), default=str))

    # Compact progressively by narrative value. Full `insight_facts` remains
    # untouched for report rendering and claim-grounding validation.
    if _serialized_size() > MAX_NARRATIVE_PROMPT_CHARS:
        for key in ("data_quality_detail", "category_normalization", "excluded_columns", "formulaic_pairs", "validation", "reliability"):
            prompt_facts.pop(key, None)
        prompt_facts = _truncate_lists_for_prompt(prompt_facts, max_items=2)
    if _serialized_size() > MAX_NARRATIVE_PROMPT_CHARS:
        prompt_facts["rankings"] = _compact_dimension_sections(prompt_facts.get("rankings", {}), max_sections=3, max_rows=1)
        prompt_facts["profit_breakdown"] = _compact_dimension_sections(prompt_facts.get("profit_breakdown", {}), max_sections=3, max_rows=1)
        prompt_facts["cross_dimensional"] = _compact_cross_dimensional_facts(prompt_facts.get("cross_dimensional", {}))
        prompt_facts["charts"] = (prompt_facts.get("charts") or [])[:2]
    if _serialized_size() > MAX_NARRATIVE_PROMPT_CHARS:
        prompt_facts["cross_dimensional"] = {}
        prompt_facts["charts"] = []
        prompt_facts["growth"] = {}
        prompt_facts["significant_trends"] = []
    if _serialized_size() > MAX_NARRATIVE_PROMPT_CHARS:
        prompt_facts["rankings"] = _compact_dimension_sections(prompt_facts.get("rankings", {}), max_sections=1, max_rows=1)
        prompt_facts["profit_breakdown"] = _compact_dimension_sections(prompt_facts.get("profit_breakdown", {}), max_sections=1, max_rows=1)
    return prompt_facts


def _call_llm_for_narrative(insight_facts: dict) -> dict:
    """Ask Groq for the narrative, falling back to Gemini on provider failure.

    The prompt facts are truncated to bounded list lengths (see
    `_truncate_lists_for_prompt`) so this stays under Groq's per-request TPM
    cap; if Groq still fails (quota, outage, oversized prompt) Gemini is tried
    next, and the caller falls back to a deterministic narrative if both fail.
    """
    prompt_facts = _build_narrative_prompt_facts(insight_facts)
    user_content = (
        "Write the report narrative for these facts:\n"
        f"{json.dumps(prompt_facts, separators=(',', ':'), default=str)}"
    )

    groq_error: Exception | None = None
    try:
        response = _get_groq_client().chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": INSIGHT_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            max_tokens=AGENT6_MAX_OUTPUT_TOKENS,
            reasoning_effort=GROQ_REASONING_EFFORT,
        )
        raw_text = response.choices[0].message.content.strip()
        narrative = _parse_schema_blueprint_response(raw_text)
        narrative["source"] = "groq"
        return narrative
    except Exception as exc:
        groq_error = exc
        print(f"[Agent 6] Groq ({GROQ_MODEL}) unavailable; trying Gemini: {exc}")

    try:
        narrative = _call_gemini_json_with_failover(
            contents=user_content,
            system_instruction=INSIGHT_SYSTEM_PROMPT,
            temperature=0.2,
            max_output_tokens=AGENT6_MAX_OUTPUT_TOKENS,
        )
        narrative["source"] = "gemini"
        return narrative
    except Exception as gemini_error:
        # Keep BOTH provider errors, each naming its model, so the deterministic
        # fallback that follows records exactly which model hit the wall.
        raise RuntimeError(
            f"Report narrative LLM failed — Groq ({GROQ_MODEL}): {groq_error}; {gemini_error}"
        ) from gemini_error


def _is_material_difference(top_share_pct, comparison_share_pct, threshold_multiplier=1.5, absolute_threshold_pct=5):
    """
    Determine if a difference between top and next performer is "material" enough
    to justify a "leader" claim.
    
    Returns True if:
    - top_share is at least threshold_multiplier times the comparison_share (e.g., 1.5x), OR
    - top_share exceeds comparison_share by at least absolute_threshold_pct points (e.g., 5pp)
    
    This prevents saying "X is your clear leader" when it's 35% vs 34% vs 30%.
    """
    if not top_share_pct or not comparison_share_pct:
        return False
    
    if comparison_share_pct <= 0:
        return True  # Any positive vs zero/negative is material
    
    ratio_test = top_share_pct >= comparison_share_pct * threshold_multiplier
    absolute_test = (top_share_pct - comparison_share_pct) >= absolute_threshold_pct
    
    return ratio_test or absolute_test


def _plain_language_fallback(insight_facts: dict) -> tuple[list[str], str]:
    """Deterministic, jargon-free bullets for non-technical readers, plus a single
    "bottom line" sentence. Built straight from the facts JSON - no LLM involved."""
    bullets = []

    anomalies = insight_facts.get("anomalies") or {}
    quality = insight_facts.get("data_quality") or {}
    structural_penalty = float(quality.get("data_quality_issue_penalty", 0) or 0)
    statistical_penalty = float(quality.get("anomaly_quality_penalty", 0) or 0)
    if structural_penalty > statistical_penalty and anomalies.get("data_quality_issue_rows"):
        bullets.append(
            f"{anomalies['data_quality_issue_rows']} records contain structural data issues, costing "
            f"{structural_penalty} quality points - resolve these before acting on the results."
        )
    elif anomalies.get("unique_flagged_rows"):
        bullets.append(
            f"About {anomalies.get('unique_flagged_row_pct')}% of your records "
            f"({anomalies.get('unique_flagged_rows')} rows) look unusual compared to the rest - "
            f"these are worth a manual check for data-entry mistakes or one-off events."
        )

    for cat_col, data in (insight_facts.get("rankings") or {}).items():
        metric_label = (data.get("metric_label") or "revenue").lower()
        top = (data.get("top") or [None])[0]
        bottom = (data.get("bottom") or [None])[0]
        
        # Check if the difference is material before claiming a "leader"
        top_share = top.get("revenue_share_pct") if top else None
        bottom_share = bottom.get("revenue_share_pct") if bottom else None
        
        if top:
            name = top.get(cat_col)
            share = top_share
            if name is not None and share is not None:
                # Only claim "best performer" if the gap to others is material
                # Use bottom share as a proxy for second-place (might not be exact but good enough)
                if bottom_share and _is_material_difference(share, bottom_share):
                    bullets.append(
                        f"'{name}' is your best performer in {cat_col}, bringing in "
                        f"{share}% of total {metric_label} on its own."
                    )
                elif not bottom_share or share > 10:  # Only mention top if truly dominant (>10%) or sole entry
                    bullets.append(
                        f"'{name}' leads in {cat_col} with {share}% of total {metric_label}."
                    )
        
        if bottom:
            name = bottom.get(cat_col)
            share = bottom_share
            if name is not None and share is not None:
                # Similarly, only flag as "weakest" if it's a real outlier
                if share < 5:  # Bottom performer contributes <5% - worth mentioning
                    bullets.append(
                        f"'{name}' contributes only {share}% of total {metric_label} in {cat_col} - "
                        f"worth a closer look for optimization opportunities."
                    )

    growth = insight_facts.get("growth") or {}
    best_month = growth.get("best_month")
    worst_month = growth.get("worst_month")
    if best_month and worst_month:
        bullets.append(
            f"Business is consistently strongest in {best_month.get('month')} and weakest in "
            f"{worst_month.get('month')} - good months to plan stock and staffing around."
        )
    latest_month = growth.get("latest_month")
    if latest_month and latest_month.get("mom_growth_pct") is not None:
        direction = "up" if latest_month["mom_growth_pct"] >= 0 else "down"
        bullets.append(
            f"The most recent month ({latest_month.get('label')}) is {direction} "
            f"{abs(latest_month['mom_growth_pct'])}% compared to the month before."
        )

    for pair in insight_facts.get("top_correlations", [])[:3]:
        verb = "tend to rise together" if pair.get("direction") == "positive" else "tend to move in opposite directions"
        sample_n = pair.get("n")
        sample_note = f" (seen across {sample_n:,} records)" if sample_n else ""
        bullets.append(
            f"{pair['col1']} and {pair['col2']} {verb}{sample_note} - a change in one is a good early "
            f"warning sign for the other."
        )

    if anomalies.get("unique_flagged_rows") and structural_penalty <= statistical_penalty:
        bullets.append(
            f"About {anomalies.get('unique_flagged_row_pct')}% of your records "
            f"({anomalies.get('unique_flagged_rows')} rows) look unusual compared to the rest - "
            f"these are worth a manual check for data-entry mistakes or one-off events."
        )

    score = quality.get("overall_quality_score")
    if score is not None:
        if score >= 80:
            bullets.append(f"Your data is in good shape (quality score {score}/100) - safe to act on these numbers.")
        else:
            bullets.append(
                f"Your data quality score is {score}/100 - treat these findings as a rough "
                f"guide rather than an exact picture until the underlying data is cleaned up."
            )

    if not bullets:
        bullets.append("Nothing unusual stood out in this dataset - no red flags, no standout winners or losers.")

    # The headline "bottom line" must lead with whichever issue category actually
    # costs the most Data Quality Score points, not a fixed template order - a
    # structural defect that docks 7.5 points is more urgent than 63 statistical
    # outliers that dock 0, even though both produce an "unusual records" bullet
    # above. Rank the two anomaly categories by their actual point-impact.
    if structural_penalty > 0 and structural_penalty >= statistical_penalty and anomalies.get("data_quality_issue_rows"):
        bottom_line = (
            f"Focus first on the {anomalies.get('data_quality_issue_rows')} records with structural data "
            f"issues - they cost {structural_penalty} quality points, more than any other issue, and should "
            f"be resolved before acting on the results."
        )
    elif anomalies.get("unique_flagged_rows"):
        bottom_line = (
            f"Focus first on the {anomalies.get('unique_flagged_rows')} unusual records - "
            f"fixing or explaining those will make every other number in this report more trustworthy."
        )
    elif insight_facts.get("rankings"):
        first_col = next(iter(insight_facts["rankings"]))
        top_row = (insight_facts["rankings"][first_col].get("top") or [None])[0]
        if top_row:
            bottom_line = (
                f"'{top_row.get(first_col)}' is carrying a disproportionate share of your results in "
                f"{first_col} - protecting that relationship matters more than any single new initiative."
            )
        else:
            bottom_line = bullets[0]
    else:
        bottom_line = bullets[0]

    return bullets[:6], bottom_line


def _fallback_narrative(insight_facts: dict) -> dict:
    """Deterministic, LLM-free narrative built directly from the facts. Guarantees the
    agent never fails outright when both LLM providers are unavailable."""
    dataset = insight_facts.get("dataset", {})
    quality = insight_facts.get("data_quality", {})
    validation = insight_facts.get("validation", {})

    executive_summary = (
        f"Dataset with {dataset.get('cleaned_rows')} rows and {dataset.get('cleaned_cols')} columns "
        f"after cleaning, with an overall data quality score of {quality.get('overall_quality_score')}."
    )

    key_findings = []
    for pair in insight_facts.get("top_correlations", []):
        sample_n = pair.get("n")
        sample_note = f", n={sample_n:,}" if sample_n else ""
        key_findings.append(
            f"{pair['col1']} and {pair['col2']} show a {pair['strength']} {pair['direction']} "
            f"correlation (r={pair['pearson_r']}{sample_note})."
        )
    for trend in insight_facts.get("significant_trends", []):
        key_findings.append(
            f"{trend['column']} shows a statistically significant {trend['trend']} trend "
            f"(r²={trend['r_squared']})."
        )
    anomalies = insight_facts.get("anomalies", {})
    if anomalies.get("unique_flagged_rows"):
        key_findings.append(
            f"{anomalies.get('unique_flagged_rows')} rows "
            f"({anomalies.get('unique_flagged_row_pct')}%) were flagged as statistical anomalies."
        )
    if not key_findings:
        key_findings.append("No strong correlations, significant trends, or anomalies were detected.")

    risks_and_caveats = []
    if validation.get("flagged_issue_count"):
        risks_and_caveats.append(
            f"Agent 5 validation flagged {validation.get('flagged_issue_count')} issue(s); "
            f"review before relying on downstream conclusions."
        )
    if quality.get("overall_quality_score") is not None and quality["overall_quality_score"] < 80:
        risks_and_caveats.append(
            f"Data quality score ({quality['overall_quality_score']}) is below 80; "
            f"treat findings as directional rather than precise."
        )

    recommendations = []
    rankings = insight_facts.get("rankings") or {}
    for dimension, data in rankings.items():
        weakest = (data.get("bottom") or [None])[0]
        if weakest and weakest.get(dimension) is not None:
            recommendations.append(
                f"Investigate '{weakest[dimension]}' in {dimension}, the weakest result in the report, "
                f"and test a targeted recovery action."
            )
            break
    anomalies = insight_facts.get("anomalies") or {}
    prioritized = anomalies.get("prioritized_anomalies") or []
    if prioritized:
        first = prioritized[0]
        recommendations.append(
            f"Review {first['column']} first: its flagged records represent about "
            f"{first['business_impact']} in estimated business impact."
        )
    correlations = insight_facts.get("top_correlations") or []
    if correlations:
        pair = correlations[0]
        recommendations.append(f"Investigate the {pair['col1']}-{pair['col2']} relationship in the operating process.")
    recommendations.append("Re-run this pipeline as new data arrives to track whether the findings persist.")
    recommendations = recommendations[:5]

    plain_language_insights, bottom_line = _plain_language_fallback(insight_facts)

    return {
        "executive_summary": executive_summary,
        "key_findings": key_findings,
        "story": _fallback_story(insight_facts),
        "chart_captions": {},
        "glossary_terms": [],
        "plain_language_insights": plain_language_insights,
        "bottom_line": bottom_line,
        "risks_and_caveats": risks_and_caveats,
        "recommendations": recommendations,
        "source": "fallback",
    }


# ── hybrid narrative assembly (deterministic floor + LLM polish) ─────────────

def _fallback_story(insight_facts: dict) -> dict:
    """Three-part deterministic story used when the LLM is unavailable or its
    own story fails validation. Built strictly from extracted facts."""
    quality = insight_facts.get("data_quality") or {}
    anomalies = insight_facts.get("anomalies") or {}
    growth = insight_facts.get("growth") or {}

    what_parts = []
    for cat_col, data in (insight_facts.get("rankings") or {}).items():
        top = (data.get("top") or [None])[0]
        if top and top.get("revenue_share_pct") is not None:
            metric_label = (data.get("metric_label") or "revenue").lower()
            what_parts.append(
                f"'{top.get(cat_col)}' is the strongest {cat_col}, contributing "
                f"{top.get('revenue_share_pct')}% of {metric_label}"
            )
            break
    best_month = growth.get("best_month")
    if best_month and best_month.get("month"):
        what_parts.append(f"{best_month['month']} is the strongest month in the record")
    if anomalies.get("unique_flagged_rows"):
        what_parts.append(
            f"{anomalies['unique_flagged_rows']} records look unusual compared with their normal ranges"
        )
    what_happened = (
        "The analysis found " + "; ".join(what_parts[:3]) + "."
        if what_parts else
        "No single standout pattern emerged from this dataset — performance is fairly evenly spread."
    )

    why_parts = []
    score = quality.get("overall_quality_score")
    if score is not None:
        why_parts.append(
            "the data is solid enough to act on with confidence"
            if score >= 80 else
            f"the data scores {score}/100 for quality, so treat the figures as directional"
        )
    if anomalies.get("data_quality_issue_rows"):
        why_parts.append(
            f"{anomalies['data_quality_issue_rows']} rows carry structural issues worth fixing first"
        )
    why_it_matters = (
        "Because " + "; ".join(why_parts) + "."
        if why_parts else
        "These patterns are mild but consistent across the dataset."
    )

    what_to_do_next = (
        "Start by reviewing the strongest and weakest groups highlighted above, "
        "double-check the flagged unusual records, then revisit these numbers "
        "after any structural issues noted in this report have been fixed."
    )
    return {"what_happened": what_happened, "why_it_matters": why_it_matters,
            "what_to_do_next": what_to_do_next}


def _jargon_hits(text) -> list[str]:
    """Return jargon terms found in `text` (case-insensitive)."""
    if not isinstance(text, str):
        return []
    lowered = text.lower()
    hits = []
    for pattern in _JARGON_PATTERNS:
        match = re.search(pattern, lowered)
        if match:
            hits.append(match.group(0))
    return hits


def _narrative_text_blob(narrative: dict) -> str:
    """Flatten every reader-facing narrative field into one lowercase blob,
    used to decide which glossary terms are actually worth showing."""
    parts = [narrative.get("executive_summary"), narrative.get("bottom_line")]
    parts.extend(narrative.get("key_findings") or [])
    parts.extend(narrative.get("plain_language_insights") or [])
    parts.extend(narrative.get("risks_and_caveats") or [])
    parts.extend(narrative.get("recommendations") or [])
    story = narrative.get("story") or {}
    if isinstance(story, dict):
        parts.extend(story.values())
    captions = narrative.get("chart_captions") or {}
    if isinstance(captions, dict):
        parts.extend(captions.values())
    return " ".join(str(p) for p in parts if isinstance(p, str)).lower()


def _build_dynamic_glossary(narrative: dict) -> dict:
    """Only surface a glossary tooltip for terms that actually appear in the
    final rendered narrative - an always-on static glossary shows definitions
    for words ('skewed', 'link strength'...) that may never occur in a given
    report, which is clutter, not clarity."""
    candidates = {**DEFAULT_GLOSSARY, **EXTENDED_GLOSSARY}
    raw_terms = narrative.get("glossary_terms")
    if isinstance(raw_terms, dict):
        candidates.update(raw_terms)
    elif isinstance(raw_terms, list):
        for entry in raw_terms:
            if isinstance(entry, dict) and entry.get("term") and entry.get("plain_explanation"):
                candidates[str(entry["term"]).strip()] = str(entry["plain_explanation"]).strip()

    text = _narrative_text_blob(narrative)
    matched = {term: definition for term, definition in candidates.items() if term.lower() in text}
    return dict(list(matched.items())[:12])


def _valid_story(story) -> dict | None:
    """Accept an LLM story only when all three parts are usable strings."""
    if not isinstance(story, dict):
        return None
    cleaned = {}
    for key in ("what_happened", "why_it_matters", "what_to_do_next"):
        value = story.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 900:
            return None
        cleaned[key] = value.strip()
    return cleaned


def _compose_hybrid_narrative(llm_narrative: dict, deterministic: dict, facts: dict) -> dict:
    """Deterministic-first composition.

    The guaranteed plain-language floor (bullets, bottom line, story skeleton)
    ALWAYS renders; the LLM's contribution is layered on top where it passes
    basic hygiene checks. This is what makes the report safe to ship even on a
    day the LLM returns nonsense.
    """
    known_chart_ids = {c.get("id") for c in facts.get("charts", [])}

    # Start from the LLM output but never inherit empty/missing sections.
    merged = {}
    for key, value in llm_narrative.items():
        if value not in (None, "", [], {}):
            merged[key] = value

    # 1 — plain-language bullets: deterministic first, deduped LLM extras after.
    det_bullets = [b for b in (deterministic.get("plain_language_insights") or [])]
    seen = {" ".join(str(b).lower().split()) for b in det_bullets}
    extras = []
    for bullet in llm_narrative.get("plain_language_insights") or []:
        if not isinstance(bullet, str):
            continue
        normalized = " ".join(bullet.lower().split())
        if normalized and normalized not in seen:
            seen.add(normalized)
            extras.append(bullet.strip())
    merged["plain_language_insights"] = (det_bullets + extras[:4]) or det_bullets

    # 2 — bottom line & story: LLM version wins only when jargon-free.
    if _jargon_hits(merged.get("bottom_line")):
        merged["bottom_line"] = deterministic.get("bottom_line", "")
    llm_story = _valid_story(llm_narrative.get("story"))
    if llm_story is None or any(_jargon_hits(v) for v in llm_story.values()):
        merged["story"] = _fallback_story(facts)
    else:
        merged["story"] = llm_story

    # 3 — captions: only for real chart ids, only jargon-free ones.
    captions = {}
    raw_captions = llm_narrative.get("chart_captions")
    if isinstance(raw_captions, dict):
        for cid, caption in raw_captions.items():
            if cid in known_chart_ids and isinstance(caption, str) \
                    and caption.strip() and not _jargon_hits(caption):
                captions[cid] = caption.strip()
    merged["chart_captions"] = dict(list(captions.items())[:MAX_CHART_CAPTIONS_FROM_LLM])

    # 4 — glossary: raw LLM terms pass through as-is; final filtering down to
    # only the terms that actually appear in the rendered text happens once
    # per-request in _build_dynamic_glossary, after linting/grounding settle.
    merged["glossary_terms"] = llm_narrative.get("glossary_terms") or []
    return merged


def _lint_plain_language(merged: dict, deterministic: dict) -> int:
    """Final safety net: swap any remaining jargon-laden bullet/line back to
    deterministic wording. Returns the number of replacements made."""
    swaps = [b for b in (deterministic.get("plain_language_insights") or [])
             if not _jargon_hits(b)]
    used: set[str] = set()
    clean = []
    replaced = 0
    for bullet in merged.get("plain_language_insights") or []:
        if not _jargon_hits(bullet):
            clean.append(bullet)
            continue
        replacement = next((s for s in swaps
                            if s.lower() not in {c.lower() for c in clean}
                            and s.lower() not in used), None)
        if replacement:
            used.add(replacement.lower())
            clean.append(replacement)
            replaced += 1
    merged["plain_language_insights"] = clean
    if _jargon_hits(merged.get("bottom_line")) and deterministic.get("bottom_line"):
        merged["bottom_line"] = deterministic["bottom_line"]
        replaced += 1
    return replaced


def _ground_recommendations(insight_facts, narrative):
    """Keep model recommendations tied to at least one reported finding."""
    fallback = _fallback_narrative(insight_facts).get("recommendations", [])
    anchors = set()
    for dimension, data in (insight_facts.get("rankings") or {}).items():
        weakest = (data.get("bottom") or [None])[0]
        if weakest and weakest.get(dimension) is not None:
            anchors.add(str(weakest[dimension]).casefold())
    for item in (insight_facts.get("anomalies") or {}).get("prioritized_anomalies", []):
        if item.get("column"):
            anchors.add(str(item["column"]).casefold())
    for pair in insight_facts.get("top_correlations") or []:
        anchors.update(str(pair.get(key)).casefold() for key in ("col1", "col2") if pair.get(key))

    anomaly_impacts = {
        round(float(item["business_impact"]), 2)
        for item in (insight_facts.get("anomalies") or {}).get("prioritized_anomalies", [])
        if item.get("business_impact") is not None
    }

    def _recommendation_is_traceable(recommendation):
        text = str(recommendation)
        numeric_claims = _extract_numeric_claims(text)
        mentions_money = "$" in text or any(word in text.casefold() for word in ("impact", "revenue", "cost"))
        if not mentions_money or not numeric_claims:
            return True
        return any(
            any(abs(claim - impact) <= max(CLAIM_GROUNDING_TOLERANCE, abs(impact) * 0.05)
                for impact in anomaly_impacts)
            for claim in numeric_claims
        )

    grounded = [
        recommendation for recommendation in (narrative.get("recommendations", []) or [])
        if any(anchor in str(recommendation).casefold() for anchor in anchors)
        and _recommendation_is_traceable(recommendation)
    ]
    for recommendation in fallback:
        if len(grounded) >= 5:
            break
        if recommendation not in grounded:
            grounded.append(recommendation)
    return grounded[:5]


# ─────────────────────────────────────────────────────────────────────────────
# 3 — RENDERING (Jinja2 -> HTML -> WeasyPrint PDF)
# ─────────────────────────────────────────────────────────────────────────────

def _embed_png(path: Path, max_size=(1400, 900)) -> str | None:
    """Read a PNG and return a base64 data URI (single-file portability)."""
    try:
        from PIL import Image
        with Image.open(path) as image:
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
            compressed = BytesIO()
            image.convert("RGB").save(compressed, format="PNG", optimize=True, compress_level=9)
        return f"data:image/png;base64,{base64.b64encode(compressed.getvalue()).decode('ascii')}"
    except OSError:
        return None


def _charts_output_dir(state) -> Path:
    """Per-run charts directory (falls back to the shared legacy dir)."""
    run_id = str(state.get("run_id") or "").strip()
    base = Path("outputs/charts")
    return base / run_id if run_id else base


def _build_chart_view_models(state, narrative: dict) -> list[dict]:
    """Unified gallery entries consumed by the template.

    Every entry carries BOTH render targets:
      * `option_json` — ECharts option for the interactive screen view
      * `img_b64`     — static PNG twin for print/PDF/<noscript>

    Legacy agent_4 PNG-only families arrive as render="image" specs; planner
    specs get their static twin rendered on demand here.
    
    Deduplicates charts by ID to prevent the same chart from appearing multiple times.
    """
    captions = narrative.get("chart_captions") or {}
    out_dir = _charts_output_dir(state)
    out_dir.mkdir(parents=True, exist_ok=True)

    view_models = []
    seen_ids = set()  # Track chart IDs to avoid duplicates
    
    for spec in state.get("chart_specs") or []:
        if not isinstance(spec, dict):
            continue
        
        chart_id = spec.get("id", "chart")
        
        # Skip if we've already included this chart ID
        if chart_id in seen_ids:
            print(f"[Agent 6] Skipping duplicate chart: {chart_id}")
            continue
        seen_ids.add(chart_id)
        
        png_path = spec.get("png_path")
        if not png_path:
            # Render the static twin lazily so print/PDF stays complete even
            # when only the interactive path was planned up front.
            png_path = render_spec_png(spec, str(out_dir))
        img_b64 = _embed_png(Path(png_path)) if png_path else None

        entry = {
            "id": chart_id,
            "title": spec.get("title", ""),
            "subtitle": spec.get("subtitle", ""),
            "why_it_matters": spec.get("why_it_matters", ""),
            "plain_summary": spec.get("plain_summary", ""),
            "descriptive": spec.get("descriptive", ""),
            "diagnostic": spec.get("diagnostic", ""),
            "llm_caption": captions.get(chart_id, ""),
            "alt_text": spec.get("alt_text") or spec.get("title", ""),
            "section": spec.get("section", "what_matters"),
            "priority": spec.get("priority") or 0.0,
            "render": spec.get("render", "image"),
            "annotations": spec.get("annotations") or [],
            "option_json": "",
            "img_b64": img_b64 or "",
        }
        if spec.get("render") == "echarts":
            try:
                entry["option_json"] = echarts_option_json(spec)
            except Exception:  # noqa: BLE001 — degrade to static image
                entry["render"] = "image"
        view_models.append(entry)
    return view_models


def _group_by_section(chart_entries: list[dict]) -> list[tuple[str, list[dict]]]:
    """Order sections by the combined signal strength of the charts placed in them,
    so a dataset dominated by (say) trends leads with "Direction of travel" instead of
    always opening with "What matters most" regardless of what's actually strongest."""
    order = ["what_matters", "shape", "direction", "relationships", "watchlist"]
    headings = {
        "what_matters": ("What matters most", "The groups and items that carry the business."),
        "shape": ("The shape of your numbers", "How values spread out, and what typical really means."),
        "direction": ("Direction of travel", "Trends over time and repeating rhythms."),
        "relationships": ("How things connect", "Where two measures move together."),
        "watchlist": ("Worth double-checking", "Unusual records and risk pockets to review."),
    }
    sections = []
    for position, section in enumerate(order):
        items = [c for c in chart_entries if c["section"] == section]
        if not items:
            continue
        items.sort(key=lambda c: c.get("priority") or 0.0, reverse=True)
        signal = sum(c.get("priority") or 0.0 for c in items)
        title, blurb = headings.get(section, (section.replace("_", " ").title(), ""))
        sections.append((signal, position, section, {"heading": title, "blurb": blurb, "charts": items}))
    sections.sort(key=lambda entry: (-entry[0], entry[1]))
    return [(section, payload) for _, _, section, payload in sections]


def _quality_verdict(score):
    """Translate a numeric quality score into a plain-language verdict.

    Returns {"label": ..., "cls": good|warn|bad} so templates can show a
    human word instead of a bare number."""
    if score is None:
        return None
    try:
        value = float(score)
    except (TypeError, ValueError):
        return None
    if value >= 85:
        return {"label": "Excellent", "cls": "good"}
    if value >= 70:
        return {"label": "Good", "cls": "good"}
    if value >= 50:
        return {"label": "Fair — some cleaning helped", "cls": "warn"}
    return {"label": "Needs attention", "cls": "bad"}


def _kpi_cards(facts: dict) -> list[dict]:
    """Hero strip values, all grounded in extracted facts."""
    dataset = facts.get("dataset") or {}
    quality = facts.get("data_quality") or {}
    validation = facts.get("validation") or {}
    reliability = facts.get("reliability") or {}
    cards = [
        {"label": "Rows analysed",
         "value": humanize_number(dataset.get("raw_rows")),
         "hint": "Each row is one record — e.g. one sale, order or entry"},
        {"label": "Columns",
         "value": humanize_number(dataset.get("raw_cols")),
         "hint": "Details recorded for every record"},
    ]
    score = quality.get("overall_quality_score")
    if score is not None:
        verdict = _quality_verdict(score)
        cards.append({"label": "Data health",
                      "value": f"{humanize_pct(score)}".rstrip("%") + "/100",
                      "hint": f"{verdict['label']} — how complete and consistent the data is"})
    v_score = validation.get("overall_validation_score")
    if v_score is not None:
        cards.append({"label": "Validation",
                      "value": ("Pass · " if validation.get("passed") else "Fail · ")
                               + f"{humanize_pct(v_score)}".rstrip("%") + "/100",
                      "hint": "An independent re-check of the analysis steps"})
    readiness = reliability.get("decision_readiness")
    if readiness:
        cards.append({"label": "Decision readiness",
                      "value": str(readiness).replace("_", " "),
                      "hint": "How safely you can act on these findings"})
    return cards


def _dataset_intro(facts: dict) -> list[str]:
    """Friendly 'what's in your data' sentences for non-technical readers,
    built strictly from extracted pipeline facts."""
    dataset = facts.get("dataset") or {}
    quality = facts.get("data_quality") or {}
    lines = []
    rows = dataset.get("raw_rows")
    cols = dataset.get("raw_cols")
    if rows is not None and cols is not None:
        try:
            is_one_row = int(rows) == 1
        except (TypeError, ValueError):
            is_one_row = False
        lines.append(
            f"Your file contains <strong>{humanize_number(rows)}</strong> record{'' if is_one_row else 's'} "
            f"with <strong>{humanize_number(cols)}</strong> pieces of information each."
        )
    removed = quality.get("duplicates_removed")
    dup_rate = quality.get("duplicate_rate_pct")
    if removed:
        rate = f" ({dup_rate}% of rows)" if dup_rate else ""
        lines.append(
            f"We found and removed <strong>{humanize_number(removed)}</strong> duplicate record{'' if removed == 1 else 's'}{rate}, "
            f"so nothing is counted twice."
        )
    missing_raw = quality.get("raw_missing_pct")
    missing_left = quality.get("remaining_null_pct")
    if missing_raw is not None and missing_raw > 0:
        msg = f"Some cells were empty ({float(missing_raw):g}% of the file); the pipeline filled them using standard rules"
        if missing_left is not None and missing_left > 0:
            msg += f", and {float(missing_left):g}% remain unfilled where filling would distort the data"
        lines.append(msg + ".")
    elif missing_raw == 0:
        lines.append("No empty cells were found — the file is complete.")
    raw_rows = dataset.get("raw_rows")
    cleaned_rows = dataset.get("cleaned_rows")
    if raw_rows is not None and cleaned_rows is not None and cleaned_rows != raw_rows:
        diff = raw_rows - cleaned_rows
        if diff > 0:
            lines.append(
                f"After cleanup, <strong>{humanize_number(cleaned_rows)}</strong> records remain for analysis "
                f"(the other {humanize_number(diff)} were exact duplicates or unusable rows)."
            )
        else:
            lines.append(
                f"Analysis-ready data has <strong>{humanize_number(cleaned_rows)}</strong> records "
                "(extra columns such as calculated metrics are added by the pipeline)."
            )
    return lines


def _narrative_provenance(narrative: dict) -> dict:
    """Reader-facing summary of HOW the prose in this report was produced.

    The report is always a hybrid: every number, table and chart read-out
    ("What it shows" / "Why it looks this way") is computed deterministically
    from the dataset. This only describes the *narrative* layer — executive
    summary, key findings, recommendations, and the optional per-chart captions —
    which is either drafted by an LLM (and then grounded against the computed
    facts) or, when no model is reachable, assembled from fixed templates.
    """
    narrative = narrative or {}
    source = narrative.get("source") or "fallback"
    raw_reason = str(narrative.get("fallback_reason") or "").strip()
    # Provider failures arrive as a full exception dump (nested JSON, both
    # providers' errors). Keep just the human-readable head so the report stays
    # legible: everything up to the first embedded JSON / dict, capped.
    short_reason = re.split(r"\s*[-–—]\s*\{|\s*\{['\"]|\n", raw_reason, maxsplit=1)[0].strip()
    if len(short_reason) > 200:
        short_reason = short_reason[:197].rstrip() + "…"
    grounding = narrative.get("claims_grounding") or {}
    captions = narrative.get("chart_captions") or {}
    engines = {
        "groq": f"Groq · {GROQ_MODEL}",
        "gemini": "Google Gemini",
        "fallback": "deterministic templates (no LLM)",
    }
    is_llm = source in ("groq", "gemini")
    engine = engines.get(source, source)
    return {
        "source": source,
        "is_llm": is_llm,
        "label": "AI-assisted narrative" if is_llm else "Rule-based narrative",
        "engine": engine,
        "fallback_reason": short_reason or None,
        "llm_chart_captions": len(captions),
        "claims_checked": grounding.get("claims_checked") or 0,
        "claims_grounded": grounding.get("claims_grounded") or 0,
        "claims_flagged": bool(grounding.get("claims_flagged")),
        "detail": (
            f"The executive summary, key findings and recommendations were drafted by "
            f"{engine} from the pipeline's computed facts, then checked back against "
            f"those facts. Every figure, table and chart read-out in this report is "
            f"computed deterministically, not written by the model."
            if is_llm else
            "No language model was reachable, so the executive summary, key findings "
            "and recommendations were assembled from fixed templates over the "
            "pipeline's computed facts. Every figure, table and chart read-out is "
            "computed deterministically."
        ),
    }


def _render_html(insight_facts, narrative, chart_paths, state):
    """Render the report. Signature kept compatible with existing tests:
    legacy `chart_paths` PNGs are still embedded as base64 images."""
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)
    env.filters.update({
        "humnum": humanize_number,
        "humpct": humanize_pct,
        "humcur": lambda v, symbol="": humanize_currency(v, symbol),
        "humratio": humanize_ratio,
        "titleize": titleize,
        "abbr_glossary": _glossary_abbr,
    })

    # Legacy PNG paths -> image entries. This is ONLY a backwards-compat path for
    # tests/CLI runs where state["chart_specs"] was never populated. In the live
    # pipeline, agent_4 already wraps every kept legacy candidate into chart_specs
    # (chart_spec.wrap_legacy_candidate) and caps/dedupes them via finalize_specs —
    # chart_paths is the pre-cap, pre-dedup candidate list, so replaying it here
    # whenever chart_specs exists just re-adds charts the cap/dedup intentionally
    # dropped, all mis-filed into "what_matters" with a crude filename-derived
    # title. Skip entirely once the unified gallery has anything to show.
    legacy_entries = []
    if not state.get("chart_specs"):
        for p in (chart_paths or []):
            path = Path(p)
            if not path.exists():
                continue
            data_uri = _embed_png(path)
            if not data_uri:
                continue
            legacy_entries.append({
                "id": f"legacy_{path.stem}",
                "title": path.stem.replace("_", " ").title(),
                "subtitle": "", "why_it_matters": "", "plain_summary": "",
                "descriptive": "", "diagnostic": "",
                "llm_caption": "", "alt_text": path.stem.replace("_", " "),
                "section": "what_matters",
                "render": "image", "annotations": [],
                "option_json": "", "img_b64": data_uri,
            })

    # Non-JSON-native values (pd.Timestamp, numpy scalars, etc.) can end up in
    # facts/example_rows; fall back to str() instead of letting |tojson raise.
    env.policies["json.dumps_kwargs"] = {"default": str}

    entries = _build_chart_view_models(state, narrative) + legacy_entries
    echarts_lib = ""
    if ECHARTS_LIB_PATH.exists():
        echarts_lib = ECHARTS_LIB_PATH.read_text(encoding="utf-8", errors="replace")

    template = env.get_template(TEMPLATE_NAME)
    quality = (insight_facts.get("data_quality") or {}).get("overall_quality_score")
    return template.render(
        facts=insight_facts,
        narrative=narrative,
        story=narrative.get("story") or {},
        glossary=narrative.get("glossary_terms") or {},
        kpis=_kpi_cards(insight_facts),
        dataset_intro=_dataset_intro(insight_facts),
        quality_verdict=_quality_verdict(quality),
        chart_sections=_group_by_section(entries),
        narrative_provenance=_narrative_provenance(narrative),
        has_interactive=bool(echarts_lib),
        echarts_lib=echarts_lib,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        # Prefer the name the user actually uploaded — csv_path is the server-side
        # "<job_id>.csv" storage path once a job is created (see analysis.py), so
        # deriving the display name from it shows a UUID-looking filename instead.
        dataset_name=state.get("original_filename") or Path(state.get("csv_path", "dataset")).name,
    )


def _glossary_abbr(text, glossary):
    """Wrap known technical terms in <abbr> tooltips (Jinja filter).

    Escapes everything itself and returns Markup, so templates use it as
    `{{ text | abbr_glossary(glossary) }}` even under autoescape — no unsafe
    raw-HTML passthrough of LLM-generated prose.
    """
    from markupsafe import Markup, escape
    if not isinstance(text, str) or not text or not glossary:
        return text
    result = escape(text)
    for term, explanation in glossary.items():
        pattern = re.compile(re.escape(str(term)), re.IGNORECASE)
        match = pattern.search(str(result))
        if not match:
            continue
        matched = str(escape(match.group(0)))
        tooltip = str(escape(explanation))
        abbr = Markup(f'<abbr class="glossary" title="{tooltip}">{matched}</abbr>')
        result = Markup(pattern.sub(lambda _m: str(abbr), str(result), count=1))
    return result


def _write_report(html_string, reports_dir, errors, run_id: str | None = None):
    """Always write the HTML file; best-effort convert to PDF. Returns the report path
    (PDF if conversion succeeded, otherwise the HTML fallback) plus a pdf_written flag.

    When `run_id` is present the report is written to `<reports_dir>/<run_id>/`
    so concurrent pipeline runs never overwrite each other's documents. Legacy
    callers (no run_id) keep the historical flat filename."""
    output_dir = Path(reports_dir) / str(run_id) if run_id else Path(reports_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    html_path = output_dir / "insight_report.html"
    if html_path.exists():
        html_path.unlink()
    html_path.write_text(html_string, encoding="utf-8")

    pdf_path = output_dir / "insight_report.pdf"
    try:
        from weasyprint import HTML
    except Exception as import_error:
        errors.append(f"Agent6: PDF conversion failed, falling back to HTML report: {import_error}")
        return str(html_path), False

    try:
        from weasyprint import WeasyPrintUnavailableError
    except ImportError:
        WeasyPrintUnavailableError = None

    try:
        if pdf_path.exists():
            pdf_path.unlink()
        HTML(string=html_string, base_url=str(output_dir)).write_pdf(str(pdf_path))
        return str(pdf_path), True
    except Exception as pdf_error:
        if (
            WeasyPrintUnavailableError is not None
            and isinstance(pdf_error, WeasyPrintUnavailableError)
        ):
            return str(html_path), False
        errors.append(f"Agent6: PDF conversion failed, falling back to HTML report: {pdf_error}")
        return str(html_path), False


def _validate_raw_column_count(insight_facts: dict, raw_shape: dict | None) -> None:
    """Guard against the executive summary silently reporting a post-transform column
    count as if it were the raw dataset's shape. `raw_shape` is captured once by Agent 1
    immediately on ingestion (see agent_1.agent1_structural_profiler) and must never be
    re-derived downstream; `insight_facts["dataset"]["raw_cols"]` should always agree
    with it. Raises AssertionError on mismatch so this class of bug is caught in tests
    (or here, best-effort) instead of only surfacing when someone manually diffs the
    report against the source file.
    """
    expected = (raw_shape or {}).get("cols")
    actual = (insight_facts.get("dataset") or {}).get("raw_cols")
    if expected is None or actual is None:
        return
    assert actual == expected, (
        f"Executive summary is reporting raw column count as {actual} but Agent 1's "
        f"raw_shape captured {expected} columns at ingestion — a downstream step is "
        f"overwriting the raw shape with a post-transform column count."
    )


# ─────────────────────────────────────────────────────────────────────────────
# TABLE CELL POPULATION GUARANTEE
# ─────────────────────────────────────────────────────────────────────────────
# Generic post-generation validation over every report table: no required
# field may be None/blank in any row. Declared once per table shape here (not
# per dataset) - every table in insight_report.html.jinja backed by a list of
# dicts is covered so a silently-empty cell fails loudly instead of shipping.
_REQUIRED_TABLE_FIELDS = {
    "top_correlations": ("col1", "col2", "pearson_r", "strength", "direction"),
    "formulaic_pairs": ("col1", "col2", "pearson_r", "strength", "direction"),
    "significant_trends": ("column", "trend", "r_squared", "p_value"),
    "category_normalization": ("column", "raw", "canonical", "row_count"),
}


def _validate_no_empty_required_cells(insight_facts: dict) -> None:
    """Fail loudly (AssertionError naming the table/column) if any required
    table cell would render empty, rather than silently shipping a report
    with gaps. Optional columns (anything not listed here, or fields that are
    legitimately allowed to be absent, e.g. review-only example rows) are not
    checked."""
    problems = []

    for table_name, required_fields in _REQUIRED_TABLE_FIELDS.items():
        rows = insight_facts.get(table_name) or []
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            for field in required_fields:
                value = row.get(field)
                if value is None or (isinstance(value, str) and not value.strip()):
                    problems.append(f"{table_name}[{i}].{field}")

    dqd = insight_facts.get("data_quality_detail") or {}
    for i, row in enumerate(dqd.get("missing_values") or []):
        for field in ("column", "missing_count", "missing_pct", "action"):
            if row.get(field) is None or (isinstance(row.get(field), str) and not row.get(field).strip()):
                problems.append(f"data_quality_detail.missing_values[{i}].{field}")

    for section_name, value_field, share_field in (
        ("rankings", "total_revenue", "revenue_share_pct"),
        ("profit_breakdown", "total_profit", "profit_share_pct"),
    ):
        section = insight_facts.get(section_name) or {}
        for cat_col, data in section.items():
            for label in ("top", "bottom"):
                for i, row in enumerate(data.get(label) or []):
                    for field in (cat_col, value_field, share_field):
                        if row.get(field) is None:
                            problems.append(f"{section_name}.{cat_col}.{label}[{i}].{field}")

    if problems:
        raise AssertionError(f"Report table(s) have empty required cell(s): {problems}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN AGENT FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def agent6_insight_report_generator(state: GraphState) -> GraphState:
    errors = state.get("errors", [])
    cleaned_df = state.get("cleaned_df")
    stats = state.get("stats")
    validation_report = state.get("validation_report")

    if cleaned_df is None or not stats or not validation_report:
        errors.append("Agent6: Missing cleaned_df, stats, or validation_report. Upstream agent failed.")
        return {**state, "errors": errors}

    verbose = _verbose_logging_enabled()
    print("[Agent 6] Starting insight report generation")

    insight_facts = _extract_insight_facts(state)
    try:
        _validate_raw_column_count(insight_facts, state.get("raw_shape"))
    except AssertionError as shape_error:
        errors.append(f"Agent6: {shape_error}")

    try:
        _validate_no_empty_required_cells(insight_facts)
    except AssertionError as table_error:
        errors.append(f"Agent6: {table_error}")

    narrative_source = "llm"
    narrative_fallback_reason = None
    try:
        narrative = _call_llm_for_narrative(insight_facts)
    except Exception as llm_error:
        print(f"[Agent 6] LLM narrative generation failed, using deterministic fallback: {llm_error}")
        narrative = _fallback_narrative(insight_facts)
        narrative_source = "fallback"
        narrative_fallback_reason = str(llm_error)

    # Hybrid composition: the deterministic narrative is ALWAYS computed and
    # forms the guaranteed floor; the LLM output (when it arrived) is layered
    # on top where it passes hygiene checks (story validity, jargon, ids).
    deterministic = _fallback_narrative(insight_facts)
    if narrative_source == "llm":
        try:
            narrative = _compose_hybrid_narrative(narrative, deterministic, insight_facts)
            # Preserve the actual provider tag ("groq"/"gemini") set by
            # _call_llm_for_narrative instead of hardcoding one provider.
        except Exception as compose_error:
            print(f"[Agent 6] Hybrid composition failed, using deterministic floor: {compose_error}")
            narrative = deterministic
            narrative_source = "fallback"
    else:
        narrative = deterministic
    if narrative_fallback_reason:
        narrative["fallback_reason"] = narrative_fallback_reason
    lint_replacements = _lint_plain_language(narrative, deterministic)
    if lint_replacements:
        print(f"[Agent 6] Jargon linter replaced {lint_replacements} plain-language line(s)")

    narrative["recommendations"] = _ground_recommendations(insight_facts, narrative)
    narrative["glossary_terms"] = _build_dynamic_glossary(narrative)

    claims_grounding = _check_narrative_grounding(insight_facts, narrative)
    narrative["claims_grounding"] = claims_grounding
    if claims_grounding["claims_flagged"]:
        print(
            f"[Agent 6] Claim grounding: {claims_grounding['claims_grounded']}/{claims_grounding['claims_checked']} "
            f"checked claims matched computed facts; flagged={claims_grounding['flagged_examples']}"
        )
    
    # Check for internal contradictions in the narrative
    contradictions = _check_narrative_contradictions(narrative)
    narrative["contradictions"] = contradictions
    if contradictions["contradictions_found"]:
        print(
            f"[Agent 6] WARNING: {contradictions['contradiction_count']} contradictory statement(s) detected in narrative. "
            f"Review data quality claims for consistency."
        )

    chart_paths = state.get("chart_paths", []) or []
    html_string = _render_html(insight_facts, narrative, chart_paths, state)
    report_path, pdf_written = _write_report(
        html_string, REPORTS_DIR, errors, run_id=state.get("run_id")
    )

    if verbose:
        print(f"[Agent 6]   narrative_source={narrative.get('source', narrative_source)}")
        print(f"[Agent 6]   key_findings={len(narrative.get('key_findings', []))}")

    print(f"[Agent 6] Completed: report={report_path} pdf_written={pdf_written}")

    # Confidence reflects NARRATIVE quality only: whether the story came from
    # the grounded LLM pass or the deterministic fallback. PDF availability is
    # environmental (missing native libs on some machines), not a data-quality
    # signal, so it no longer docks points — it stays in the evidence trail.
    if narrative.get("source", narrative_source) == "fallback":
        confidence = 0.55
    else:
        confidence = 0.95

    # A narrative that cites numbers absent from the computed facts is less
    # trustworthy even if it read grammatically fine.
    grounding_confidence = claims_grounding.get("confidence", 1.0)
    confidence = round(confidence * (0.7 + 0.3 * grounding_confidence), 3)

    ready = (
        narrative.get("source", narrative_source) != "fallback"
        and not claims_grounding.get("claims_flagged")
    )
    state_with_reliability = update_reliability(
        state,
        "agent6",
        confidence,
        evidence=[
            f"narrative_source={narrative.get('source', narrative_source)}",
            f"pdf_written={pdf_written}",
            f"report_path={report_path}",
            f"claims_grounded={claims_grounding['claims_grounded']}/{claims_grounding['claims_checked']}",
        ],
        decision_readiness="ready" if ready else "needs_review",
    )

    return {
        **state_with_reliability,
        "insight_facts": insight_facts,
        "insight_narrative": narrative,
        "report_path": report_path,
        "errors": errors,
    }
