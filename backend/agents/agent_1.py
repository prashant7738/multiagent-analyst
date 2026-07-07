# agents/agent_1  -- --- ----structural_profiler.py
import csv
from io import StringIO

import pandas as pd
import json
from main import GraphState


def _read_mixed_delimiter_csv(csv_path: str) -> pd.DataFrame:
    """Read CSV files that mix comma- and semicolon-delimited rows."""
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as handle:
        lines = [line.rstrip("\n") for line in handle]

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
        column_profiles[col] = {
            "dtype": str(df[col].dtype),
            "missing_count": missing_count,
            "missing_rate_pct": round(missing_count / len(df) * 100, 2) if len(df) > 0 else 0,
            "unique_count": int(df[col].nunique(dropna=False)),
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