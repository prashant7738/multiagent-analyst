import re
import pandas as pd
import numpy as np
from agents.agent_1 import GraphState


NULL_STRINGS = {
    "nan", "none", "null", "n/a", "na", "-", "", "unknown",
    "not available", "not applicable", "nil", "#n/a", "nan ",
}


def _normalize_missing_text(series):
    """Normalize common textual null markers while preserving true missing values."""
    trimmed = series.astype("string").str.strip()
    normalized = trimmed.str.casefold()
    return trimmed.mask(normalized.isin(NULL_STRINGS), pd.NA)


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
                    notes.append(f"{col}: {new_nulls} values could not be cast to {intended} → NaN")
                if intended == "int" and df[col].isna().sum() == 0:
                    df[col] = df[col].astype(int)
            elif intended == "datetime":
                df[col] = pd.to_datetime(df[col], errors="coerce")
                notes.append(f"{col}: coerced to datetime")
            elif intended == "boolean":
                df[col] = df[col].map(
                    lambda x: True  if str(x).strip().lower() in ("true",  "1", "yes")
                         else False if str(x).strip().lower() in ("false", "0", "no")
                         else np.nan
                )
                notes.append(f"{col}: coerced to boolean")
            elif intended in ("category", "string"):
                df[col] = _normalize_missing_text(df[col])
        except Exception as e:
            notes.append(f"{col}: coercion failed — {e}")
    return df, notes


def _clean_currency_values(df, schema_blueprint):
    notes = []
    for col, meta in schema_blueprint.items():
        if col not in df.columns:
            continue
        if meta.get("semantic_tag") != "currency":
            continue
        original_nulls = int(df[col].isna().sum())
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].str.replace(r'^\((.+)\)$', r'-\1', regex=True)
        df[col] = df[col].str.replace(r'[₹$€£¥₩\s]', '', regex=True)
        df[col] = df[col].str.replace(r'^Rs\.?', '', regex=True)
        mask = df[col].str.contains(',', na=False)
        df.loc[mask, col] = (
            df.loc[mask, col]
            .str.replace(r'\.(?=\d{3})', '', regex=True)
            .str.replace(',', '.', regex=False)
        )
        df[col] = df[col].str.replace(',', '', regex=False)
        df[col] = pd.to_numeric(df[col], errors="coerce")
        new_nulls = int(df[col].isna().sum()) - original_nulls
        notes.append(
            f"{col}: currency symbols cleaned"
            + (f", {new_nulls} unparseable values → NaN" if new_nulls > 0 else "")
        )
    return df, notes


def _standardize_text_columns(df, schema_blueprint):
    notes = []
    for col, meta in schema_blueprint.items():
        if col not in df.columns:
            continue
        if meta.get("intended_type") not in ("string", "category"):
            continue
        if meta.get("is_identifier"):
            continue
        text_series = _normalize_missing_text(df[col])

        # Title-casing is opt-in because it can corrupt acronyms/brand names.
        if meta.get("text_case_strategy") == "title":
            df[col] = text_series.str.title()
            notes.append(f"{col}: text standardized (stripped, title-cased, null strings → NaN)")
        else:
            df[col] = text_series
            notes.append(f"{col}: text standardized (stripped, null strings → NaN)")
    return df, notes


def _remove_duplicates(df):
    before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    return df, before - len(df)


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
                notes.append(f"{col}: unknown strategy '{strategy}' — skipped")
        except Exception as e:
            notes.append(f"{col}: imputation failed — {e}")
    if drop_mask.any():
        df = df[~drop_mask].reset_index(drop=True)
        notes.append(f"Dropped {rows_before - len(df)} rows with missing identifier values")
    return df, notes


def _clip_outliers(df, schema_blueprint):
    notes = []
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
        Q1  = numeric_col.quantile(0.25)
        Q3  = numeric_col.quantile(0.75)
        IQR = Q3 - Q1
        if IQR == 0:
            notes.append(f"{col}: outlier clipping skipped (zero IQR)")
            continue
        lower = Q1 - 1.5 * IQR
        upper = Q3 + 1.5 * IQR
        clipped = int(((numeric_col < lower) | (numeric_col > upper)).sum())
        df[col] = numeric_col.clip(lower=lower, upper=upper)
        notes.append(f"{col}: IQR clipping (lower={lower:.3f}, upper={upper:.3f}), {clipped} values clipped")
    return df, notes


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
        col_min = df[col].min()
        col_max = df[col].max()
        if col_max == col_min:
            notes.append(f"{col}: scaling skipped (constant column)")
            continue
        df[col] = (df[col] - col_min) / (col_max - col_min)
        scaling_params[col] = {"min": float(col_min), "max": float(col_max)}
        notes.append(f"{col}: Min-Max scaled (min={col_min:.4f}, max={col_max:.4f})")
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
            df[f"{col}_year"]         = dt.dt.year
            df[f"{col}_month"]        = dt.dt.month
            df[f"{col}_quarter"]      = dt.dt.quarter
            df[f"{col}_day"]          = dt.dt.day
            df[f"{col}_day_of_week"]  = dt.dt.dayofweek
            df[f"{col}_is_weekend"]   = (dt.dt.dayofweek >= 5).astype(int)
            df[f"{col}_week_of_year"] = dt.dt.isocalendar().week.astype("Int64")
            notes.append(f"{col}: extracted year, month, quarter, day, day_of_week, is_weekend, week_of_year")
        except Exception as e:
            notes.append(f"{col}: date feature extraction failed — {e}")
    return df, notes


def _find_col(df, keywords):
    """Whole-word keyword matching — prevents 'count' matching 'Country'."""
    for col in df.columns:
        col_lower = col.lower()
        for kw in keywords:
            if re.search(rf'\b{re.escape(kw)}\b', col_lower):
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

    rev_col      = _find_col(df, ["revenue", "sales", "income", "total_amount", "net_sales"])
    cost_col     = _find_col(df, ["cost_price", "cost", "expense", "cogs", "expenditure"])
    unit_col     = _find_col(df, ["units_sold", "units", "quantity", "qty", "volume"])
    price_col    = _find_col(df, ["unit_price", "price", "rate", "mrp", "selling_price"])
    discount_col = _find_col(df, ["discount", "rebate", "deduction"])
    budget_col   = _find_col(df, ["budget", "target", "planned", "projected"])
    tax_col      = _find_col(df, ["tax", "vat", "gst", "duty"])
    ship_col     = _find_col(df, ["shipping", "freight", "delivery_cost", "logistics"])

    # Verify every detected column is actually numeric before doing math
    rev_col      = rev_col      if _is_numeric_col(df, rev_col)      else None
    cost_col     = cost_col     if _is_numeric_col(df, cost_col)     else None
    unit_col     = unit_col     if _is_numeric_col(df, unit_col)     else None
    price_col    = price_col    if _is_numeric_col(df, price_col)    else None
    discount_col = discount_col if _is_numeric_col(df, discount_col) else None
    budget_col   = budget_col   if _is_numeric_col(df, budget_col)   else None
    tax_col      = tax_col      if _is_numeric_col(df, tax_col)      else None
    ship_col     = ship_col     if _is_numeric_col(df, ship_col)     else None

    # Force numeric on verified columns only — never touches string columns
    for col in [rev_col, cost_col, unit_col, price_col,
                discount_col, budget_col, tax_col, ship_col]:
        if col and col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if rev_col and cost_col:
        df["derived_profit"] = df[rev_col] - df[cost_col]
        df["derived_profit_margin_pct"] = (
            df["derived_profit"] / df[rev_col].replace(0, np.nan)
        ) * 100
        notes.append(f"Derived: profit and profit_margin_pct from [{rev_col}] - [{cost_col}]")

    if rev_col and unit_col:
        df["derived_revenue_per_unit"] = df[rev_col] / df[unit_col].replace(0, np.nan)
        notes.append(f"Derived: revenue_per_unit from [{rev_col}] / [{unit_col}]")

    if not rev_col and price_col and unit_col:
        df["derived_total_revenue"] = df[price_col] * df[unit_col]
        notes.append(f"Derived: total_revenue from [{price_col}] × [{unit_col}]")

    if rev_col and discount_col:
        df["derived_revenue_after_discount"] = df[rev_col] - df[discount_col]
        df["derived_discount_pct"] = (
            df[discount_col] / df[rev_col].replace(0, np.nan)
        ) * 100
        notes.append(f"Derived: revenue_after_discount and discount_pct from [{rev_col}] and [{discount_col}]")

    if rev_col and budget_col:
        df["derived_budget_variance"] = df[rev_col] - df[budget_col]
        df["derived_budget_variance_pct"] = (
            df["derived_budget_variance"] / df[budget_col].replace(0, np.nan)
        ) * 100
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


def _compute_quality_score(df_raw, df_clean):
    total_cells  = df_raw.shape[0] * df_raw.shape[1]
    completeness = 1 - (df_raw.isna().sum().sum() / max(total_cells, 1))
    dup_penalty  = df_raw.duplicated().sum() / max(len(df_raw), 1)
    score        = round((completeness - dup_penalty) * 100, 2)
    return {
        "overall_quality_score": max(0.0, min(100.0, score)),
        "raw_completeness_pct":  round(completeness * 100, 2),
        "duplicate_rate_pct":    round(dup_penalty * 100, 2),
        "rows_before":           int(df_raw.shape[0]),
        "rows_after":            int(df_clean.shape[0]),
        "rows_removed":          int(df_raw.shape[0] - df_clean.shape[0]),
        "columns_before":        int(df_raw.shape[1]),
        "columns_after":         int(df_clean.shape[1]),
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

    df_raw = df.copy()
    preprocessing_log = []
    print(f"[Agent 3] Starting preprocessing: {df.shape[0]} rows × {df.shape[1]} cols")

    # Clean semantic currency fields before generic numeric coercion.
    df, notes = _clean_currency_values(df, schema_blueprint)
    preprocessing_log.extend(notes)
    print(f"[Agent 3] Step 1 — Currency cleaning done ({len(notes)} columns)")

    df, notes = _coerce_types(df, schema_blueprint)
    preprocessing_log.extend(notes)
    print(f"[Agent 3] Step 2 — Type coercion done ({len(notes)} actions)")

    df, notes = _standardize_text_columns(df, schema_blueprint)
    preprocessing_log.extend(notes)
    print(f"[Agent 3] Step 3 — Text standardization done ({len(notes)} columns)")

    df, dupes_removed = _remove_duplicates(df)
    preprocessing_log.append(f"Duplicate removal: {dupes_removed} rows removed")
    print(f"[Agent 3] Step 4 — Duplicates removed: {dupes_removed}")

    df, notes = _impute(df, schema_blueprint)
    preprocessing_log.extend(notes)
    print(f"[Agent 3] Step 5 — Imputation done ({len(notes)} actions)")

    df, notes = _clip_outliers(df, schema_blueprint)
    preprocessing_log.extend(notes)
    print(f"[Agent 3] Step 6 — Outlier clipping done ({len(notes)} columns)")

    df, scaling_params, notes = _scale_columns(df, schema_blueprint)
    preprocessing_log.extend(notes)
    print(f"[Agent 3] Step 7 — Scaling done ({len(scaling_params)} columns)")

    df, notes = _extract_date_features(df, schema_blueprint)
    preprocessing_log.extend(notes)
    print(f"[Agent 3] Step 8 — Date features extracted ({len(notes)} datetime columns)")

    df, notes = _derive_business_metrics(df)
    preprocessing_log.extend(notes)
    print(f"[Agent 3] Step 9 — Business metrics derived ({len(notes)} metrics)")

    data_quality = _compute_quality_score(df_raw, df)
    preprocessing_log.append(
        f"Data quality score: {data_quality['overall_quality_score']}/100 "
        f"(completeness={data_quality['raw_completeness_pct']}%, "
        f"duplicates={data_quality['duplicate_rate_pct']}%)"
    )
    print(f"[Agent 3] Step 10 — Quality score: {data_quality['overall_quality_score']}/100")

    final_missing = int(df.isna().sum().sum())
    preprocessing_log.append(
        f"Final shape: {df.shape[0]} rows × {df.shape[1]} cols | Remaining NaNs: {final_missing}"
    )
    print(f"[Agent 3] Done → {df.shape[0]} rows × {df.shape[1]} cols | Remaining NaNs: {final_missing}")

    return {
        **state,
        "cleaned_df":        df,
        "scaling_params":    scaling_params,
        "preprocessing_log": preprocessing_log,
        "data_quality":      data_quality,
        "errors":            errors,
    }