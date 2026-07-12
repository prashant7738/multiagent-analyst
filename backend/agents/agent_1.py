"""Agent 1: structural profiling for CSV inputs.

This module reads a CSV file, gathers row/column shape information,
computes missingness and duplication metrics, and records lightweight
format hints that later agents can use for semantic inference.
"""

import csv
from io import StringIO
import re
import warnings

import numpy as np
import pandas as pd
import json
from main import GraphState


warnings.filterwarnings('ignore', category=UserWarning)


def _read_csv_lines(csv_path: str) -> list[str]:
    """Read CSV text using a small set of common encodings.

    The pipeline is expected to handle user-provided files from different
    sources, so we try a short list of common encodings before failing.
    """
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
    """Read CSV files that mix comma- and semicolon-delimited rows.

    Some real-world exports switch delimiters across rows. This reader uses
    the header row as the schema anchor and normalizes the rest into a single
    DataFrame.
    """
    lines = _read_csv_lines(csv_path)

    if not lines:
        return pd.DataFrame()

    header = next(csv.reader([lines[0]], delimiter=",", quotechar='"'))
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


def _parseability_pct(series: pd.Series, parser) -> float:
    """Return the share of non-null values that a parser can coerce."""
    non_null = series.dropna()
    if non_null.empty:
        return 0.0

    try:
        parsed = parser(non_null)
    except Exception:
        return 0.0

    return round((parsed.notna().sum() / len(non_null)) * 100, 2)


def _extract_format_hints(series: pd.Series) -> dict:
    """Infer a few lightweight hints from sample values.

    These are intentionally heuristic and are meant to help later agents
    distinguish likely currency, date, and identifier columns.
    """
    samples = [str(value).strip() for value in series.dropna().head(10).tolist()]
    if not samples:
        return {
            "currency_like": False,
            "date_like": False,
            "identifier_like": False,
        }

    currency_like = any(re.search(r"[₹$€£¥₩]", sample) or re.search(r"\b(?:rs|usd|eur|gbp|inr)\b", sample, re.I) for sample in samples)
    date_like = any(re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", sample) or re.search(r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", sample) for sample in samples)
    identifier_like = any(
        re.search(r"\b(?:id|uuid|key|code|no|num)\b", sample, re.I)
        for sample in samples
    )

    return {
        "currency_like": bool(currency_like),
        "date_like": bool(date_like),
        "identifier_like": bool(identifier_like),
    }


def _analyze_column_distribution(series: pd.Series) -> dict:
    """Analyze distribution shape, skewness, and normality for one column."""
    non_null = series.dropna()
    if len(non_null) < 10:
        return {
            "skewness": 0.0,
            "kurtosis": 0.0,
            "is_normal_distribution": False,
            "is_normal": False,
            "distribution_type": "insufficient_data",
        }

    numeric = pd.to_numeric(non_null, errors="coerce").dropna()
    if len(numeric) < 3:
        return {
            "skewness": 0.0,
            "kurtosis": 0.0,
            "is_normal_distribution": False,
            "is_normal": False,
            "distribution_type": "not_numeric",
        }

    mean = float(np.mean(numeric))
    std = float(np.std(numeric, ddof=0))
    skewness = float(np.mean(((numeric - mean) / std) ** 3)) if std else 0.0
    kurt = float(np.mean(((numeric - mean) / std) ** 4) - 3) if std else 0.0

    is_normal = False
    if len(numeric) <= 5000:
        is_normal = abs(skewness) < 0.5 and abs(kurt) < 1
    else:
        is_normal = abs(skewness) < 0.5 and abs(kurt) < 1

    if is_normal:
        distribution_type = "normal"
    elif skewness > 0.5:
        distribution_type = "right_skewed"
    elif skewness < -0.5:
        distribution_type = "left_skewed"
    else:
        distribution_type = "symmetric"

    return {
        "skewness": round(skewness, 3),
        "kurtosis": round(kurt, 3),
        "is_normal_distribution": is_normal,
        "is_normal": is_normal,
        "distribution_type": distribution_type,
    }


def _detect_implicit_missingness(df: pd.DataFrame) -> dict:
    """Find sentinel values and common textual placeholders for missing data."""
    implicit_patterns = {}

    for col in df.columns:
        series = df[col]
        implicit_flags = []

        if pd.api.types.is_numeric_dtype(series):
            numeric = pd.to_numeric(series, errors="coerce")
            total = len(numeric)
            if total > 0:
                for sentinel in [-1, -999, 9999, 0, 99999, 999999]:
                    count = int((numeric == sentinel).sum())
                    if count > 0 and (count / total) > 0.005:
                        implicit_flags.append({
                            "sentinel": sentinel,
                            "count": count,
                            "pct": round((count / total) * 100, 2),
                            "recommendation": "treat as missing value",
                        })

        if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
            stripped = series.astype("string").str.strip()
            total = len(stripped)
            if total > 0:
                for pattern in ["0000-00-00", "1900-01-01", "n/a", "none", "null", "na", ""]:
                    count = int((stripped.str.casefold() == pattern).sum())
                    if count > 0 and (count / total) > 0.005:
                        implicit_flags.append({
                            "pattern": pattern,
                            "count": count,
                            "pct": round((count / total) * 100, 2),
                            "recommendation": "treat as missing value",
                        })

        if implicit_flags:
            implicit_patterns[col] = implicit_flags

    return implicit_patterns


def _detect_potential_outliers(series: pd.Series) -> dict:
    """Detect potential outliers using IQR and z-score heuristics."""
    non_null = series.dropna()
    if len(non_null) < 10:
        return {}

    numeric = pd.to_numeric(non_null, errors="coerce").dropna()
    if len(numeric) < 4:
        return {}

    q1 = numeric.quantile(0.25)
    q3 = numeric.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0:
        return {
            "outlier_count": 0,
            "iqr_outlier_count": 0,
            "iqr_outlier_pct": 0.0,
            "z_score_outlier_count": 0,
            "z_score_outlier_pct": 0.0,
            "iqr_bounds": {"lower": float(q1), "upper": float(q3)},
            "has_significant_outliers": False,
            "method": "iqr",
            "note": "zero IQR - likely constant column",
        }

    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    iqr_mask = (numeric < lower_bound) | (numeric > upper_bound)
    iqr_outliers = int(iqr_mask.sum())

    std = float(np.std(numeric, ddof=0))
    if std > 0:
        z_scores = np.abs((numeric - float(np.mean(numeric))) / std)
        z_outliers = int(np.sum(np.asarray(z_scores) > 3))
    else:
        z_outliers = 0

    return {
        "outlier_count": int(max(iqr_outliers, z_outliers)),
        "iqr_outlier_count": int(iqr_outliers),
        "iqr_outlier_pct": round((iqr_outliers / len(numeric)) * 100, 2),
        "z_score_outlier_count": int(z_outliers),
        "z_score_outlier_pct": round((z_outliers / len(numeric)) * 100, 2),
        "iqr_bounds": {"lower": float(lower_bound), "upper": float(upper_bound)},
        "has_significant_outliers": bool(iqr_outliers > max(5, len(numeric) * 0.05)),
        "method": "iqr_and_zscore",
    }


def _detect_column_relationships(df: pd.DataFrame, column_profiles: dict) -> dict:
    """Find candidate keys, duplicate columns, and strong numeric correlations."""
    relationships = {
        "potential_keys": [],
        "high_cardinality_text": [],
        "numeric_correlations": [],
        "suspicious_duplicates": [],
    }

    total_rows = max(len(df), 1)

    for col, profile in column_profiles.items():
        if profile.get("cardinality_ratio", 0) > 0.98 and profile.get("missing_count", 0) == 0:
            relationships["potential_keys"].append(col)

        if pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col]):
            unique_count = int(profile.get("unique_count", df[col].nunique(dropna=False)))
            if unique_count > total_rows * 0.9:
                relationships["high_cardinality_text"].append({
                    "column": col,
                    "unique_count": unique_count,
                    "uniqueness_pct": round((unique_count / total_rows) * 100, 1),
                    "likely_identifier": True,
                })

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if len(numeric_cols) >= 2:
        corr_matrix = df[numeric_cols].corr()
        for index, col1 in enumerate(numeric_cols):
            for col2 in numeric_cols[index + 1:]:
                corr_val = corr_matrix.loc[col1, col2]
                if pd.notna(corr_val) and abs(float(corr_val)) > 0.95:
                    relationships["numeric_correlations"].append({
                        "col1": col1,
                        "col2": col2,
                        "correlation": round(float(abs(corr_val)), 3),
                        "warning": "highly correlated - may indicate redundancy or multicollinearity",
                    })

    columns = list(df.columns)
    for index, col1 in enumerate(columns):
        for col2 in columns[index + 1:]:
            if df[col1].equals(df[col2]):
                relationships["suspicious_duplicates"].append({
                    "col1": col1,
                    "col2": col2,
                    "reason": "columns contain identical values",
                })

    return relationships

def agent1_structural_profiler(state: GraphState) -> GraphState:
    """
    Load the CSV, compute structural metrics, and stash the DataFrame in state.

    This agent is observation-only: it does not clean, coerce, or mutate the
    input data. Its job is to produce the metadata that downstream agents use.
    """
    csv_path = state["csv_path"]
    errors = state.get("errors", [])

    try:
        df = _read_mixed_delimiter_csv(csv_path)
    except Exception as e:
        errors.append(f"Agent1: CSV load failed — {e}")
        return {**state, "errors": errors}

    total_cells = df.shape[0] * df.shape[1]

    # Per-column profile
    column_profiles = {}
    for col in df.columns:
        missing_count = int(df[col].isna().sum())
        non_null_count = int(df[col].notna().sum())
        unique_count = int(df[col].nunique(dropna=False))
        unique_non_null_count = int(df[col].nunique(dropna=True))
        cardinality_ratio = round(unique_count / max(df.shape[0], 1), 4)
        unique_non_null_ratio = round(unique_non_null_count / max(non_null_count, 1), 4) if non_null_count > 0 else 0.0
        candidate_key_score = round(unique_non_null_ratio * (1 - (missing_count / max(df.shape[0], 1))), 4)

        numeric_parseability_pct = 0.0
        datetime_parseability_pct = 0.0
        if pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col]):
            numeric_parseability_pct = _parseability_pct(df[col], lambda s: pd.to_numeric(s, errors="coerce"))
            datetime_parseability_pct = _parseability_pct(df[col], lambda s: pd.to_datetime(s, errors="coerce"))

        format_hints = _extract_format_hints(df[col])
        column_profiles[col] = {
            "dtype": str(df[col].dtype),
            "missing_count": missing_count,
            "missing_rate_pct": round(missing_count / len(df) * 100, 2) if len(df) > 0 else 0,
            "unique_count": unique_count,
            "unique_non_null_count": unique_non_null_count,
            "cardinality_ratio": cardinality_ratio,
            "candidate_key_score": candidate_key_score,
            "candidate_key_hint": candidate_key_score >= 0.98 and missing_count == 0,
            "parseability": {
                "numeric_pct": numeric_parseability_pct,
                "datetime_pct": datetime_parseability_pct,
            },
            "format_hints": format_hints,
            "sample_values": df[col].dropna().head(3).tolist(),
        }

    duplicate_rows = int(df.duplicated().sum())

    distribution_analysis = {}
    implicit_missing = _detect_implicit_missingness(df)
    relationships = _detect_column_relationships(df, column_profiles)

    for col in df.columns:
        distribution_analysis[col] = _analyze_column_distribution(df[col])
        if pd.api.types.is_numeric_dtype(df[col]):
            column_profiles[col]["outlier_analysis"] = _detect_potential_outliers(df[col])

    raw_profile = {
        "shape": {"rows": df.shape[0], "cols": df.shape[1]},
        "total_cells": total_cells,
        "total_missing": int(df.isna().sum().sum()),
        "overall_missing_rate_pct": round(df.isna().sum().sum() / total_cells * 100, 2) if total_cells > 0 else 0,
        "duplicate_rows": duplicate_rows,
        "duplicate_rate_pct": round(duplicate_rows / df.shape[0] * 100, 2) if df.shape[0] > 0 else 0,
        "distribution_analysis": distribution_analysis,
        "implicit_missing_values": implicit_missing,
        "column_relationships": relationships,
        "columns": column_profiles,
    }

    print(f"[Agent 1] Profiled: {df.shape[0]} rows × {df.shape[1]} cols | "
          f"Missing: {raw_profile['overall_missing_rate_pct']}% | "
          f"Duplicates: {duplicate_rows}")

    # Keep the parsed DataFrame in state so Agent 2 can reuse it without
    # reopening the CSV and repeating delimiter/encoding detection.
    return {
        **state,
        "raw_profile": raw_profile,
        "_df_cache": df,
        "errors": errors,
    }