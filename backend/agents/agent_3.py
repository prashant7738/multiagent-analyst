import re
import os
from pathlib import Path

import numpy as np
import pandas as pd

from agents.agent_1 import GraphState


NULL_STRINGS = {
    "nan", "none", "null", "n/a", "na", "-", "", "unknown",
    "not available", "not applicable", "nil", "#n/a", "nan ",
}

PREPROCESSING_PROFILES = {
    "strict": {
        "currency_max_abs_value": 100_000_000,
        "max_reasonable_tax_rate": 0.30,
        "reconciliation_rel_tol": 0.01,
        "reconciliation_abs_tol": 0.50,
        "quality_weights": {
            "remaining_null_pct": 0.55,
            "validation_fail_pct": 0.35,
            "duplicate_rate_pct": 0.10,
        },
    },
    "balanced": {
        "currency_max_abs_value": 1_000_000_000,
        "max_reasonable_tax_rate": 0.40,
        "reconciliation_rel_tol": 0.02,
        "reconciliation_abs_tol": 1.0,
        "quality_weights": {
            "remaining_null_pct": 0.50,
            "validation_fail_pct": 0.40,
            "duplicate_rate_pct": 0.10,
        },
    },
    "lenient": {
        "currency_max_abs_value": 10_000_000_000,
        "max_reasonable_tax_rate": 0.60,
        "reconciliation_rel_tol": 0.05,
        "reconciliation_abs_tol": 2.0,
        "quality_weights": {
            "remaining_null_pct": 0.40,
            "validation_fail_pct": 0.30,
            "duplicate_rate_pct": 0.30,
        },
    },
}

DEFAULT_PROFILE = "balanced"


def _verbose_logging_enabled():
    val = os.getenv("PIPELINE_VERBOSE", "0").strip().lower()
    return val in {"1", "true", "yes", "on"}


class ColumnLedger:
    """Tracks per-column transformation details for the final report."""
    def __init__(self):
        self.columns = {}  # col_name -> {action, before_nulls_pct, after_nulls_pct, parse_fail_pct, range_fail_pct, notes}
        self.clip_bounds = {}  # col_name -> {lower, upper}
        self.clip_post_bounds = {}  # col_name -> {min, max}
        self.validation_failures = {}  # check_name -> {count, rows_affected_pct, note}
        self.rows_removed = 0
    
    def record_column_action(self, col_name, action, before_nulls_pct, after_nulls_pct, notes=""):
        if col_name not in self.columns:
            self.columns[col_name] = {}
        self.columns[col_name].update({
            "action": action,
            "before_nulls_pct": round(before_nulls_pct, 2),
            "after_nulls_pct": round(after_nulls_pct, 2),
            "parse_fail_pct": 0.0,
            "range_fail_pct": 0.0,
            "notes": notes
        })
    
    def record_parse_failure(self, col_name, pct, count):
        if col_name not in self.columns:
            self.columns[col_name] = {}
        self.columns[col_name]["parse_fail_pct"] = round(pct, 2)
        self.columns[col_name]["parse_fail_count"] = count
    
    def record_range_failure(self, col_name, pct, count):
        if col_name not in self.columns:
            self.columns[col_name] = {}
        self.columns[col_name]["range_fail_pct"] = round(pct, 2)
        self.columns[col_name]["range_fail_count"] = count
    
    def record_clip_bounds(self, col_name, lower, upper):
        self.clip_bounds[col_name] = {"lower": round(float(lower), 2), "upper": round(float(upper), 2)}
    
    def record_clip_post_bounds(self, col_name, min_val, max_val):
        self.clip_post_bounds[col_name] = {"min": round(float(min_val), 2), "max": round(float(max_val), 2)}
    
    def record_validation_failure(self, check_name, count, total_rows):
        pct = (count / max(total_rows, 1)) * 100
        self.validation_failures[check_name] = {"count": count, "pct": round(pct, 2)}


def _detect_dataset_domain(schema_blueprint):
    finance_name_hits = 0
    finance_tag_hits = 0

    finance_keywords = {
        "amount", "revenue", "cost", "tax", "price", "discount", "sales", "profit", "margin", "invoice"
    }

    for col, meta in schema_blueprint.items():
        col_lower = col.lower()
        if any(kw in col_lower for kw in finance_keywords):
            finance_name_hits += 1
        if meta.get("semantic_tag") in ("currency", "percentage"):
            finance_tag_hits += 1

    if finance_name_hits >= 3 or finance_tag_hits >= 2:
        return "finance_sales"
    return "generic"


def _build_preprocessing_config(state_config, requested_profile, schema_blueprint):
    domain = _detect_dataset_domain(schema_blueprint)

    if requested_profile in PREPROCESSING_PROFILES:
        selected_profile = requested_profile
    elif domain == "finance_sales":
        selected_profile = "strict"
    else:
        selected_profile = DEFAULT_PROFILE

    base_profile = PREPROCESSING_PROFILES[selected_profile]
    cfg = {
        "currency_max_abs_value": base_profile["currency_max_abs_value"],
        "max_reasonable_tax_rate": base_profile["max_reasonable_tax_rate"],
        "reconciliation_rel_tol": base_profile["reconciliation_rel_tol"],
        "reconciliation_abs_tol": base_profile["reconciliation_abs_tol"],
        "quality_weights": base_profile["quality_weights"].copy(),
    }
    if not isinstance(state_config, dict):
        return cfg, selected_profile, domain

    for key in [
        "currency_max_abs_value",
        "max_reasonable_tax_rate",
        "reconciliation_rel_tol",
        "reconciliation_abs_tol",
    ]:
        if key in state_config:
            cfg[key] = state_config[key]

    quality_weights = state_config.get("quality_weights")
    if isinstance(quality_weights, dict):
        cfg["quality_weights"].update(quality_weights)

    return cfg, selected_profile, domain


def _normalize_missing_text(series):
    """Normalize common textual null markers while preserving true missing values."""
    trimmed = series.astype("string").str.strip()
    normalized = trimmed.str.casefold()
    return trimmed.mask(normalized.isin(NULL_STRINGS), pd.NA)


def _canonicalize_text_values(series):
    """Canonicalize categorical-like text so case/separator variants collapse to one value."""
    canonical = series.astype("string")
    canonical = canonical.str.replace(r"[_\-]+", " ", regex=True)
    canonical = canonical.str.replace(r"\s+", " ", regex=True).str.strip()
    canonical = _normalize_missing_text(canonical)
    return canonical.str.casefold().str.title()


def _log_null_diff(before_df, after_df, step_name):
    """Return per-column null-count deltas for debugging and regression detection."""
    notes = []
    shared_cols = [c for c in before_df.columns if c in after_df.columns]
    for col in shared_cols:
        before_nulls = int(before_df[col].isna().sum())
        after_nulls = int(after_df[col].isna().sum())
        if before_nulls != after_nulls:
            delta = after_nulls - before_nulls
            direction = "increased" if delta > 0 else "decreased"
            notes.append(
                f"{step_name} null diff [{col}]: {before_nulls} -> {after_nulls} "
                f"({direction} by {abs(delta)})"
            )
    return notes


def _is_count_field(col, meta):
    if meta.get("semantic_tag") == "count":
        return True
    return bool(re.search(r"\b(count|counts|qty|quantity|quantities|units|num|number)\b", col.lower()))


def _resolve_business_keys(df, schema_blueprint):
    key_cols = [
        col for col, meta in schema_blueprint.items()
        if col in df.columns and meta.get("is_identifier")
    ]
    if key_cols:
        return key_cols

    fallback_priority = ["transaction_id", "order_id", "invoice_id", "customer_id", "id"]
    fallback = [col for col in fallback_priority if col in df.columns]
    if fallback:
        return fallback
    return []


def _coerce_types(df, schema_blueprint):
    notes = []
    df = df.copy()
    for col, meta in schema_blueprint.items():
        if col not in df.columns:
            continue

        intended = meta.get("intended_type", "string")
        try:
            if intended in ("float", "int"):
                before_nulls = df[col].isna().sum()
                df[col] = pd.to_numeric(df[col], errors="coerce")
                new_nulls = int(df[col].isna().sum() - before_nulls)
                if new_nulls > 0:
                    notes.append(f"{col}: {new_nulls} values could not be cast to {intended} -> NaN")
                if intended == "int" and df[col].isna().sum() == 0:
                    df[col] = df[col].astype(int)
            elif intended == "datetime":
                df[col] = pd.to_datetime(df[col], errors="coerce")
                notes.append(f"{col}: coerced to datetime")
            elif intended == "boolean":
                df[col] = df[col].map(
                    lambda x: True if str(x).strip().lower() in ("true", "1", "yes")
                    else False if str(x).strip().lower() in ("false", "0", "no")
                    else np.nan
                )
                notes.append(f"{col}: coerced to boolean")
            elif intended in ("category", "string"):
                df[col] = _normalize_missing_text(df[col])
        except Exception as e:
            notes.append(f"{col}: coercion failed - {e}")

    return df, notes


def _clean_currency_values(df, schema_blueprint, config, ledger=None):
    notes = []
    critical_errors = []

    for col, meta in schema_blueprint.items():
        if col not in df.columns:
            continue
        if meta.get("semantic_tag") != "currency":
            continue
        if meta.get("intended_type") not in ("float", "int"):
            notes.append(
                f"{col}: currency tag detected but intended_type={meta.get('intended_type')} -> skipped numeric currency parsing"
            )
            continue

        original_series = df[col]
        original_nulls = int(original_series.isna().sum())
        before_null_pct = (original_nulls / max(len(df), 1)) * 100

        working = original_series.astype("string").str.strip()
        working = working.str.replace(r"^\((.+)\)$", r"-\1", regex=True)
        working = working.str.replace(r"[₹$€£¥₩\s]", "", regex=True)
        working = working.str.replace(r"^Rs\.?", "", regex=True)

        has_comma = working.str.contains(",", na=False)
        working.loc[has_comma] = (
            working.loc[has_comma]
            .str.replace(r"\.(?=\d{3})", "", regex=True)
            .str.replace(",", ".", regex=False)
        )
        working = working.str.replace(",", "", regex=False)

        parsed = pd.to_numeric(working, errors="coerce")
        parse_failed_mask = original_series.notna() & parsed.isna()
        parse_failed_col = f"{col}_parse_failed"

        df[col] = parsed
        df[parse_failed_col] = parse_failed_mask.astype(int)

        new_nulls = int(parsed.isna().sum())
        after_null_pct = (new_nulls / max(len(df), 1)) * 100
        failed_count = int(parse_failed_mask.sum())
        failed_pct = (failed_count / max(len(df), 1)) * 100
        
        notes.append(
            f"{col}: currency cleaned, {new_nulls} unparseable values -> NaN, "
            f"{failed_count} failures flagged in [{parse_failed_col}]"
        )
        
        if ledger:
            ledger.record_column_action(col, "currency_clean", before_null_pct, after_null_pct, "multi-currency formats")
            if failed_count > 0:
                ledger.record_parse_failure(col, failed_pct, failed_count)

        if parsed.notna().sum() == 0:
            critical_errors.append(
                f"Agent3: CRITICAL currency parse assertion failed for [{col}] - column is 100% null"
            )
            continue

        max_abs = float(parsed.abs().max(skipna=True))
        if np.isfinite(max_abs) and max_abs > config["currency_max_abs_value"]:
            critical_errors.append(
                f"Agent3: CRITICAL currency plausibility assertion failed for [{col}] "
                f"(max abs {max_abs:.2f})"
            )

    return df, notes, critical_errors


def _standardize_text_columns(df, schema_blueprint):
    notes = []
    for col, meta in schema_blueprint.items():
        if col not in df.columns:
            continue
        if meta.get("intended_type") not in ("string", "category"):
            continue
        if meta.get("is_identifier"):
            continue

        # Canonicalize category-like text to avoid split groups from casing or separators.
        if meta.get("canonicalize_text", True):
            df[col] = _canonicalize_text_values(df[col])
            notes.append(
                f"{col}: text standardized (null normalization + separator cleanup + case canonicalization)"
            )
        else:
            text_series = _normalize_missing_text(df[col])
            if meta.get("text_case_strategy") == "title":
                df[col] = text_series.str.title()
                notes.append(f"{col}: text standardized (strip + title-case + null normalization)")
                continue

            df[col] = text_series
            notes.append(f"{col}: text standardized (strip + null normalization)")

    return df, notes


def _remove_duplicates(df, schema_blueprint):
    before = len(df)
    key_cols = _resolve_business_keys(df, schema_blueprint)

    if key_cols:
        df = df.drop_duplicates(subset=key_cols).reset_index(drop=True)
    else:
        df = df.drop_duplicates().reset_index(drop=True)

    return df, before - len(df), key_cols


def _impute(df, schema_blueprint):
    notes = []
    df = df.copy()
    rows_before = len(df)
    drop_mask = pd.Series([False] * len(df), index=df.index)

    for col, meta in schema_blueprint.items():
        if col not in df.columns:
            continue

        strategy = meta.get("imputation_strategy", "none")
        missing_count = int(df[col].isna().sum())
        if missing_count == 0:
            continue

        try:
            if strategy == "mean":
                fill_value = df[col].mean()
                if pd.isna(fill_value):
                    notes.append(f"{col}: mean imputation skipped (all values missing/non-numeric)")
                    continue
                df[col] = df[col].fillna(fill_value)
                notes.append(f"{col}: imputed {missing_count} NaNs with mean ({fill_value:.4f})")
            elif strategy == "median":
                fill_value = df[col].median()
                if pd.isna(fill_value):
                    notes.append(f"{col}: median imputation skipped (all values missing/non-numeric)")
                    continue
                df[col] = df[col].fillna(fill_value)
                notes.append(f"{col}: imputed {missing_count} NaNs with median ({fill_value:.4f})")
            elif strategy == "mode":
                mode_val = df[col].mode()
                if len(mode_val) > 0:
                    df[col] = df[col].fillna(mode_val[0])
                    notes.append(f"{col}: imputed {missing_count} NaNs with mode ({mode_val[0]})")
                else:
                    notes.append(f"{col}: mode imputation skipped (no valid mode)")
            elif strategy == "unknown_label":
                df[col] = df[col].fillna("Unknown")
                notes.append(f"{col}: imputed {missing_count} NaNs with 'Unknown'")
            elif strategy == "drop":
                drop_mask = drop_mask | df[col].isna()
                notes.append(f"{col}: {missing_count} rows flagged for drop (identifier NaN)")
            elif strategy == "none":
                notes.append(f"{col}: {missing_count} NaNs left as-is (strategy=none)")
            else:
                notes.append(f"{col}: unknown strategy '{strategy}' - skipped")
        except Exception as e:
            notes.append(f"{col}: imputation failed - {e}")

    if drop_mask.any():
        df = df[~drop_mask].reset_index(drop=True)
        notes.append(f"Dropped {rows_before - len(df)} rows with missing identifier values")

    return df, notes


def _clip_outliers(df, schema_blueprint, ledger=None):
    notes = []
    critical_errors = []
    df = df.copy()

    for col, meta in schema_blueprint.items():
        if col not in df.columns:
            continue
        if not meta.get("scaling_allowed", False):
            continue
        if meta.get("is_identifier", False):
            continue
        if meta.get("intended_type") not in ("float", "int"):
            continue

        numeric_col = pd.to_numeric(df[col], errors="coerce")
        q1 = numeric_col.quantile(0.25)
        q3 = numeric_col.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            notes.append(f"{col}: outlier clipping skipped (zero IQR)")
            continue

        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        clipped = int(((numeric_col < lower) | (numeric_col > upper)).sum())
        df[col] = numeric_col.clip(lower=lower, upper=upper)
        notes.append(f"{col}: IQR clipping (lower={lower:.3f}, upper={upper:.3f}), {clipped} values clipped")
        
        if ledger:
            ledger.record_clip_bounds(col, lower, upper)

        # Post-step assertion.
        non_null = df[col].dropna()
        if not non_null.empty:
            actual_min = float(non_null.min())
            actual_max = float(non_null.max())
            if ledger:
                ledger.record_clip_post_bounds(col, actual_min, actual_max)
            if actual_min < lower - 1e-9 or actual_max > upper + 1e-9:
                critical_errors.append(
                    f"Agent3: CRITICAL clipping assertion failed for [{col}] "
                    f"(min={actual_min:.4f}, max={actual_max:.4f}, bounds={lower:.4f}..{upper:.4f})"
                )

    return df, notes, critical_errors


def _scale_columns(df, schema_blueprint):
    notes = []
    scaling_params = {}
    df = df.copy()

    for col, meta in schema_blueprint.items():
        if col not in df.columns:
            continue
        if not meta.get("scaling_allowed", False):
            continue
        if meta.get("is_identifier", False):
            continue
        if meta.get("semantic_tag") in ("currency", "datetime", "identifier"):
            continue
        if meta.get("intended_type") not in ("float", "int"):
            continue
        if _is_count_field(col, meta):
            notes.append(f"{col}: scaling skipped (count field)")
            continue

        raw_col = f"{col}_raw"
        scaled_col = f"{col}_scaled"
        if raw_col not in df.columns:
            df[raw_col] = df[col]

        col_min = df[col].min()
        col_max = df[col].max()
        if col_max == col_min:
            notes.append(f"{col}: scaling skipped (constant column)")
            continue

        df[scaled_col] = (df[col] - col_min) / (col_max - col_min)
        # Preserve backward compatibility for downstream code expecting the original name.
        df[col] = df[scaled_col]

        scaling_params[col] = {
            "min": float(col_min),
            "max": float(col_max),
            "raw_col": raw_col,
            "scaled_col": scaled_col,
        }
        notes.append(
            f"{col}: Min-Max scaled in [{scaled_col}] with raw backup [{raw_col}] "
            f"(min={col_min:.4f}, max={col_max:.4f})"
        )

    return df, scaling_params, notes


def _extract_date_features(df, schema_blueprint):
    notes = []
    for col, meta in schema_blueprint.items():
        if col not in df.columns:
            continue
        if meta.get("semantic_tag") != "datetime":
            continue

        try:
            dt = pd.to_datetime(df[col], errors="coerce")
            df[f"{col}_year"] = dt.dt.year
            df[f"{col}_month"] = dt.dt.month
            df[f"{col}_quarter"] = dt.dt.quarter
            df[f"{col}_day"] = dt.dt.day
            df[f"{col}_day_of_week"] = dt.dt.dayofweek
            df[f"{col}_is_weekend"] = (dt.dt.dayofweek >= 5).astype(int)
            df[f"{col}_week_of_year"] = dt.dt.isocalendar().week.astype("Int64")
            notes.append(f"{col}: extracted year, month, quarter, day, day_of_week, is_weekend, week_of_year")
        except Exception as e:
            notes.append(f"{col}: date feature extraction failed - {e}")

    return df, notes


def _find_col(df, keywords):
    """Whole-word keyword matching; prevents accidental substring matches."""
    for col in df.columns:
        col_lower = col.lower()
        for kw in keywords:
            if re.search(rf"\b{re.escape(kw)}\b", col_lower):
                return col
    return None


def _is_numeric_col(df, col):
    """Returns True only if 80%+ of column values are numeric."""
    if col is None or col not in df.columns:
        return False
    numeric_check = pd.to_numeric(df[col], errors="coerce")
    return numeric_check.notna().sum() / max(len(df), 1) >= 0.8


def _derive_business_metrics(df):
    notes = []

    rev_col = _find_col(df, ["revenue", "sales", "income", "total_amount", "net_sales"])
    cost_col = _find_col(df, ["cost_price", "cost", "expense", "cogs", "expenditure"])
    unit_col = _find_col(df, ["units_sold", "units", "quantity", "qty", "volume"])
    price_col = _find_col(df, ["unit_price", "price", "rate", "mrp", "selling_price"])
    discount_col = _find_col(df, ["discount_amount", "discount", "rebate", "deduction"])
    budget_col = _find_col(df, ["budget", "target", "planned", "projected"])
    tax_col = _find_col(df, ["tax_amount", "tax", "vat", "gst", "duty"])
    ship_col = _find_col(df, ["shipping", "freight", "delivery_cost", "logistics"])

    rev_col = rev_col if _is_numeric_col(df, rev_col) else None
    cost_col = cost_col if _is_numeric_col(df, cost_col) else None
    unit_col = unit_col if _is_numeric_col(df, unit_col) else None
    price_col = price_col if _is_numeric_col(df, price_col) else None
    discount_col = discount_col if _is_numeric_col(df, discount_col) else None
    budget_col = budget_col if _is_numeric_col(df, budget_col) else None
    tax_col = tax_col if _is_numeric_col(df, tax_col) else None
    ship_col = ship_col if _is_numeric_col(df, ship_col) else None

    for col in [rev_col, cost_col, unit_col, price_col, discount_col, budget_col, tax_col, ship_col]:
        if col and col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if rev_col and cost_col:
        df["derived_profit"] = df[rev_col] - df[cost_col]
        df["derived_profit_margin_pct"] = (df["derived_profit"] / df[rev_col].replace(0, np.nan)) * 100
        notes.append(f"Derived: profit and profit_margin_pct from [{rev_col}] - [{cost_col}]")

    if rev_col and unit_col:
        df["derived_revenue_per_unit"] = df[rev_col] / df[unit_col].replace(0, np.nan)
        notes.append(f"Derived: revenue_per_unit from [{rev_col}] / [{unit_col}]")

    if not rev_col and price_col and unit_col:
        df["derived_total_revenue"] = df[price_col] * df[unit_col]
        notes.append(f"Derived: total_revenue from [{price_col}] * [{unit_col}]")

    if rev_col and discount_col:
        df["derived_revenue_after_discount"] = df[rev_col] - df[discount_col]
        df["derived_discount_pct"] = (df[discount_col] / df[rev_col].replace(0, np.nan)) * 100
        notes.append(f"Derived: revenue_after_discount and discount_pct from [{rev_col}] and [{discount_col}]")

    if rev_col and budget_col:
        df["derived_budget_variance"] = df[rev_col] - df[budget_col]
        df["derived_budget_variance_pct"] = (df["derived_budget_variance"] / df[budget_col].replace(0, np.nan)) * 100
        notes.append(f"Derived: budget_variance and variance_pct from [{rev_col}] and [{budget_col}]")

    if cost_col and tax_col and ship_col:
        df["derived_total_cost"] = df[cost_col] + df[tax_col] + df[ship_col]
        notes.append(f"Derived: total_cost from [{cost_col}] + [{tax_col}] + [{ship_col}]")
    elif cost_col and tax_col:
        df["derived_total_cost_with_tax"] = df[cost_col] + df[tax_col]
        notes.append(f"Derived: total_cost_with_tax from [{cost_col}] + [{tax_col}]")

    if not notes:
        notes.append("Derived metrics: no matching column pairs found")

    return df, notes


def _validate_count_ranges(df, schema_blueprint, ledger=None):
    notes = []
    checks = 0
    failed_rows = 0

    for col, meta in schema_blueprint.items():
        if col not in df.columns or not _is_count_field(col, meta):
            continue

        numeric = pd.to_numeric(df[col], errors="coerce")
        valid = numeric.notna()
        negative_mask = valid & (numeric < 0)
        non_int_mask = valid & (np.floor(numeric) != numeric)
        violation_mask = negative_mask | non_int_mask
        flag_col = f"{col}_range_failed"
        df[flag_col] = violation_mask.astype(int)

        checks += int(valid.sum())
        col_failed = int(violation_mask.sum())
        failed_rows += col_failed
        notes.append(f"{col}: count-range validation -> {col_failed} rows flagged in [{flag_col}]")
        
        if ledger and col_failed > 0:
            pct = (col_failed / max(len(df), 1)) * 100
            ledger.record_range_failure(col, pct, col_failed)
            ledger.record_validation_failure(f"{col}_range_failed", col_failed, len(df))

    return df, notes, {"checks": checks, "failed_rows": failed_rows}


def _validate_financial_constraints(df, config, ledger=None):
    notes = []
    checks = 0
    failed_rows = 0

    amount_col = _find_col(df, ["amount", "revenue", "sales", "subtotal"])
    tax_col = _find_col(df, ["tax_amount", "tax", "vat", "gst"])
    discount_col = _find_col(df, ["discount_amount", "discount", "rebate", "deduction"])
    total_col = _find_col(df, ["total_amount", "grand_total", "invoice_total"])
    margin_col = _find_col(df, ["profit_margin", "derived_profit_margin_pct"])

    if amount_col and tax_col:
        amount = pd.to_numeric(df[amount_col], errors="coerce")
        tax = pd.to_numeric(df[tax_col], errors="coerce")
        valid = amount.notna() & tax.notna() & (amount != 0)
        fail_mask = valid & (tax > amount.abs() * config["max_reasonable_tax_rate"])
        flag_col = f"{tax_col}_rate_failed"
        df[flag_col] = fail_mask.astype(int)
        checks += int(valid.sum())
        col_failed = int(fail_mask.sum())
        failed_rows += col_failed
        notes.append(f"Tax-rate validation [{tax_col}] vs [{amount_col}]: {col_failed} rows flagged")
        if ledger and col_failed > 0:
            pct = (col_failed / max(len(df), 1)) * 100
            ledger.record_range_failure(tax_col, pct, col_failed)
            ledger.record_validation_failure(f"{tax_col}_rate_failed", col_failed, len(df))

    if amount_col and total_col:
        amount = pd.to_numeric(df[amount_col], errors="coerce")
        total = pd.to_numeric(df[total_col], errors="coerce")
        tax_series = pd.to_numeric(df[tax_col], errors="coerce") if tax_col else 0.0
        discount_series = pd.to_numeric(df[discount_col], errors="coerce") if discount_col else 0.0
        expected = amount + tax_series - discount_series
        tol = np.maximum(config["reconciliation_abs_tol"], expected.abs() * config["reconciliation_rel_tol"])
        valid = expected.notna() & total.notna()
        fail_mask = valid & ((total - expected).abs() > tol)
        flag_col = f"{total_col}_reconciliation_failed"
        df[flag_col] = fail_mask.astype(int)
        checks += int(valid.sum())
        col_failed = int(fail_mask.sum())
        failed_rows += col_failed
        notes.append(f"Total reconciliation [{total_col}]: {col_failed} rows flagged")
        if ledger and col_failed > 0:
            pct = (col_failed / max(len(df), 1)) * 100
            ledger.record_validation_failure(f"{total_col}_reconciliation_failed", col_failed, len(df))

    if margin_col:
        margin = pd.to_numeric(df[margin_col], errors="coerce")
        valid = margin.notna()
        if margin_col.endswith("_pct"):
            fail_mask = valid & ((margin < -100) | (margin > 100))
        else:
            fail_mask = valid & ((margin < -1) | (margin > 1))
        flag_col = f"{margin_col}_range_failed"
        df[flag_col] = fail_mask.astype(int)
        checks += int(valid.sum())
        col_failed = int(fail_mask.sum())
        failed_rows += col_failed
        notes.append(f"Profit-margin range validation [{margin_col}]: {col_failed} rows flagged")
        if ledger and col_failed > 0:
            pct = (col_failed / max(len(df), 1)) * 100
            ledger.record_validation_failure(f"{margin_col}_range_failed", col_failed, len(df))

    return df, notes, {"checks": checks, "failed_rows": failed_rows}


def _compute_quality_score(df_raw, df_clean, validation_summary, config):
    raw_total_cells = df_raw.shape[0] * df_raw.shape[1]
    clean_total_cells = df_clean.shape[0] * df_clean.shape[1]

    raw_completeness = 1 - (df_raw.isna().sum().sum() / max(raw_total_cells, 1))
    remaining_null_pct = round((df_clean.isna().sum().sum() / max(clean_total_cells, 1)) * 100, 2)
    duplicate_rate_pct = round((df_raw.duplicated().sum() / max(len(df_raw), 1)) * 100, 2)

    total_checks = max(validation_summary.get("checks", 0), 1)
    validation_fail_pct = round((validation_summary.get("failed_rows", 0) / total_checks) * 100, 2)

    weights = config.get("quality_weights", PREPROCESSING_PROFILES[DEFAULT_PROFILE]["quality_weights"])
    # Score is driven by post-hoc failures, not by number of executed steps.
    score = (
        100.0
        - (weights.get("remaining_null_pct", 0.50) * remaining_null_pct)
        - (weights.get("validation_fail_pct", 0.40) * validation_fail_pct)
        - (weights.get("duplicate_rate_pct", 0.10) * duplicate_rate_pct)
    )

    null_pct_by_column = {
        col: round((df_clean[col].isna().sum() / max(len(df_clean), 1)) * 100, 2)
        for col in df_clean.columns
    }

    return {
        "overall_quality_score": max(0.0, min(100.0, round(score, 2))),
        "raw_completeness_pct": round(raw_completeness * 100, 2),
        "remaining_null_pct": remaining_null_pct,
        "duplicate_rate_pct": duplicate_rate_pct,
        "validation_fail_pct": validation_fail_pct,
        "null_pct_by_column": null_pct_by_column,
        "rows_before": int(df_raw.shape[0]),
        "rows_after": int(df_clean.shape[0]),
        "rows_removed": int(df_raw.shape[0] - df_clean.shape[0]),
        "columns_before": int(df_raw.shape[1]),
        "columns_after": int(df_clean.shape[1]),
    }


def _export_cleaned_dataset(df, output_path="outputs/cleaned_data.csv"):
    """Persist cleaned DataFrame to CSV and return (path, error)."""
    try:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output, index=False)
        return str(output), None
    except Exception as e:
        return "", f"Failed to export cleaned dataset CSV: {e}"


def _early_exit_with_error(state, errors, preprocessing_log, message):
    errors.append(message)
    return {
        **state,
        "cleaned_df": None,
        "cleaned_csv_path": "",
        "preprocessing_log": preprocessing_log,
        "errors": errors,
    }


def agent3_preprocessor(state: GraphState) -> GraphState:
    errors = state.get("errors", [])
    schema_blueprint = state.get("schema_blueprint", {})
    df = state.get("_df_cache")

    if df is None:
        errors.append("Agent3: No DataFrame in state. Agent 1 or 2 failed.")
        return {**state, "errors": errors}

    if not schema_blueprint:
        errors.append("Agent3: schema_blueprint is empty. Agent 2 failed.")
        return {**state, "errors": errors}

    preprocessing_config, selected_profile, dataset_domain = _build_preprocessing_config(
        state.get("preprocessing_config"),
        state.get("preprocessing_profile"),
        schema_blueprint,
    )

    df_raw = df.copy()
    preprocessing_log = []
    validation_summary = {"checks": 0, "failed_rows": 0}
    ledger = ColumnLedger()
    verbose = _verbose_logging_enabled()

    print(
        f"[Agent 3] Preprocessing: profile={selected_profile} domain={dataset_domain} "
        f"input={df.shape[0]}x{df.shape[1]}"
    )

    # Step 1: currency cleanup + strict assertions.
    before_step = df.copy()
    df, notes, critical_errors = _clean_currency_values(df, schema_blueprint, preprocessing_config, ledger)
    preprocessing_log.extend(notes)
    preprocessing_log.extend(_log_null_diff(before_step, df, "Step 1"))
    if verbose:
        print(f"[Agent 3] Step 1 - Currency cleaning done ({len(notes)} columns)")
    if critical_errors:
        return _early_exit_with_error(state, errors, preprocessing_log, "; ".join(critical_errors))

    before_step = df.copy()
    df, notes = _coerce_types(df, schema_blueprint)
    preprocessing_log.extend(notes)
    preprocessing_log.extend(_log_null_diff(before_step, df, "Step 2"))
    if verbose:
        print(f"[Agent 3] Step 2 - Type coercion done ({len(notes)} actions)")

    before_step = df.copy()
    df, notes = _standardize_text_columns(df, schema_blueprint)
    preprocessing_log.extend(notes)
    preprocessing_log.extend(_log_null_diff(before_step, df, "Step 3"))
    if verbose:
        print(f"[Agent 3] Step 3 - Text standardization done ({len(notes)} columns)")

    # Deduplicate before imputation/scaling, using business keys when available.
    before_step = df.copy()
    df, dupes_removed, dedup_keys = _remove_duplicates(df, schema_blueprint)
    if dedup_keys:
        preprocessing_log.append(f"Duplicate removal: {dupes_removed} rows removed using business keys {dedup_keys}")
    else:
        preprocessing_log.append(f"Duplicate removal: {dupes_removed} rows removed using full-row match")
    preprocessing_log.extend(_log_null_diff(before_step, df, "Step 4"))
    if verbose:
        print(f"[Agent 3] Step 4 - Duplicates removed: {dupes_removed}")

    before_step = df.copy()
    df, notes = _impute(df, schema_blueprint)
    preprocessing_log.extend(notes)
    preprocessing_log.extend(_log_null_diff(before_step, df, "Step 5"))
    if verbose:
        print(f"[Agent 3] Step 5 - Imputation done ({len(notes)} actions)")

    before_step = df.copy()
    df, notes, critical_errors = _clip_outliers(df, schema_blueprint, ledger)
    preprocessing_log.extend(notes)
    preprocessing_log.extend(_log_null_diff(before_step, df, "Step 6"))
    if verbose:
        print(f"[Agent 3] Step 6 - Outlier clipping done ({len(notes)} columns)")
    if critical_errors:
        return _early_exit_with_error(state, errors, preprocessing_log, "; ".join(critical_errors))

    before_step = df.copy()
    df, scaling_params, notes = _scale_columns(df, schema_blueprint)
    preprocessing_log.extend(notes)
    preprocessing_log.extend(_log_null_diff(before_step, df, "Step 7"))
    if verbose:
        print(f"[Agent 3] Step 7 - Scaling done ({len(scaling_params)} columns)")

    before_step = df.copy()
    df, notes = _extract_date_features(df, schema_blueprint)
    preprocessing_log.extend(notes)
    preprocessing_log.extend(_log_null_diff(before_step, df, "Step 8"))
    if verbose:
        print(f"[Agent 3] Step 8 - Date features extracted ({len(notes)} datetime columns)")

    # Derived metrics are computed only after upstream columns are finalized.
    before_step = df.copy()
    df, notes = _derive_business_metrics(df)
    preprocessing_log.extend(notes)
    preprocessing_log.extend(_log_null_diff(before_step, df, "Step 9"))
    if verbose:
        print(f"[Agent 3] Step 9 - Business metrics derived ({len(notes)} metrics)")

    df, count_validation_notes, count_validation = _validate_count_ranges(df, schema_blueprint, ledger)
    preprocessing_log.extend(count_validation_notes)
    validation_summary["checks"] += count_validation["checks"]
    validation_summary["failed_rows"] += count_validation["failed_rows"]

    df, financial_validation_notes, financial_validation = _validate_financial_constraints(df, preprocessing_config, ledger)
    preprocessing_log.extend(financial_validation_notes)
    validation_summary["checks"] += financial_validation["checks"]
    validation_summary["failed_rows"] += financial_validation["failed_rows"]

    data_quality = _compute_quality_score(df_raw, df, validation_summary, preprocessing_config)
    preprocessing_log.append(
        f"Data quality score: {data_quality['overall_quality_score']}/100 "
        f"(remaining_nulls={data_quality['remaining_null_pct']}%, "
        f"validation_fail={data_quality['validation_fail_pct']}%, "
        f"duplicates={data_quality['duplicate_rate_pct']}%)"
    )
    if verbose:
        print(f"[Agent 3] Step 10 - Quality score: {data_quality['overall_quality_score']}/100")

    final_missing = int(df.isna().sum().sum())
    preprocessing_log.append(
        f"Final shape: {df.shape[0]} rows x {df.shape[1]} cols | Remaining NaNs: {final_missing}"
    )
    print(
        f"[Agent 3] Completed: rows={df_raw.shape[0]}->{df.shape[0]} "
        f"cols={df_raw.shape[1]}->{df.shape[1]} "
        f"quality={data_quality['overall_quality_score']}/100 "
        f"remaining_nulls={data_quality['remaining_null_pct']}%"
    )

    cleaned_csv_path, export_error = _export_cleaned_dataset(df)
    if export_error:
        errors.append(f"Agent3: {export_error}")
        preprocessing_log.append(f"CSV export failed: {export_error}")
    else:
        preprocessing_log.append(f"Cleaned CSV exported to {cleaned_csv_path}")
        if verbose:
            print(f"[Agent 3] Cleaned CSV exported -> {cleaned_csv_path}")

    return {
        **state,
        "cleaned_df": df,
        "cleaned_csv_path": cleaned_csv_path,
        "scaling_params": scaling_params,
        "preprocessing_log": preprocessing_log,
        "preprocessing_config": preprocessing_config,
        "preprocessing_profile": selected_profile,
        "dataset_domain": dataset_domain,
        "data_quality": data_quality,
        "column_ledger": {
            "columns": ledger.columns,
            "clip_bounds": ledger.clip_bounds,
            "clip_post_bounds": ledger.clip_post_bounds,
            "validation_failures": ledger.validation_failures,
        },
        "errors": errors,
    }
