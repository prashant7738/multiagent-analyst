"""
Agent 3: Context-Aware Preprocessing Agent
-----------------------------------------
Executes the cleaning blueprint produced by Agent 2 using deterministic Python.
No LLM anywhere in this step.

Responsibilities:
  1. Type coercion  — cast columns to their intended types per blueprint
  2. Imputation     — fill missing values using blueprint-specified strategy
  3. Duplicate removal
  4. Outlier clipping — IQR-based, only on columns Agent 2 marked scaling_allowed
  5. Min-Max scaling  — only on columns Agent 2 marked scaling_allowed=True
                        (financial columns, identifiers, datetimes are skipped)
"""

import pandas as pd
import numpy as np
from main import GraphState


# ── helpers ──────────────────────────────────────────────────────────────────

def _coerce_types(df: pd.DataFrame, schema_blueprint: dict) -> tuple[pd.DataFrame, list]:
    """
    Cast each column to its intended_type from Agent 2's blueprint.
    Uncoerceable cells become NaN (handled in imputation step).

    Returns (df_coerced, coercion_notes)
    """
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
                after_nulls = df[col].isna().sum()
                new_nulls = int(after_nulls - before_nulls)
                if new_nulls > 0:
                    notes.append(f"{col}: {new_nulls} values could not be cast to {intended} → set to NaN")
                if intended == "int":
                    # only convert if no NaNs remain; int can't hold NaN in older pandas
                    if df[col].isna().sum() == 0:
                        df[col] = df[col].astype(int)

            elif intended == "datetime":
                df[col] = pd.to_datetime(df[col], errors="coerce", infer_datetime_format=True)
                notes.append(f"{col}: coerced to datetime")

            elif intended == "boolean":
                df[col] = df[col].map(
                    lambda x: True if str(x).strip().lower() in ("true", "1", "yes")
                    else (False if str(x).strip().lower() in ("false", "0", "no") else np.nan)
                )
                notes.append(f"{col}: coerced to boolean")

            elif intended == "category":
                df[col] = df[col].astype(str).str.strip()
                df[col] = df[col].replace("nan", np.nan)

            else:  # string / unknown
                df[col] = df[col].astype(str).str.strip()
                df[col] = df[col].replace("nan", np.nan)

        except Exception as e:
            notes.append(f"{col}: coercion failed — {e}")

    return df, notes


def _impute(df: pd.DataFrame, schema_blueprint: dict) -> tuple[pd.DataFrame, list]:
    """
    Fill missing values according to each column's imputation_strategy.

    Strategies from report:
      mean          → numeric columns
      median        → currency / financial columns
      mode          → categorical columns
      unknown_label → string/category columns (fills with "Unknown")
      drop          → identifier columns (rows with missing ID are dropped)
      none          → datetime columns (left as NaT)
    """
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
                df[col] = df[col].fillna(fill_value)
                notes.append(f"{col}: imputed {missing_count} NaNs with mean ({fill_value:.4f})")

            elif strategy == "median":
                fill_value = df[col].median()
                df[col] = df[col].fillna(fill_value)
                notes.append(f"{col}: imputed {missing_count} NaNs with median ({fill_value:.4f})")

            elif strategy == "mode":
                mode_val = df[col].mode()
                if len(mode_val) > 0:
                    df[col] = df[col].fillna(mode_val[0])
                    notes.append(f"{col}: imputed {missing_count} NaNs with mode ({mode_val[0]})")
                else:
                    notes.append(f"{col}: mode imputation skipped — no mode found")

            elif strategy == "unknown_label":
                df[col] = df[col].fillna("Unknown")
                notes.append(f"{col}: imputed {missing_count} NaNs with 'Unknown'")

            elif strategy == "drop":
                # Mark rows where this identifier column is null for dropping
                drop_mask = drop_mask | df[col].isna()
                notes.append(f"{col}: {missing_count} rows flagged for drop (identifier NaN)")

            elif strategy == "none":
                notes.append(f"{col}: {missing_count} NaNs left as-is (strategy=none)")

            else:
                notes.append(f"{col}: unknown strategy '{strategy}' — skipped")

        except Exception as e:
            notes.append(f"{col}: imputation failed — {e}")

    # Apply identifier row drops once
    if drop_mask.any():
        df = df[~drop_mask].reset_index(drop=True)
        dropped = rows_before - len(df)
        notes.append(f"Dropped {dropped} rows with missing identifier values")

    return df, notes


def _remove_duplicates(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    removed = before - len(df)
    return df, removed


def _clip_outliers(df: pd.DataFrame, schema_blueprint: dict) -> tuple[pd.DataFrame, list]:
    """
    IQR-based clipping ONLY on columns where Agent 2 set scaling_allowed=True.
    Identifiers, currency columns, datetimes are explicitly skipped.

    Formula from report:
      IQR   = Q3 - Q1
      Lower = Q1 - 1.5 * IQR
      Upper = Q3 + 1.5 * IQR
    """
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
        Q1 = numeric_col.quantile(0.25)
        Q3 = numeric_col.quantile(0.75)
        IQR = Q3 - Q1
        lower = Q1 - 1.5 * IQR
        upper = Q3 + 1.5 * IQR

        before_outliers = ((numeric_col < lower) | (numeric_col > upper)).sum()
        df[col] = numeric_col.clip(lower=lower, upper=upper)
        notes.append(
            f"{col}: IQR clipping applied (lower={lower:.3f}, upper={upper:.3f}), "
            f"{before_outliers} values clipped"
        )

    return df, notes


def _scale_columns(df: pd.DataFrame, schema_blueprint: dict) -> tuple[pd.DataFrame, dict, list]:
    """
    Min-Max normalization on columns where scaling_allowed=True.

    Formula from report:
      X_scaled = (X - X_min) / (X_max - X_min)

    Returns (df_scaled, scaling_params, notes)
    scaling_params is saved to state so Agent 4 can inverse-transform for display.
    """
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
            notes.append(f"{col}: scaling skipped (zero range — constant column)")
            continue

        df[col] = (df[col] - col_min) / (col_max - col_min)
        scaling_params[col] = {"min": col_min, "max": col_max}
        notes.append(f"{col}: Min-Max scaled (min={col_min:.4f}, max={col_max:.4f})")

    return df, scaling_params, notes


# ── main agent function ───────────────────────────────────────────────────────

def agent3_preprocessor(state: GraphState) -> GraphState:
    """
    Context-Aware Preprocessing Agent.

    Reads:
      state["_df_cache"]        — raw DataFrame from Agent 1
      state["schema_blueprint"] — column metadata from Agent 2

    Writes:
      state["cleaned_df"]       — fully preprocessed DataFrame
      state["preprocessing_log"] — audit log of every action taken
      state["scaling_params"]   — min/max per scaled column (for inverse transform)
      state["errors"]           — appends any agent-level errors
    """
    errors = state.get("errors", [])
    schema_blueprint = state.get("schema_blueprint", {})
    df = state.get("_df_cache")

    if df is None:
        errors.append("Agent3: No DataFrame in state. Agent 1 or 2 failed.")
        return {**state, "errors": errors}

    if not schema_blueprint:
        errors.append("Agent3: schema_blueprint is empty. Agent 2 failed.")
        return {**state, "errors": errors}

    preprocessing_log = []
    print(f"[Agent 3] Starting preprocessing: {df.shape[0]} rows × {df.shape[1]} cols")

    # ── Step 1: Type coercion ─────────────────────────────────────────────
    df, coerce_notes = _coerce_types(df, schema_blueprint)
    preprocessing_log.extend(coerce_notes)
    print(f"[Agent 3] Type coercion done ({len(coerce_notes)} actions)")

    # ── Step 2: Duplicate removal ─────────────────────────────────────────
    df, dupes_removed = _remove_duplicates(df)
    preprocessing_log.append(f"Duplicate removal: {dupes_removed} duplicate rows removed")
    print(f"[Agent 3] Duplicates removed: {dupes_removed}")

    # ── Step 3: Imputation ────────────────────────────────────────────────
    df, impute_notes = _impute(df, schema_blueprint)
    preprocessing_log.extend(impute_notes)
    print(f"[Agent 3] Imputation done ({len(impute_notes)} actions)")

    # ── Step 4: Outlier clipping (IQR) ───────────────────────────────────
    df, outlier_notes = _clip_outliers(df, schema_blueprint)
    preprocessing_log.extend(outlier_notes)
    print(f"[Agent 3] Outlier clipping done ({len(outlier_notes)} columns processed)")

    # ── Step 5: Min-Max scaling ───────────────────────────────────────────
    df, scaling_params, scale_notes = _scale_columns(df, schema_blueprint)
    preprocessing_log.extend(scale_notes)
    print(f"[Agent 3] Scaling done ({len(scaling_params)} columns scaled)")

    # ── Final shape report ────────────────────────────────────────────────
    final_missing = int(df.isna().sum().sum())
    preprocessing_log.append(
        f"Final shape: {df.shape[0]} rows × {df.shape[1]} cols | "
        f"Remaining NaNs: {final_missing}"
    )
    print(f"[Agent 3] Done → {df.shape[0]} rows × {df.shape[1]} cols | "
          f"Remaining NaNs: {final_missing}")

    return {
        **state,
        "cleaned_df": df,
        "scaling_params": scaling_params,
        "preprocessing_log": preprocessing_log,
        "errors": errors,
    }