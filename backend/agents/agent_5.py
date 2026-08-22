"""Agent 5: Output Validation & Trust Agent.

Validates the outputs produced by Agents 1-4 before they reach reporting.
Two tiers of checks are run:

  Tier 1 - Deterministic contract/statistical checks (always run, no LLM cost).
           These catch pipeline bugs: row/column loss, out-of-range stats,
           broken chart artifacts, and business-rule violations already
           surfaced by Agent 3's column ledger.

  Tier 2 - Cohen's kappa agreement between Agent 2's LLM-assigned
           `intended_type` and the pure-Python heuristic type sniffer
           (`_infer_intended_types`). This gives an objective, ground-truth-
           free trust signal for the LLM's semantic tagging: low agreement
           means the LLM overrode the mechanical signal often and the schema
           should be reviewed.

SelfCheckGPT-style resampling and ROUGE-L/Bradley-Terry ranking are reserved
for a future Agent 6 (narrative report generation) once there is actual
free-form LLM prose to validate against a reference or rank candidates of.
"""

import math
import os
from pathlib import Path
from collections import Counter

from agents.agent_1 import GraphState
from agents.agent_2 import _infer_intended_types
from main import update_reliability


INTENDED_TYPE_TO_COARSE = {
    "float": "numeric",
    "int": "numeric",
    "datetime": "datetime",
    "boolean": "boolean",
    "string": "string",
    "category": "string",
}

HEURISTIC_TYPE_TO_COARSE = {
    "numeric": "numeric",
    "datetime": "datetime",
    "boolean": "boolean",
    "string": "string",
    "unknown": "unknown",
}

MIN_ACCEPTABLE_KAPPA = 0.4       # "fair" agreement or better (Landis & Koch)
MAX_VALIDATION_FAIL_PCT = 15.0   # business-rule failure tolerance
MIN_TREND_SAMPLE_SIZE = 10       # trends below this many points aren't trustworthy even if p < 0.05


def _validation_confidence(validation_score, review_required=False, insufficient_trends=None):
    """Estimate confidence in validation decisions separately from their score."""
    confidence = max(0.0, min(1.0, float(validation_score) / 100.0))
    if review_required:
        confidence *= 0.5
    confidence -= min(0.25, 0.05 * len(insufficient_trends or []))
    return round(max(0.0, confidence), 3)


def _verbose_logging_enabled():
    val = os.getenv("PIPELINE_VERBOSE", "0").strip().lower()
    return val in {"1", "true", "yes", "on"}


def _cohen_kappa_score(rater_a: list[str], rater_b: list[str]) -> float:
    """Pure-Python Cohen's kappa so the validator does not depend on sklearn."""
    if len(rater_a) != len(rater_b):
        raise ValueError("Raters must have the same number of labels")
    if not rater_a:
        return 1.0

    n = len(rater_a)
    observed = sum(a == b for a, b in zip(rater_a, rater_b)) / n
    counts_a = Counter(rater_a)
    counts_b = Counter(rater_b)
    expected = sum((counts_a[label] / n) * (counts_b[label] / n) for label in set(counts_a) | set(counts_b))

    if expected >= 1.0:
        return 1.0
    return (observed - expected) / (1.0 - expected)


class ValidationLedger:
    """Tracks pass/warn/fail status for every Agent 5 check."""

    def __init__(self):
        self.checks = {}   # check_name -> {"status": "pass"|"warn"|"fail", "detail": str}
        self.issues = []    # list of {"check", "severity", "detail"} for failed/warned checks

    def record(self, name, passed, detail="", severity="error"):
        if passed:
            status = "pass"
        else:
            status = "warn" if severity == "warning" else "fail"
        self.checks[name] = {"status": status, "detail": detail}
        if not passed:
            self.issues.append({"check": name, "severity": severity, "detail": detail})


# ─────────────────────────────────────────────────────────────────────────────
# TIER 1 — deterministic contract checks
# ─────────────────────────────────────────────────────────────────────────────

def _check_row_column_reconciliation(state, ledger):
    """Cross-check Agent 3's row_accounting ledger against the actual cleaned_df shape."""
    column_ledger = state.get("column_ledger", {}) or {}
    row_accounting = column_ledger.get("row_accounting", {}) if isinstance(column_ledger, dict) else {}
    cleaned_df = state.get("cleaned_df")

    if not row_accounting or cleaned_df is None:
        ledger.record("row_reconciliation", False, "missing row_accounting or cleaned_df", severity="warning")
        return

    expected_final = row_accounting.get("final_rows")
    actual_final = int(len(cleaned_df))
    ok = expected_final is None or expected_final == actual_final
    ledger.record(
        "row_reconciliation", ok,
        f"row_accounting.final_rows={expected_final}, cleaned_df rows={actual_final}",
    )


def _check_schema_dataframe_consistency(state, ledger):
    """Every non-dropped schema_blueprint column must exist in cleaned_df."""
    schema_blueprint = state.get("schema_blueprint", {}) or {}
    cleaned_df = state.get("cleaned_df")

    if cleaned_df is None:
        ledger.record("schema_dataframe_consistency", False, "cleaned_df missing", severity="error")
        return

    df_cols = set(cleaned_df.columns)
    missing_from_df = []
    for col, meta in schema_blueprint.items():
        if col == "__metadata__" or not isinstance(meta, dict):
            continue
        if meta.get("dropped_by_imputation"):
            continue
        if col not in df_cols:
            missing_from_df.append(col)

    ok = len(missing_from_df) == 0
    ledger.record(
        "schema_dataframe_consistency", ok,
        f"{len(missing_from_df)} schema columns missing from cleaned_df: {missing_from_df[:10]}",
    )


def _check_quality_score_bounds(state, ledger):
    data_quality = state.get("data_quality", {}) or {}
    score = data_quality.get("overall_quality_score")
    ok = isinstance(score, (int, float)) and 0.0 <= score <= 100.0
    ledger.record("quality_score_bounds", ok, f"overall_quality_score={score}")


def _check_stats_numeric_sanity(state, ledger):
    """Descriptive stats must be finite; correlation coefficients must be in [-1, 1]."""
    stats = state.get("stats", {}) or {}
    descriptive = stats.get("descriptive", {}) or {}

    bad_fields = []
    for col, metrics in descriptive.items():
        if not isinstance(metrics, dict):
            continue
        for key, value in metrics.items():
            if isinstance(value, (int, float)) and (math.isnan(value) or math.isinf(value)):
                bad_fields.append(f"{col}.{key}")

    pearson = (stats.get("correlation", {}) or {}).get("pearson", {}) or {}
    out_of_range = []
    for col1, row in pearson.items():
        if not isinstance(row, dict):
            continue
        for col2, value in row.items():
            if isinstance(value, (int, float)) and not math.isnan(value) and not (-1.0001 <= value <= 1.0001):
                out_of_range.append(f"{col1}~{col2}={value}")

    ok = not bad_fields and not out_of_range
    ledger.record(
        "stats_numeric_sanity", ok,
        f"nan_or_inf_fields={bad_fields[:5]}, out_of_range_correlations={out_of_range[:5]}",
    )


def _check_chart_artifact_integrity(state, ledger):
    """Every path in chart_paths must exist on disk and be non-empty."""
    chart_paths = state.get("chart_paths", []) or []
    missing, empty = [], []
    for path in chart_paths:
        p = Path(path)
        if not p.exists():
            missing.append(path)
        elif p.stat().st_size == 0:
            empty.append(path)

    ok = not missing and not empty
    ledger.record(
        "chart_artifact_integrity", ok,
        f"total={len(chart_paths)}, missing={missing[:5]}, empty={empty[:5]}",
    )


def _check_trend_sample_sufficiency(state, ledger, min_sample_size=MIN_TREND_SAMPLE_SIZE):
    """Flag regression trends marked significant but backed by too few data points.

    A p-value < 0.05 from 4-5 rows is not a trend worth reporting - it's noise
    that happened to fit a line. Agent 4 doesn't know Agent 5's reliability
    bar, so this check re-validates each "significant" trend against a minimum
    sample size before the pipeline trusts it downstream.
    """
    stats = state.get("stats", {}) or {}
    regression = stats.get("regression", {}) or {}

    insufficient = []
    for col, metrics in regression.items():
        if not isinstance(metrics, dict) or not metrics.get("significant"):
            continue
        sample_size = metrics.get("n")
        if sample_size is not None and int(sample_size) < min_sample_size:
            insufficient.append(f"{col} (n={sample_size})")

    ok = not insufficient
    ledger.record(
        "trend_sample_sufficiency", ok,
        f"significant trends with n<{min_sample_size}: {insufficient[:5]}",
        severity="warning",
    )
    return insufficient


def _check_business_rule_validation(state, ledger, max_fail_pct=MAX_VALIDATION_FAIL_PCT):
    """Roll up Agent 3's count-range / financial-constraint validation failures."""
    column_ledger = state.get("column_ledger", {}) or {}
    validation_failures = column_ledger.get("validation_failures", {}) if isinstance(column_ledger, dict) else {}

    if not validation_failures:
        ledger.record("business_rule_validation", True, "no validation checks recorded")
        return

    worst_name, worst_data = max(validation_failures.items(), key=lambda kv: kv[1].get("pct", 0.0))
    worst_pct = worst_data.get("pct", 0.0)
    ok = worst_pct <= max_fail_pct
    ledger.record(
        "business_rule_validation", ok,
        f"worst_check={worst_name} fail_pct={worst_pct} (threshold={max_fail_pct}%)",
        severity="warning",
    )


# ─────────────────────────────────────────────────────────────────────────────
# TIER 2 — Cohen's kappa: LLM semantic tagging vs heuristic type sniffing
# ─────────────────────────────────────────────────────────────────────────────

def _coarsen_intended_type(intended_type):
    return INTENDED_TYPE_TO_COARSE.get(intended_type, "unknown")


def _coarsen_heuristic_type(heuristic_type):
    return HEURISTIC_TYPE_TO_COARSE.get(heuristic_type, "unknown")


def _validate_semantic_tagging_agreement(state, ledger):
    """Compute Cohen's kappa between Agent 2's LLM intended_type and the
    pure-Python heuristic sniffer, treating them as two independent raters.
    Requires no ground truth labels — only measures whether the LLM's type
    judgment mechanically agrees with the rule-based baseline.
    """
    schema_blueprint = state.get("schema_blueprint", {}) or {}
    raw_profile = state.get("raw_profile", {}) or {}
    df = state.get("_df_cache")

    result = {"cohen_kappa": None, "n_columns": 0, "method": "cohen_kappa_vs_heuristic", "disagreements": []}

    if df is None or not raw_profile:
        ledger.record(
            "semantic_tagging_agreement", False,
            "missing _df_cache or raw_profile for heuristic comparison", severity="warning",
        )
        return result

    try:
        heuristic_types = _infer_intended_types(df, raw_profile)
    except Exception as e:
        ledger.record("semantic_tagging_agreement", False, f"heuristic re-run failed: {e}", severity="warning")
        return result

    rater_heuristic, rater_llm, disagreements = [], [], []
    for col, meta in schema_blueprint.items():
        if col == "__metadata__" or not isinstance(meta, dict):
            continue
        if col not in heuristic_types:
            continue
        heuristic_coarse = _coarsen_heuristic_type(heuristic_types[col])
        llm_coarse = _coarsen_intended_type(meta.get("intended_type", "unknown"))
        rater_heuristic.append(heuristic_coarse)
        rater_llm.append(llm_coarse)
        if heuristic_coarse != llm_coarse:
            disagreements.append(f"{col}: heuristic={heuristic_coarse} vs llm={llm_coarse}")

    result["n_columns"] = len(rater_heuristic)
    result["disagreements"] = disagreements

    if len(rater_heuristic) < 2:
        ledger.record("semantic_tagging_agreement", True, "not enough columns for kappa; skipped")
        return result

    try:
        if len(set(rater_heuristic + rater_llm)) < 2:
            kappa = 1.0  # both raters used a single class throughout -> trivial agreement
        else:
            kappa = float(_cohen_kappa_score(rater_heuristic, rater_llm))
    except Exception as e:
        ledger.record("semantic_tagging_agreement", False, f"kappa computation failed: {e}", severity="warning")
        return result

    result["cohen_kappa"] = round(kappa, 3)
    ok = kappa >= MIN_ACCEPTABLE_KAPPA
    ledger.record(
        "semantic_tagging_agreement", ok,
        f"cohen_kappa={result['cohen_kappa']}, n_columns={result['n_columns']}, "
        f"disagreements={disagreements[:5]}",
        severity="warning",
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# MAIN AGENT FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def agent5_output_validator(state: GraphState) -> GraphState:
    errors = state.get("errors", [])
    cleaned_df = state.get("cleaned_df")

    if cleaned_df is None:
        errors.append("Agent5: No cleaned_df in state. Agent 3 or Agent 4 failed.")
        return {**state, "errors": errors}

    ledger = ValidationLedger()
    verbose = _verbose_logging_enabled()

    print("[Agent 5] Starting output validation")

    _check_row_column_reconciliation(state, ledger)
    _check_schema_dataframe_consistency(state, ledger)
    _check_quality_score_bounds(state, ledger)
    _check_stats_numeric_sanity(state, ledger)
    _check_chart_artifact_integrity(state, ledger)
    _check_business_rule_validation(state, ledger)
    insufficient_trends = _check_trend_sample_sufficiency(state, ledger)

    dq_summary = (state.get("stats", {}) or {}).get("data_quality_issues", {}) or {}
    review_required = bool(dq_summary.get("review_required"))

    semantic_agreement = _validate_semantic_tagging_agreement(state, ledger)

    if verbose:
        for name, result in ledger.checks.items():
            print(f"[Agent 5]   {name}: {result['status']} - {result['detail']}")

    total_checks = len(ledger.checks)
    failed_checks = sum(1 for c in ledger.checks.values() if c["status"] == "fail")
    warned_checks = sum(1 for c in ledger.checks.values() if c["status"] == "warn")
    passed_checks = total_checks - failed_checks - warned_checks

    overall_validation_score = round(
        100.0 * (passed_checks + 0.5 * warned_checks) / max(total_checks, 1), 2
    )
    passed = failed_checks == 0

    validation_report = {
        "tier1_checks": ledger.checks,
        "semantic_tagging_agreement": semantic_agreement,
        "overall_validation_score": overall_validation_score,
        "passed": passed,
        "flagged_issues": ledger.issues,
    }

    print(
        f"[Agent 5] Completed: score={overall_validation_score}/100 "
        f"passed={passed_checks}/{total_checks} warned={warned_checks} failed={failed_checks} "
        f"kappa={semantic_agreement.get('cohen_kappa')}"
    )
    if ledger.issues:
        print(f"[Agent 5] Flagged issues ({len(ledger.issues)}):")
        for issue in ledger.issues[:5]:
            print(f"[Agent 5]   - [{issue['severity']}] {issue['check']}: {issue['detail']}")

    validation_confidence = _validation_confidence(
        overall_validation_score,
        review_required=review_required,
        insufficient_trends=insufficient_trends,
    )
    validation_report["confidence_in_score"] = validation_confidence
    validation_report["rule_review_required"] = review_required
    confidence = validation_confidence
    state_with_reliability = update_reliability(
        state,
        "agent5",
        confidence,
        evidence=[
            f"validation_score={overall_validation_score}",
            f"failed_checks={failed_checks}",
            f"cohen_kappa={semantic_agreement.get('cohen_kappa')}",
        ],
        decision_readiness="ready" if passed else "needs_review",
    )

    return {
        **state_with_reliability,
        "validation_report": validation_report,
        "errors": errors,
    }
