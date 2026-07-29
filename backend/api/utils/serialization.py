"""JSON-safe serialization helpers.

The pipeline's ``GraphState`` contains pandas DataFrames, numpy scalars,
timestamps, and other objects that are not JSON-serializable. These helpers
convert arbitrary agent output into primitives a frontend can consume, and
never leak raw DataFrames over the wire.
"""

from __future__ import annotations

import math
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# GraphState keys that must never be serialized directly (heavy / non-JSON).
_EXCLUDED_STATE_KEYS = {"_df_cache", "cleaned_df"}


def json_safe(value: Any) -> Any:
    """Recursively convert ``value`` into JSON-serializable primitives."""
    if value is None:
        return None

    if isinstance(value, (str, bool, int)):
        return value

    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value

    if isinstance(value, (np.integer,)):
        return int(value)

    if isinstance(value, (np.floating,)):
        f = float(value)
        return None if (math.isnan(f) or math.isinf(f)) else f

    if isinstance(value, (np.bool_,)):
        return bool(value)

    if isinstance(value, (np.ndarray,)):
        return [json_safe(v) for v in value.tolist()]

    if isinstance(value, (datetime, date, pd.Timestamp)):
        try:
            return value.isoformat()
        except Exception:
            return str(value)

    if isinstance(value, pd.Timedelta):
        return str(value)

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]

    if isinstance(value, pd.Series):
        return {str(k): json_safe(v) for k, v in value.to_dict().items()}

    if isinstance(value, pd.DataFrame):
        # Guardrail: summarize rather than dumping a whole frame.
        return {
            "__dataframe__": True,
            "shape": {"rows": int(value.shape[0]), "cols": int(value.shape[1])},
            "columns": [str(c) for c in value.columns],
        }

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    return str(value)


def dataframe_summary(df: Any) -> dict[str, Any]:
    """Return a compact, JSON-safe summary of a DataFrame (never the rows)."""
    if not isinstance(df, pd.DataFrame):
        return {}
    return {
        "rows": int(df.shape[0]),
        "cols": int(df.shape[1]),
        "columns": [str(c) for c in df.columns],
    }


def chart_url(path: str) -> dict[str, str]:
    """Convert an agent chart path into a frontend URL under ``/plots``."""
    filename = os.path.basename(str(path))
    return {"name": filename, "url": f"/plots/{filename}"}
