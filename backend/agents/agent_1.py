# agents/agent_1  -- --- ----structural_profiler.py
import csv
from io import StringIO
import re

import pandas as pd
import json
from main import GraphState


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
    non_null = series.dropna()
    if non_null.empty:
        return 0.0

    try:
        parsed = parser(non_null)
    except Exception:
        return 0.0

    return round((parsed.notna().sum() / len(non_null)) * 100, 2)


def _extract_format_hints(series: pd.Series) -> dict:
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

def agent1_structural_profiler(state: GraphState) -> GraphState:
    """
    Reads CSV. Records shape, dtypes, missing values, duplicates.
    No fixing. No inference. Just observe and record.
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

    raw_profile = {
        "shape": {"rows": df.shape[0], "cols": df.shape[1]},
        "total_cells": total_cells,
        "total_missing": int(df.isna().sum().sum()),
        "overall_missing_rate_pct": round(df.isna().sum().sum() / total_cells * 100, 2) if total_cells > 0 else 0,
        "duplicate_rows": duplicate_rows,
        "duplicate_rate_pct": round(duplicate_rows / df.shape[0] * 100, 2) if df.shape[0] > 0 else 0,
        "columns": column_profiles,
    }

    print(f"[Agent 1] Profiled: {df.shape[0]} rows × {df.shape[1]} cols | "
          f"Missing: {raw_profile['overall_missing_rate_pct']}% | "
          f"Duplicates: {duplicate_rows}")

    # Store df in state for Agent 2 (avoid reloading CSV downstream)
    return {
        **state,
        "raw_profile": raw_profile,
        "_df_cache": df,  # internal, agents share via state
        "errors": errors,
    }