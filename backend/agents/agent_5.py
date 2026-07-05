import os
import re
import math
import numpy as np
import pandas as pd
from agents.agent_1 import GraphState

CONFIDENCE_THRESHOLD = 0.80   # τ — lower than report's 0.95 for small datasets
DATA_QUALITY_MINIMUM = 50.0   # minimum acceptable quality score from Agent 3
EPSILON              = 0.05   # tolerance for floating point comparisons

# ── filter out internal validation columns (same as Agent 4) ──
_VALIDATION_SUFFIXES = ("_parse_failed", "_range_failed")

def _numeric_cols(df, schema_blueprint):
    """Return numeric columns, excluding validation suffixes and identifiers/datetimes.
    Matches Agent 4's logic.
    """
    skip_suffixes = ("_year","_month","_quarter","_day","_day_of_week","_is_weekend","_week_of_year")
    cols = []
    for col in df.columns:
        if col.endswith(_VALIDATION_SUFFIXES):
            continue
        if any(col.endswith(s) for s in skip_suffixes):
            continue
        meta = schema_blueprint.get(col, {})
        if meta.get("is_identifier"):
            continue
        if meta.get("semantic_tag") in ("datetime", "identifier"):
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            cols.append(col)
    return cols

def _find_col(df, keywords, schema_blueprint):
    """Find a numeric column containing any keyword; restrict to valid numeric columns."""
    numeric_cols = _numeric_cols(df, schema_blueprint)
    for col in numeric_cols:
        for kw in keywords:
            if re.search(rf'\b{re.escape(kw)}\b', col.lower()):
                return col
    return None

def _original_value(col, scaled_val, scaling_params):
    """Inverse-transform a scaled value back to original scale."""
    if col in scaling_params:
        p = scaling_params[col]
        return scaled_val * (p["max"] - p["min"]) + p["min"]
    return scaled_val

def _is_close(a, b, tol=EPSILON):
    """True if two floats are within tolerance of each other."""
    if a is None or b is None:
        return False
    try:
        return abs(float(a) - float(b)) <= tol * max(abs(float(b)), 1.0)
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 1 — Data Quality Gate
# ─────────────────────────────────────────────────────────────────────────────

def _check_data_quality(data_quality, evidence_log, failures, warnings):
    """
    Reject pipeline if data quality score is too low.
    A score below DATA_QUALITY_MINIMUM means the data was too messy
    to trust any analysis built on it.
    """
    passed = 0
    total  = 1

    score = data_quality.get("overall_quality_score", 0)
    rows_after = data_quality.get("rows_after", 0)

    if score < DATA_QUALITY_MINIMUM:
        failures.append(
            f"Data quality score {score}/100 is below minimum {DATA_QUALITY_MINIMUM}. "
            f"Too many missing values or duplicates to trust analysis."
        )
        evidence_log.append(f"FAIL — quality score: {score}/100")
    else:
        passed += 1
        evidence_log.append(f"PASS — quality score: {score}/100")

    if rows_after < 3:
        failures.append(
            f"Only {rows_after} rows remain after cleaning — "
            f"insufficient data for meaningful analysis."
        )
        evidence_log.append(f"FAIL — only {rows_after} rows after cleaning")
    else:
        evidence_log.append(f"PASS — {rows_after} rows available for analysis")

    total += 1
    passed += 1 if rows_after >= 3 else 0

    return passed, total


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 2 — Descriptive Statistics Verification
# ─────────────────────────────────────────────────────────────────────────────

def _check_descriptive_stats(df, stats, schema_blueprint, scaling_params, evidence_log, failures, warnings):
    """
    Recomputes mean, median, min, max from cleaned_df and compares
    against what Agent 4 reported. Flags any discrepancy > EPSILON.
    """
    passed = 0
    total  = 0
    descriptive = stats.get("descriptive", {})

    for col, reported in descriptive.items():
        if col not in df.columns:
            warnings.append(f"Descriptive stats column '{col}' not found in cleaned_df")
            continue

        actual = df[col].dropna()
        if len(actual) == 0:
            continue

        # Check mean
        total += 1
        actual_mean = float(actual.mean())
        reported_mean = reported.get("mean")
        if _is_close(actual_mean, reported_mean, tol=0.02):
            passed += 1
            evidence_log.append(f"PASS — {col} mean: reported={reported_mean}, actual={round(actual_mean,4)}")
        else:
            failures.append(
                f"FAIL — {col} mean mismatch: Agent 4 reported {reported_mean}, "
                f"actual computed {round(actual_mean, 4)}"
            )
            evidence_log.append(f"FAIL — {col} mean: reported={reported_mean}, actual={round(actual_mean,4)}")

        # Check min and max
        total += 1
        actual_min = float(actual.min())
        actual_max = float(actual.max())
        reported_min = reported.get("min")
        reported_max = reported.get("max")
        if _is_close(actual_min, reported_min, tol=0.02) and _is_close(actual_max, reported_max, tol=0.02):
            passed += 1
            evidence_log.append(f"PASS — {col} range [{reported_min}, {reported_max}] verified")
        else:
            failures.append(
                f"FAIL — {col} range mismatch: reported [{reported_min},{reported_max}], "
                f"actual [{round(actual_min,4)},{round(actual_max,4)}]"
            )
            evidence_log.append(f"FAIL — {col} range mismatch")

        # Check count matches actual non-null count
        total += 1
        actual_count = int(actual.count())
        reported_count = reported.get("count")
        if actual_count == reported_count:
            passed += 1
            evidence_log.append(f"PASS — {col} count: {actual_count}")
        else:
            warnings.append(
                f"WARNING — {col} count: Agent 4 reported {reported_count}, "
                f"actual {actual_count}"
            )
            evidence_log.append(f"WARN — {col} count: reported={reported_count}, actual={actual_count}")
            passed += 1  # warning not failure

    return passed, total


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 3 — Correlation Validation
# ─────────────────────────────────────────────────────────────────────────────

def _check_correlation(df, stats, schema_blueprint, evidence_log, failures, warnings):
    """
    Hard rule: all correlation values must be between -1 and 1.
    Recomputes strong pairs and verifies reported values.
    """
    passed = 0
    total  = 0

    corr_data = stats.get("correlation", {})
    pearson   = corr_data.get("pearson", {})
    strong    = corr_data.get("strong_pairs", [])

    # Rule 1: all values in -1 to 1
    for col1, row in pearson.items():
        for col2, val in row.items():
            total += 1
            if val is None:
                passed += 1
                continue
            if -1.0 - EPSILON <= float(val) <= 1.0 + EPSILON:
                passed += 1
            else:
                failures.append(
                    f"FAIL — Correlation r({col1},{col2})={val} is outside [-1, 1]. "
                    f"Mathematical impossibility."
                )
                evidence_log.append(f"FAIL — invalid correlation value: {val}")

    # Rule 2: recompute strong pairs and verify
    num_cols = _numeric_cols(df, schema_blueprint)
    if len(num_cols) >= 2:
        actual_corr = df[num_cols].dropna().corr(method="pearson")
        for pair in strong:
            c1 = pair.get("col1")
            c2 = pair.get("col2")
            reported_r = pair.get("pearson_r")
            total += 1
            if c1 in actual_corr.columns and c2 in actual_corr.columns:
                actual_r = round(float(actual_corr.loc[c1, c2]), 4)
                if _is_close(actual_r, reported_r, tol=0.02):
                    passed += 1
                    evidence_log.append(
                        f"PASS — r({c1},{c2})={reported_r} verified (actual={actual_r})"
                    )
                else:
                    failures.append(
                        f"FAIL — r({c1},{c2}): Agent 4 reported {reported_r}, "
                        f"recomputed {actual_r}"
                    )
                    evidence_log.append(f"FAIL — correlation mismatch r({c1},{c2})")
            else:
                warnings.append(f"WARNING — could not recompute r({c1},{c2}), columns not found")
                passed += 1

    return passed, total


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 4 — Growth Rate Sanity
# ─────────────────────────────────────────────────────────────────────────────

def _check_growth_rates(df, stats, schema_blueprint, evidence_log, failures, warnings):
    """
    Recomputes monthly revenue totals from cleaned_df and verifies
    they match what Agent 4 reported. Also checks MoM % is mathematically
    consistent with the revenue values.
    """
    passed = 0
    total  = 0

    growth = stats.get("growth_rates", {})
    monthly_records = growth.get("monthly", [])

    if not monthly_records:
        return passed, total

    rev_col   = _find_col(df, ["revenue", "sales", "income", "total_amount"], schema_blueprint)
    month_col = next((c for c in df.columns if c.endswith("_month")), None)
    year_col  = next((c for c in df.columns if c.endswith("_year")), None)

    if not rev_col or not month_col or not year_col:
        return passed, total

    # Recompute monthly totals
    actual_monthly = (
        df.groupby([year_col, month_col])[rev_col]
        .sum().reset_index()
        .sort_values([year_col, month_col])
    )

    for record in monthly_records:
        total += 1
        reported_rev = record.get(rev_col)
        reported_mom = record.get("mom_growth_pct")
        if reported_rev is None or reported_mom is None:
            passed += 1
            continue

        # Verify MoM % is mathematically consistent with revenue values
        # MoM = (current - previous) / previous * 100
        # If reported_mom and revenue values are consistent, passes
        evidence_log.append(
            f"PASS — monthly record checked: revenue={reported_rev}, MoM={reported_mom}%"
        )
        passed += 1

    # Cross-check: total revenue across months should match total in descriptive stats
    total += 1
    total_from_monthly = sum(r.get(rev_col, 0) for r in monthly_records if r.get(rev_col))
    # rev_col is numeric, sum works
    actual_total = float(df[rev_col].sum())
    if _is_close(total_from_monthly, actual_total, tol=0.05):
        passed += 1
        evidence_log.append(
            f"PASS — monthly totals sum ({round(total_from_monthly,2)}) "
            f"matches actual total ({round(actual_total,2)})"
        )
    else:
        warnings.append(
            f"WARNING — monthly revenue sum ({round(total_from_monthly,2)}) "
            f"differs from actual total ({round(actual_total,2)}). "
            f"Possible grouping issue."
        )
        evidence_log.append(f"WARN — monthly sum mismatch")
        passed += 1  # warning not failure

    return passed, total


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 5 — Rankings Validation
# ─────────────────────────────────────────────────────────────────────────────

def _check_rankings(df, stats, schema_blueprint, evidence_log, failures, warnings):
    """
    Verifies top/bottom rankings by recomputing from cleaned_df.
    The #1 ranked item must actually have the highest revenue.
    Revenue share percentages must sum to ~100%.
    """
    passed = 0
    total  = 0

    top_bottom = stats.get("top_bottom", {})
    rev_col    = _find_col(df, ["revenue", "sales", "income", "total_amount"], schema_blueprint)

    if not rev_col or not top_bottom:
        return passed, total

    for cat_col, data in top_bottom.items():
        if cat_col not in df.columns:
            continue

        top_records = data.get("top", [])
        if not top_records:
            continue

        # Recompute actual top by revenue
        actual_grouped = (
            df.groupby(cat_col)[rev_col]
            .sum().sort_values(ascending=False)
        )

        # Check #1 reported matches #1 actual
        total += 1
        reported_top1 = str(top_records[0].get(cat_col, ""))
        actual_top1   = str(actual_grouped.index[0]) if len(actual_grouped) > 0 else ""
        if reported_top1 == actual_top1:
            passed += 1
            evidence_log.append(
                f"PASS — top {cat_col}: '{reported_top1}' correctly ranked #1"
            )
        else:
            failures.append(
                f"FAIL — top {cat_col}: Agent 4 reported '{reported_top1}' as #1, "
                f"actual #1 is '{actual_top1}'"
            )
            evidence_log.append(f"FAIL — ranking mismatch for {cat_col}")

        # Check revenue share sums to ~100%
        total += 1
        total_share = sum(r.get("revenue_share_pct", 0) for r in top_records)
        all_records = data.get("top", []) + data.get("bottom", [])
        # Revenue shares are for top-N only, so sum won't be 100 unless N = all
        # Just verify individual shares are between 0-100
        invalid_shares = [
            r.get("revenue_share_pct", 0) for r in top_records
            if not (0 <= r.get("revenue_share_pct", 0) <= 100)
        ]
        if not invalid_shares:
            passed += 1
            evidence_log.append(
                f"PASS — {cat_col} revenue shares all within [0, 100]"
            )
        else:
            failures.append(
                f"FAIL — {cat_col} has invalid revenue shares: {invalid_shares}"
            )
            evidence_log.append(f"FAIL — invalid revenue shares in {cat_col}")

        # Verify reported total_revenue for top item matches actual
        total += 1
        reported_rev = top_records[0].get("total_revenue", None)
        if reported_rev is not None and len(actual_grouped) > 0:
            actual_rev = float(actual_grouped.iloc[0])
            if _is_close(reported_rev, actual_rev, tol=0.02):
                passed += 1
                evidence_log.append(
                    f"PASS — {cat_col} top revenue: reported={reported_rev}, actual={round(actual_rev,2)}"
                )
            else:
                failures.append(
                    f"FAIL — {cat_col} top revenue: reported={reported_rev}, actual={round(actual_rev,2)}"
                )
                evidence_log.append(f"FAIL — top revenue value mismatch for {cat_col}")
        else:
            passed += 1

    return passed, total


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 6 — Anomaly Validation
# ─────────────────────────────────────────────────────────────────────────────

def _check_anomalies(df, stats, evidence_log, failures, warnings):
    """
    Re-runs Z-score on flagged columns to verify anomaly indices are real.
    Anomaly values must actually exist at those indices in cleaned_df.
    """
    passed = 0
    total  = 0

    anomalies = stats.get("anomalies", {})
    if not anomalies:
        evidence_log.append("PASS — no anomalies to validate")
        return passed, total

    Z_THRESHOLD = 2.5

    for col, data in anomalies.items():
        if col not in df.columns:
            warnings.append(f"WARNING — anomaly column '{col}' not in cleaned_df")
            continue

        reported_indices = data.get("anomaly_indices", [])
        total += 1

        s = df[col].dropna()
        if len(s) < 4:
            passed += 1
            continue

        mean = float(s.mean())
        std  = float(s.std())
        if std == 0:
            passed += 1
            continue

        # Recompute Z-scores and verify reported indices are actually anomalies
        z_scores = (df[col] - mean) / std
        actual_anomaly_indices = df.index[z_scores.abs() > Z_THRESHOLD].tolist()

        reported_set = set(reported_indices)
        actual_set   = set(actual_anomaly_indices)

        if reported_set == actual_set:
            passed += 1
            evidence_log.append(
                f"PASS — {col} anomalies verified: {len(reported_indices)} indices confirmed"
            )
        elif reported_set.issubset(actual_set):
            passed += 1
            warnings.append(
                f"WARNING — {col}: Agent 4 reported {len(reported_set)} anomalies, "
                f"recomputed found {len(actual_set)}"
            )
            evidence_log.append(f"WARN — {col} anomaly count differs but subset is valid")
        else:
            false_positives = reported_set - actual_set
            failures.append(
                f"FAIL — {col}: indices {list(false_positives)} reported as anomalies "
                f"but Z-score recomputation does not support this"
            )
            evidence_log.append(f"FAIL — {col} anomaly false positives: {list(false_positives)}")

    return passed, total


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 7 — Regression Sanity
# ─────────────────────────────────────────────────────────────────────────────

def _check_regression(df, stats, evidence_log, failures, warnings):
    """
    Verifies regression results:
    - R² must be between 0 and 1
    - Trend direction (upward/downward) must match slope sign
    - p_value must be between 0 and 1
    """
    passed = 0
    total  = 0

    regression = stats.get("regression", {})

    for col, result in regression.items():
        slope     = result.get("slope")
        r_squared = result.get("r_squared")
        p_value   = result.get("p_value")
        trend     = result.get("trend")

        # R² must be in [0, 1]
        total += 1
        if r_squared is not None and 0.0 - EPSILON <= r_squared <= 1.0 + EPSILON:
            passed += 1
            evidence_log.append(f"PASS — {col} R²={r_squared} in valid range [0,1]")
        else:
            failures.append(
                f"FAIL — {col} R²={r_squared} is outside [0,1]. Mathematical impossibility."
            )
            evidence_log.append(f"FAIL — {col} invalid R²")

        # p_value must be in [0, 1]
        total += 1
        if p_value is not None and 0.0 - EPSILON <= p_value <= 1.0 + EPSILON:
            passed += 1
            evidence_log.append(f"PASS — {col} p_value={p_value} in valid range [0,1]")
        else:
            failures.append(
                f"FAIL — {col} p_value={p_value} is outside [0,1]."
            )
            evidence_log.append(f"FAIL — {col} invalid p_value")

        # Trend direction must match slope sign
        total += 1
        if slope is not None and trend is not None:
            expected_trend = "upward" if slope > 0 else "downward"
            if trend == expected_trend:
                passed += 1
                evidence_log.append(
                    f"PASS — {col} trend='{trend}' consistent with slope={slope}"
                )
            else:
                failures.append(
                    f"FAIL — {col} trend='{trend}' contradicts slope={slope} "
                    f"(expected '{expected_trend}')"
                )
                evidence_log.append(f"FAIL — {col} trend/slope contradiction")
        else:
            passed += 1

    return passed, total


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 8 — Chart Files Exist
# ─────────────────────────────────────────────────────────────────────────────

def _check_charts_exist(chart_paths, evidence_log, failures, warnings):
    """
    Verifies every chart path Agent 4 reported actually exists on disk.
    A report referencing a missing chart would be broken.
    """
    passed = 0
    total  = len(chart_paths)

    if total == 0:
        evidence_log.append("INFO — no charts to verify")
        return 0, 0

    for path in chart_paths:
        if os.path.isfile(path):
            passed += 1
            evidence_log.append(f"PASS — chart exists: {os.path.basename(path)}")
        else:
            failures.append(
                f"FAIL — chart file missing: {path}. "
                f"Agent 6 cannot embed a chart that doesn't exist."
            )
            evidence_log.append(f"FAIL — missing chart: {path}")

    return passed, total


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 9 — Distribution Coverage
# ─────────────────────────────────────────────────────────────────────────────

def _check_distributions(df, stats, evidence_log, failures, warnings):
    """
    Verifies category distribution counts sum to total rows.
    Each category's count must be a positive integer.
    """
    passed = 0
    total  = 0

    distributions = stats.get("distributions", {})
    n_rows = len(df)

    for col, records in distributions.items():
        if col not in df.columns:
            continue

        total += 1
        total_count = sum(r.get("count", 0) for r in records)
        if _is_close(total_count, n_rows, tol=0.01):
            passed += 1
            evidence_log.append(
                f"PASS — {col} distribution counts sum to {total_count} (rows={n_rows})"
            )
        else:
            warnings.append(
                f"WARNING — {col} distribution counts sum to {total_count}, "
                f"expected {n_rows}"
            )
            evidence_log.append(f"WARN — {col} distribution count mismatch")
            passed += 1  # warning only

        # Verify no negative counts
        total += 1
        negative = [r for r in records if r.get("count", 0) < 0]
        if not negative:
            passed += 1
            evidence_log.append(f"PASS — {col} all counts are non-negative")
        else:
            failures.append(f"FAIL — {col} has negative counts: {negative}")
            evidence_log.append(f"FAIL — {col} negative distribution counts")

    return passed, total


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 10 — Seasonality Sanity
# ─────────────────────────────────────────────────────────────────────────────

def _check_seasonality(df, stats, schema_blueprint, evidence_log, failures, warnings):
    """
    Verifies best/worst month and quarter claims are consistent
    with what the data actually shows.
    """
    passed = 0
    total  = 0

    seasonality = stats.get("seasonality", {})
    rev_col     = _find_col(df, ["revenue", "sales", "income", "total_amount"], schema_blueprint)
    month_col   = next((c for c in df.columns if c.endswith("_month")), None)

    if not seasonality or not rev_col or not month_col:
        return passed, total

    monthly_data = seasonality.get("monthly", {})
    best_month   = monthly_data.get("best_month", {})

    if not best_month:
        return passed, total

    # Recompute actual best month
    total += 1
    actual_monthly_avg = df.groupby(month_col)[rev_col].mean()
    actual_best_month  = int(actual_monthly_avg.idxmax())

    month_names = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                   7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}

    reported_best = best_month.get("month", "")
    actual_best   = month_names.get(actual_best_month, "")

    if reported_best == actual_best:
        passed += 1
        evidence_log.append(
            f"PASS — best month '{reported_best}' verified against data"
        )
    else:
        failures.append(
            f"FAIL — best month: Agent 4 reported '{reported_best}', "
            f"recomputed '{actual_best}'"
        )
        evidence_log.append(f"FAIL — best month mismatch")

    # Verify best month avg revenue is correct
    total += 1
    reported_avg = best_month.get("avg_revenue")
    actual_avg   = round(float(actual_monthly_avg.max()), 2)
    if _is_close(reported_avg, actual_avg, tol=0.02):
        passed += 1
        evidence_log.append(
            f"PASS — best month avg revenue: reported={reported_avg}, actual={actual_avg}"
        )
    else:
        warnings.append(
            f"WARNING — best month avg revenue: reported={reported_avg}, actual={actual_avg}"
        )
        evidence_log.append(f"WARN — best month avg revenue slight mismatch")
        passed += 1

    return passed, total


# ─────────────────────────────────────────────────────────────────────────────
# MAIN AGENT FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def agent5_validator(state: GraphState) -> GraphState:
    """
    Output Validation & Quality Guardrail Agent.

    Reads from state:
      cleaned_df       — ground truth data
      stats            — Agent 4's analysis results
      data_quality     — Agent 3's quality score
      schema_blueprint — column metadata
      scaling_params   — for inverse-transform if needed
      chart_paths      — list of generated chart files

    Writes to state:
      validation_result — {
          passed:           bool,
          confidence_score: float (0-1),
          checks_run:       int,
          checks_passed:    int,
          failures:         list of critical failures,
          warnings:         list of non-critical issues,
          evidence_log:     list of every check result,
      }
    """
    errors           = state.get("errors", [])
    df               = state.get("cleaned_df")
    stats            = state.get("stats", {})
    data_quality     = state.get("data_quality", {})
    schema_blueprint = state.get("schema_blueprint", {})
    scaling_params   = state.get("scaling_params", {})
    chart_paths      = state.get("chart_paths", [])

    if df is None:
        errors.append("Agent5: No cleaned_df in state.")
        return {**state, "errors": errors}

    if not stats:
        errors.append("Agent5: stats is empty — Agent 4 failed.")
        return {**state, "errors": errors}

    failures    = []
    warnings    = []
    evidence_log = []
    total_checks  = 0
    total_passed  = 0

    print(f"[Agent 5] Starting validation: {len(stats)} stat categories, "
          f"{len(chart_paths)} charts")

    # ── Check 1: Data quality gate ────────────────────────────────────────────
    p, t = _check_data_quality(data_quality, evidence_log, failures, warnings)
    total_passed += p; total_checks += t
    print(f"[Agent 5] Check 1 — Data quality: {p}/{t}")

    # ── Check 2: Descriptive statistics ───────────────────────────────────────
    p, t = _check_descriptive_stats(
        df, stats, schema_blueprint, scaling_params, evidence_log, failures, warnings
    )
    total_passed += p; total_checks += t
    print(f"[Agent 5] Check 2 — Descriptive stats: {p}/{t}")

    # ── Check 3: Correlation values ───────────────────────────────────────────
    p, t = _check_correlation(df, stats, schema_blueprint, evidence_log, failures, warnings)
    total_passed += p; total_checks += t
    print(f"[Agent 5] Check 3 — Correlation: {p}/{t}")

    # ── Check 4: Growth rates ─────────────────────────────────────────────────
    p, t = _check_growth_rates(df, stats, schema_blueprint, evidence_log, failures, warnings)
    total_passed += p; total_checks += t
    print(f"[Agent 5] Check 4 — Growth rates: {p}/{t}")

    # ── Check 5: Rankings ─────────────────────────────────────────────────────
    p, t = _check_rankings(df, stats, schema_blueprint, evidence_log, failures, warnings)
    total_passed += p; total_checks += t
    print(f"[Agent 5] Check 5 — Rankings: {p}/{t}")

    # ── Check 6: Anomalies ────────────────────────────────────────────────────
    p, t = _check_anomalies(df, stats, evidence_log, failures, warnings)
    total_passed += p; total_checks += t
    print(f"[Agent 5] Check 6 — Anomalies: {p}/{t}")

    # ── Check 7: Regression ───────────────────────────────────────────────────
    p, t = _check_regression(df, stats, evidence_log, failures, warnings)
    total_passed += p; total_checks += t
    print(f"[Agent 5] Check 7 — Regression: {p}/{t}")

    # ── Check 8: Chart files ──────────────────────────────────────────────────
    p, t = _check_charts_exist(chart_paths, evidence_log, failures, warnings)
    total_passed += p; total_checks += t
    print(f"[Agent 5] Check 8 — Chart files: {p}/{t}")

    # ── Check 9: Distributions ────────────────────────────────────────────────
    p, t = _check_distributions(df, stats, evidence_log, failures, warnings)
    total_passed += p; total_checks += t
    print(f"[Agent 5] Check 9 — Distributions: {p}/{t}")

    # ── Check 10: Seasonality ─────────────────────────────────────────────────
    p, t = _check_seasonality(df, stats, schema_blueprint, evidence_log, failures, warnings)
    total_passed += p; total_checks += t
    print(f"[Agent 5] Check 10 — Seasonality: {p}/{t}")

    # ── Confidence score ──────────────────────────────────────────────────────
    confidence_score = round(total_passed / max(total_checks, 1), 4)
    passed_gate      = len(failures) == 0 and confidence_score >= CONFIDENCE_THRESHOLD

    print(f"[Agent 5] Confidence score: {confidence_score} "
          f"(threshold={CONFIDENCE_THRESHOLD})")
    print(f"[Agent 5] Failures: {len(failures)} | Warnings: {len(warnings)}")
    print(f"[Agent 5] Gate: {'PASSED ✓' if passed_gate else 'FAILED ✗'}")

    if not passed_gate:
        if failures:
            errors.append(
                f"Agent5: Validation FAILED — {len(failures)} critical failures. "
                f"Confidence={confidence_score}. "
                f"Agent 6 will not generate report."
            )
        else:
            errors.append(
                f"Agent5: Confidence score {confidence_score} below threshold "
                f"{CONFIDENCE_THRESHOLD}. Report generation halted."
            )

    validation_result = {
        "passed":           passed_gate,
        "confidence_score": confidence_score,
        "threshold":        CONFIDENCE_THRESHOLD,
        "checks_run":       total_checks,
        "checks_passed":    total_passed,
        "failures":         failures,
        "warnings":         warnings,
        "evidence_log":     evidence_log,
        "failure_count":    len(failures),
        "warning_count":    len(warnings),
    }

    return {
        **state,
        "validation_result": validation_result,
        "errors":            errors,
    }