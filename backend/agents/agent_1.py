# agents/agent_1  -- --- ----structural_profiler.py
import csv
import os
from io import StringIO

import numpy as np
import pandas as pd
import json
from main import GraphState, update_reliability

# ---------------------------------------------------------------------------
# Sentinel / null-string catalogues
# ---------------------------------------------------------------------------
_NUMERIC_SENTINELS: frozenset[float] = frozenset({
    -999, -9999, -99, -9, -1, 0,
    999, 9999, 99999, -99999,
    -99.0, -999.0, -9999.0,
})

_TEXT_NULL_PATTERNS: frozenset[str] = frozenset({
    "n/a", "na", "none", "null", "missing", "unknown", "#n/a",
    "nil", "-", ".", "?", "n.a.", "not available", "not applicable",
    "nan", "undefined",
})


# ---------------------------------------------------------------------------
# Distribution analysis
# ---------------------------------------------------------------------------

def _analyze_column_distribution(series: pd.Series) -> dict:
    """Return skewness, a distribution type label, and a normality flag.

    Distribution types returned:
      - ``right_skewed``  — positive skewness > 1
      - ``normal``        — near-normal (|skewness| <= 0.5 and |excess kurtosis| <= 1)
      - ``symmetric``     — everything else (incl. mildly left-skewed)
    """
    s = series.dropna()
    if len(s) < 3:
        return {"skewness": 0.0, "distribution_type": "symmetric", "is_normal_distribution": False}

    skewness = float(s.skew())
    excess_kurtosis = float(s.kurt())  # Fisher's definition (0 for normal)

    is_normal = bool(abs(skewness) <= 0.5 and abs(excess_kurtosis) <= 1.0)

    if is_normal:
        dist_type = "normal"
    elif skewness > 1.0:
        dist_type = "right_skewed"
    else:
        dist_type = "symmetric"

    return {
        "skewness": round(skewness, 4),
        "distribution_type": dist_type,
        "is_normal_distribution": is_normal,
    }


# ---------------------------------------------------------------------------
# Implicit missingness detection
# ---------------------------------------------------------------------------

def _detect_implicit_missingness(df: pd.DataFrame) -> dict:
    """Return per-column flags for values that encode missingness implicitly.

    For numeric columns: checks a catalogue of common sentinel values (-999 …).
    For text columns: checks a catalogue of null-string patterns ("n/a" …).

    Only columns that have at least one suspect value appear in the result.
    Each entry is a list of dicts:
      - numeric sentinel: ``{"sentinel": -999, "count": 3}``
      - text pattern:     ``{"pattern": "n/a",  "count": 2}``
    """
    result: dict[str, list] = {}

    for col in df.columns:
        flags: list[dict] = []
        series = df[col]

        if pd.api.types.is_numeric_dtype(series):
            for sentinel in _NUMERIC_SENTINELS:
                # Avoid false positives for 0 unless it appears disproportionately
                if sentinel == 0:
                    zero_pct = float((series == 0).sum()) / max(len(series), 1)
                    if zero_pct < 0.25:
                        continue
                count = int((series == sentinel).sum())
                if count > 0:
                    flags.append({"sentinel": float(sentinel), "count": count})
        elif series.dtype == object or str(series.dtype) == "string":
            lower_vals = series.dropna().astype(str).str.lower().str.strip()
            for pattern in _TEXT_NULL_PATTERNS:
                count = int((lower_vals == pattern).sum())
                if count > 0:
                    flags.append({"pattern": pattern, "count": count})

        if flags:
            result[col] = flags

    return result


# ---------------------------------------------------------------------------
# Column relationship detection
# ---------------------------------------------------------------------------

def _detect_column_relationships(df: pd.DataFrame, profiles: dict) -> dict:
    """Detect candidate keys, identical-column pairs, and strong numeric correlations.

    Returns a dict with:
      - ``potential_keys``:       list of column names whose values are entirely unique.
      - ``suspicious_duplicates``: list of ``{col1, col2}`` pairs with identical data.
      - ``numeric_correlations``:  list of ``{col1, col2, r}`` for |r| >= 0.5.
    """
    n = len(df)
    potential_keys: list[str] = []
    for col in df.columns:
        prof = profiles.get(col, {})
        unique_count = int(prof.get("unique_count", 0))
        missing_count = int(prof.get("missing_count", 0))
        if unique_count == n and missing_count == 0 and n > 0:
            potential_keys.append(col)

    suspicious_duplicates: list[dict] = []
    cols = list(df.columns)
    for i, c1 in enumerate(cols):
        for c2 in cols[i + 1:]:
            try:
                if df[c1].equals(df[c2]):
                    suspicious_duplicates.append({"col1": c1, "col2": c2})
            except Exception:
                pass

    numeric_cols = [
        c for c in df.columns
        if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])
    ]
    numeric_correlations: list[dict] = []
    if len(numeric_cols) >= 2:
        try:
            corr = df[numeric_cols].corr()
            for i, c1 in enumerate(numeric_cols):
                for c2 in numeric_cols[i + 1:]:
                    r = corr.loc[c1, c2]
                    if not pd.isna(r) and abs(r) >= 0.5:
                        numeric_correlations.append({"col1": c1, "col2": c2, "r": round(float(r), 4)})
        except Exception:
            pass

    return {
        "potential_keys": potential_keys,
        "suspicious_duplicates": suspicious_duplicates,
        "numeric_correlations": numeric_correlations,
    }


def _read_csv_lines(csv_path: str) -> list[str]:
    """Read CSV text using a small set of common encodings."""
    encodings = ("utf-8-sig", "cp1252", "latin-1")

    last_error = None
    for encoding in encodings:
        try:
            with open(csv_path, "r", encoding=encoding, newline="") as handle:
                return [line.rstrip("\n") for line in handle]
        except UnicodeDecodeError as error:
            last_error = error

    raise UnicodeDecodeError(
        last_error.encoding if last_error else "utf-8",
        last_error.object if last_error else b"",
        last_error.start if last_error else 0,
        last_error.end if last_error else 0,
        f"Unable to decode CSV using {', '.join(encodings)}"
    )


def _read_mixed_delimiter_csv(csv_path: str) -> pd.DataFrame:
    """Read CSV files that mix comma- and semicolon-delimited rows."""
    lines = _read_csv_lines(csv_path)

    if not lines:
        return pd.DataFrame()

    # Detect header delimiter (same logic as data rows)
    header_delimiter = ";" if lines[0].count(";") > lines[0].count(",") else ","
    header = next(csv.reader([lines[0]], delimiter=header_delimiter, quotechar='"'))
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)

    for line in lines[1:]:
        if not line.strip():
            continue

        delimiter = ";" if line.count(";") > line.count(",") else ","
        fields = next(csv.reader([line], delimiter=delimiter, quotechar='"'))

        if len(fields) != len(header):
            alternate = "," if delimiter == ";" else ";"
            alt_fields = next(csv.reader([line], delimiter=alternate, quotechar='"'))
            if len(alt_fields) == len(header):
                fields = alt_fields
            else:
                raise ValueError(
                    f"Unable to parse row with {len(fields)} fields (expected {len(header)}): {line[:120]}"
                )

        writer.writerow(fields)

    buffer.seek(0)
    return pd.read_csv(buffer, low_memory=False)


def _read_excel_file(file_path: str, sheet_name: str | int | None = None) -> pd.DataFrame:
    """Read an Excel (.xlsx/.xlsm/.xls) file into a DataFrame.

    - If sheet_name is given, reads only that sheet.
    - If sheet_name is None and the workbook has multiple sheets, reads ALL
      sheets and concatenates them into a single DataFrame, tagging each row
      with its source sheet in a `_source_sheet` column. If the sheets don't
      share the same columns, they're still concatenated (outer join), and a
      warning is recorded in df.attrs so the caller can surface it.
    """
    try:
        xls = pd.ExcelFile(file_path)
    except Exception as e:
        raise ValueError(f"Unable to open Excel file: {e}")

    all_sheets = xls.sheet_names

    if sheet_name is not None:
        try:
            df = pd.read_excel(xls, sheet_name=sheet_name)
        except Exception as e:
            raise ValueError(f"Unable to read sheet '{sheet_name}': {e}")
        df.attrs["sheet_used"] = sheet_name
        df.attrs["all_sheets"] = all_sheets
        return df

    if len(all_sheets) == 1:
        try:
            df = pd.read_excel(xls, sheet_name=all_sheets[0])
        except Exception as e:
            raise ValueError(f"Unable to read sheet '{all_sheets[0]}': {e}")
        df.attrs["sheet_used"] = all_sheets[0]
        df.attrs["all_sheets"] = all_sheets
        return df

    # Multiple sheets, none specified: read and concatenate all of them
    frames = []
    schema_mismatch = False
    reference_columns = None
    for name in all_sheets:
        try:
            sheet_df = pd.read_excel(xls, sheet_name=name)
        except Exception as e:
            raise ValueError(f"Unable to read sheet '{name}': {e}")

        if reference_columns is None:
            reference_columns = list(sheet_df.columns)
        elif list(sheet_df.columns) != reference_columns:
            schema_mismatch = True

        sheet_df = sheet_df.copy()
        sheet_df["_source_sheet"] = name
        frames.append(sheet_df)

    df = pd.concat(frames, ignore_index=True, sort=False)
    df.attrs["sheet_used"] = "ALL (concatenated)"
    df.attrs["all_sheets"] = all_sheets
    df.attrs["schema_mismatch"] = schema_mismatch
    return df


def _read_json_file(file_path: str) -> pd.DataFrame:
    """Read a JSON file into a DataFrame.

    Tries the following orientations in order until one succeeds:
    - JSON Lines (one object per line, .jsonl / .ndjson)
    - Records list:  [{col: val, ...}, ...]
    - Columns dict:  {col: {index: val, ...}, ...}
    - Pandas default (let pandas decide)
    """
    # 1. JSON Lines (most common for large datasets)
    try:
        df = pd.read_json(file_path, lines=True)
        if not df.empty:
            return df
    except (ValueError, TypeError):
        pass

    # 2. Records / columns / pandas default
    for orient in ("records", "columns", None):
        try:
            kwargs: dict = {} if orient is None else {"orient": orient}
            df = pd.read_json(file_path, **kwargs)
            if not df.empty:
                return df
        except (ValueError, TypeError):
            continue

    raise ValueError(
        f"Unable to parse '{file_path}' as JSON. "
        "Supported formats: JSON Lines, records list, or columns dict."
    )


def _read_parquet_file(file_path: str) -> pd.DataFrame:
    """Read a Parquet file into a DataFrame using the best available engine."""
    try:
        return pd.read_parquet(file_path)
    except Exception as e:
        raise ValueError(f"Unable to read Parquet file '{file_path}': {e}") from e


def _load_dataframe(file_path: str, sheet_name: str | int | None = None) -> pd.DataFrame:
    """Dispatch to the correct reader based on file extension.

    Supported formats:
    - CSV / TSV / mixed-delimiter (default, no extension)
    - Excel: .xlsx, .xlsm, .xls
    - JSON: .json, .jsonl, .ndjson
    - Parquet: .parquet, .pq
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext in (".xlsx", ".xlsm", ".xls"):
        return _read_excel_file(file_path, sheet_name=sheet_name)
    elif ext in (".json", ".jsonl", ".ndjson"):
        return _read_json_file(file_path)
    elif ext in (".parquet", ".pq"):
        return _read_parquet_file(file_path)
    else:
        # CSV / TSV / missing extension — use the robust mixed-delimiter reader
        return _read_mixed_delimiter_csv(file_path)


def _compute_agent1_confidence(raw_profile: dict, df: pd.DataFrame) -> tuple[float, list[str]]:
    overall_missing = float(raw_profile.get("overall_missing_rate_pct", 0.0))
    duplicate_rate = float(raw_profile.get("duplicate_rate_pct", 0.0))
    rows = int(df.shape[0]) if df is not None else 0
    confidence = round(
        min(1.0, max(0.0, 1.0 - (overall_missing / 100.0) * 0.5 - (duplicate_rate / 100.0) * 0.3)),
        3,
    )
    evidence = [
        f"rows={rows}",
        f"missing_rate_pct={overall_missing}",
        f"duplicate_rate_pct={duplicate_rate}",
    ]
    return confidence, evidence


def agent1_structural_profiler(state: GraphState) -> GraphState:
    """
    Reads CSV, Excel (.xlsx/.xlsm/.xls), JSON/JSON-Lines, or Parquet.
    Records shape, dtypes, missing values, duplicates.
    No fixing. No inference. Just observe and record.
    """
    csv_path = state["csv_path"]
    sheet_name = state.get("sheet_name")  # optional: caller can pin a specific sheet
    errors = state.get("errors", [])

    try:
        df = _load_dataframe(csv_path, sheet_name=sheet_name)
    except Exception as e:
        errors.append(f"Agent1: File load failed — {e}")
        return {**state, "errors": errors}

    total_cells = df.shape[0] * df.shape[1]

    # Per-column profile
    column_profiles = {}
    for col in df.columns:
        missing_count = int(df[col].isna().sum())
        unique_count = int(df[col].nunique(dropna=False))
        cardinality_ratio = unique_count / len(df) if len(df) > 0 else 0.0
        candidate_key_hint = bool(cardinality_ratio >= 0.95 and missing_count == 0 and len(df) > 1)

        # Outlier analysis (IQR) for numeric columns
        if pd.api.types.is_numeric_dtype(df[col]) and not pd.api.types.is_bool_dtype(df[col]):
            s = df[col].dropna()
            if len(s) >= 4:
                q1, q3 = float(s.quantile(0.25)), float(s.quantile(0.75))
                iqr = q3 - q1
                lb, ub = q1 - 1.5 * iqr, q3 + 1.5 * iqr
                outlier_count = int(((df[col] < lb) | (df[col] > ub)).sum())
                outlier_analysis = {
                    "method": "IQR",
                    "lower_bound": round(lb, 4),
                    "upper_bound": round(ub, 4),
                    "outlier_count": outlier_count,
                    "outlier_pct": round(outlier_count / len(df) * 100, 2) if len(df) > 0 else 0.0,
                    "has_significant_outliers": outlier_count > 0,
                }
            else:
                outlier_analysis = {"method": "IQR", "outlier_count": 0, "has_significant_outliers": False}
        else:
            outlier_analysis = {"method": "none", "outlier_count": 0, "has_significant_outliers": False}

        column_profiles[col] = {
            "dtype": str(df[col].dtype),
            "missing_count": missing_count,
            "missing_rate_pct": round(missing_count / len(df) * 100, 2) if len(df) > 0 else 0,
            "unique_count": unique_count,
            "sample_values": df[col].dropna().head(3).tolist(),
            "candidate_key_hint": candidate_key_hint,
            "outlier_analysis": outlier_analysis,
        }

    duplicate_rows = int(df.duplicated().sum())

    # Dataset-level enrichments
    distribution_analysis: dict[str, dict] = {}
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]) and not pd.api.types.is_bool_dtype(df[col]):
            distribution_analysis[col] = _analyze_column_distribution(df[col])

    implicit_missing_values = _detect_implicit_missingness(df)

    column_relationships = _detect_column_relationships(df, column_profiles)

    raw_profile = {
        "shape": {"rows": df.shape[0], "cols": df.shape[1]},
        "total_cells": total_cells,
        "total_missing": int(df.isna().sum().sum()),
        "overall_missing_rate_pct": round(df.isna().sum().sum() / total_cells * 100, 2) if total_cells > 0 else 0,
        "duplicate_rows": duplicate_rows,
        "duplicate_rate_pct": round(duplicate_rows / df.shape[0] * 100, 2) if df.shape[0] > 0 else 0,
        "columns": column_profiles,
        "distribution_analysis": distribution_analysis,
        "implicit_missing_values": implicit_missing_values,
        "column_relationships": column_relationships,
    }

    # Surface Excel sheet metadata, if applicable
    sheet_used = df.attrs.get("sheet_used")
    all_sheets = df.attrs.get("all_sheets")
    schema_mismatch = df.attrs.get("schema_mismatch", False)
    if sheet_used is not None:
        raw_profile["sheet_used"] = sheet_used
    if all_sheets is not None:
        raw_profile["all_sheets"] = all_sheets
        if len(all_sheets) > 1 and sheet_name is None:
            print(f"[Agent 1] Combined {len(all_sheets)} sheets {all_sheets} into one DataFrame "
                  f"({df.shape[0]} total rows, tagged via '_source_sheet').")
            if schema_mismatch:
                errors.append(
                    f"Agent1: Sheets {all_sheets} have differing columns; concatenated with "
                    f"an outer join, so some cells may be NaN due to schema mismatch rather than "
                    f"missing source data. Pass state['sheet_name'] to read a single sheet instead."
                )

    print(f"[Agent 1] Profiled: {df.shape[0]} rows × {df.shape[1]} cols | "
          f"Missing: {raw_profile['overall_missing_rate_pct']}% | "
          f"Duplicates: {duplicate_rows}")

    confidence, evidence = _compute_agent1_confidence(raw_profile, df)
    state_with_reliability = update_reliability(
        state,
        "agent1",
        confidence,
        evidence=evidence,
        decision_readiness="ready" if confidence >= 0.8 else "needs_review",
    )

    # Store df in state for Agent 2 (avoid reloading source file downstream)
    return {
        **state_with_reliability,
        "raw_profile": raw_profile,
        "_df_cache": df,  # internal, agents share via state
        "errors": errors,
    }
