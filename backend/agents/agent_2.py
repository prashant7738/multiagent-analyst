"""Agent 2: semantic tagging and schema blueprint generation.

This module consumes Agent 1's structural profile plus the cached DataFrame,
infers likely column semantics, optionally consults an LLM for richer schema
metadata, and falls back to metadata-only heuristics when the model is not
available or returns invalid JSON.
"""

import re
import os
import pandas as pd
import json
import numpy as np

from groq import Groq

client = None
gemini_client = None


class SchemaBlueprint(dict):
    """Dictionary wrapper that excludes internal metadata from length checks."""

    def __len__(self):
        return sum(1 for key in super().keys() if key != "__metadata__")


def _get_groq_client() -> Groq:
    """Return the active Groq client or raise a controlled error if unavailable."""
    global client
    if client is not None:
        return client

    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY is not set")

    client = Groq()
    return client


def _get_gemini_client():
    """Return the active Gemini client, importing the SDK only when needed."""
    global gemini_client
    if gemini_client is not None:
        return gemini_client

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("Gemini_API_Key") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    from google import genai

    gemini_client = genai.Client(api_key=api_key)
    return gemini_client

GROQ_MODEL = "llama-3.3-70b-versatile" 
GEMINI_MODEL = "gemini-2.5-flash"
MISSINGNESS_ANALYSIS_THRESHOLD_PCT = 20.0
LLM_BATCH_SIZE = 15
LLM_SINGLE_CALL_THRESHOLD = 20
LLM_MAX_TOKENS = 3000

_NAME_HINTS = [
    ("identifier", {"id", "identifier", "uuid", "key", "code"}),
    ("currency", {"sales", "revenue", "profit", "cost", "price", "amount", "budget", "tax", "discount", "total"}),
    ("percentage", {"percent", "pct", "rate", "margin", "ratio"}),
    ("count", {"count", "qty", "quantity", "units", "number", "num"}),
    ("geographic", {"city", "state", "country", "region", "zip", "postal", "latitude", "longitude"}),
    ("categorical_label", {"status", "segment", "category", "type", "mode", "brand", "channel", "department"}),
    ("text", {"name", "email", "address", "description", "notes", "message", "password"}),
]


def _name_tokens(column_name: str) -> set[str]:
    """Split a column name into lowercase alphanumeric tokens."""
    return set(re.findall(r"[a-z0-9]+", column_name.lower()))


def _confidence_level_from_score(score: float) -> str:
    """Convert a 0-100 confidence score into a coarse label."""
    if score >= 80:
        return "high"
    if score >= 60:
        return "medium"
    return "low"


def _calculate_semantic_confidence(
    column_name: str,
    profile: dict,
    inferred_type: str,
    semantic_tag: str,
    format_hints: dict,
) -> dict:
    """Calculate a confidence score for semantic tag inference."""
    score = 50.0
    evidence_points = []
    signal_breakdown = {}

    name_tokens = _name_tokens(column_name)
    tag_keywords = _NAME_HINTS

    name_bonus = 0.0
    if semantic_tag in tag_keywords and name_tokens & tag_keywords[semantic_tag]:
        name_bonus = 20.0
        score += name_bonus
        evidence_points.append(f"name_match: '{semantic_tag}' keyword in column name")
    signal_breakdown["name_match"] = name_bonus

    type_alignment = {
        "currency": ["numeric"],
        "datetime": ["datetime"],
        "identifier": ["string", "numeric"],
        "count": ["numeric"],
        "percentage": ["numeric"],
        "geographic": ["string"],
        "categorical_label": ["string"],
    }

    type_bonus = 0.0
    type_penalty = 0.0
    if inferred_type in type_alignment.get(semantic_tag, []):
        type_bonus = 15.0
        score += type_bonus
        evidence_points.append(f"type_alignment: {inferred_type} matches {semantic_tag}")
    elif semantic_tag in type_alignment and inferred_type not in type_alignment[semantic_tag]:
        type_penalty = 10.0
        score -= type_penalty
        evidence_points.append(f"type_mismatch: {inferred_type} does not match {semantic_tag}")
    signal_breakdown["type_alignment"] = type_bonus - type_penalty

    format_bonus = 0.0
    if semantic_tag == "currency" and format_hints.get("currency_like"):
        format_bonus += 15.0
        evidence_points.append("format_hint: currency symbols detected")
    if semantic_tag == "datetime" and format_hints.get("date_like"):
        format_bonus += 15.0
        evidence_points.append("format_hint: date patterns detected")
    if semantic_tag == "identifier" and format_hints.get("identifier_like"):
        format_bonus += 10.0
        evidence_points.append("format_hint: identifier patterns detected")
    score += format_bonus
    signal_breakdown["format_hints"] = format_bonus

    missing_rate = float(profile.get("missing_rate_pct", 0))
    unique_count = int(profile.get("unique_count", 0))
    cardinality_bonus = 0.0

    if semantic_tag == "identifier":
        if missing_rate == 0:
            cardinality_bonus += 10.0
            evidence_points.append("quality: no missing values in identifier")
        if profile.get("candidate_key_hint"):
            cardinality_bonus += 5.0
            evidence_points.append("quality: candidate key hint present")
    elif semantic_tag == "categorical_label" and 1 < unique_count < 20:
        cardinality_bonus += 10.0
        evidence_points.append(f"cardinality: {unique_count} unique values suitable for categorical")
    score += cardinality_bonus
    signal_breakdown["cardinality"] = cardinality_bonus

    penalty = 0.0
    if missing_rate > 50:
        penalty += 10.0
        evidence_points.append(f"penalty: high missingness ({missing_rate}%)")
    if profile.get("has_significant_outliers"):
        penalty += 5.0
        evidence_points.append("penalty: significant outlier signal present")
    score -= penalty
    signal_breakdown["penalties"] = -penalty

    score = max(0.0, min(100.0, round(score, 2)))
    return {
        "confidence_score": score,
        "confidence_level": _confidence_level_from_score(score),
        "evidence": evidence_points,
        "signal_breakdown": signal_breakdown,
    }


def _assess_data_quality_signals(df: pd.DataFrame, raw_profile: dict) -> dict:
    """Summarize quality risk signals that downstream preprocessing can use."""
    total_cols = max(len(df.columns), 1)
    missing_rate_pct = float(raw_profile.get("overall_missing_rate_pct", 0.0) or 0.0)
    duplicate_rate_pct = float(raw_profile.get("duplicate_rate_pct", 0.0) or 0.0)
    implicit_missing = raw_profile.get("implicit_missing_values", {}) or {}
    distribution_analysis = raw_profile.get("distribution_analysis", {}) or {}

    implicit_missing_columns = len(implicit_missing)
    significant_outlier_columns = sum(
        1
        for profile in distribution_analysis.values()
        if isinstance(profile, dict) and profile.get("has_significant_outliers")
    )

    quality_issues = []
    if missing_rate_pct >= 30:
        quality_issues.append(f"critical_missingness: {missing_rate_pct:.1f}%")
    elif missing_rate_pct >= 15:
        quality_issues.append(f"elevated_missingness: {missing_rate_pct:.1f}%")

    if duplicate_rate_pct >= 8:
        quality_issues.append(f"critical_duplication: {duplicate_rate_pct:.1f}%")
    elif duplicate_rate_pct >= 3:
        quality_issues.append(f"elevated_duplication: {duplicate_rate_pct:.1f}%")

    if implicit_missing_columns > 0:
        quality_issues.append(f"multiple_implicit_nulls: {implicit_missing_columns} columns affected")

    if significant_outlier_columns > 0:
        quality_issues.append(f"outlier_signals: {significant_outlier_columns} columns flagged")

    if missing_rate_pct >= 30 or duplicate_rate_pct >= 8 or implicit_missing_columns >= 4:
        risk_assessment = "critical"
        preprocessing_recommendation = "strict"
    elif missing_rate_pct >= 15 or duplicate_rate_pct >= 3 or significant_outlier_columns >= max(1, total_cols // 3):
        risk_assessment = "high"
        preprocessing_recommendation = "strict"
    elif missing_rate_pct >= 5 or significant_outlier_columns > 0:
        risk_assessment = "moderate"
        preprocessing_recommendation = "balanced"
    else:
        risk_assessment = "low"
        preprocessing_recommendation = "lenient"

    component_scores = {
        "completeness": round(max(0.0, 100.0 - missing_rate_pct), 2),
        "duplication": round(max(0.0, 100.0 - duplicate_rate_pct), 2),
        "implicit_missingness": round(max(0.0, 100.0 - (implicit_missing_columns * 12.5)), 2),
        "distribution_health": round(max(0.0, 100.0 - (significant_outlier_columns * 12.5)), 2),
    }

    return {
        "risk_assessment": risk_assessment,
        "preprocessing_recommendation": preprocessing_recommendation,
        "quality_issues": quality_issues,
        "component_scores": component_scores,
        "signal_counts": {
            "columns": total_cols,
            "implicit_missing_columns": implicit_missing_columns,
            "significant_outlier_columns": significant_outlier_columns,
        },
    }

SEMANTIC_SYSTEM_PROMPT = """You are a senior data analyst generating a schema blueprint for a CSV dataset.

The user message contains column metadata, inferred types, missingness rates, cardinality, and sample values.

Return ONLY one valid JSON object.
Do not return Markdown, code fences, comments, explanations, or trailing text.
Return one entry for every input column.
Use the exact input column names as JSON keys.
Do not add columns, dataset-level metadata, or a "__metadata__" key.

For each column, return exactly this structure:

{
  "column_name": {
    "intended_type": "float|int|string|datetime|boolean|category",
    "semantic_tag": "currency|identifier|datetime|geographic|physical_measurement|categorical_label|text|percentage|count|unknown",
    "is_identifier": true,
    "scaling_allowed": true,
    "imputation_strategy": "mean|median|mode|unknown_label|drop|forward_fill|knn|iterative|drop_column|none",
    "encoding_strategy": {
      "method": "one_hot|ordinal|none",
      "order": [],
      "reason": "brief reason"
    },
    "null_policy": {
            "action": "flag_only|drop_rows|impute_mean|impute_median|impute_mode|impute_unknown_label|impute_forward_fill|impute_knn|impute_iterative|drop_column|none",
      "threshold_pct": 0,
      "reason": "brief reason based on the observed missing_rate_pct"
    },
    "notes": "brief evidence-based explanation"
  }
}

Classification rules:

1. Use the supplied inferred_type as the primary type signal.
   Do not change a numeric or datetime type unless the samples clearly contradict it.

2. Use sample values, parseability, format hints, cardinality, and column names together.
   Do not classify a column from its name alone.

3. Currency and financial fields:
   - semantic_tag="currency"
   - intended_type="float" or "int"
   - scaling_allowed=false
   - imputation_strategy="none"
   - null_policy.action="flag_only"
   - Never use median, mean, mode, or unknown_label imputation for currency.
   - Preserve missing financial values for review.

4. Identifier fields:
   - is_identifier=true
   - semantic_tag="identifier"
   - scaling_allowed=false
   - imputation_strategy="drop"
   - null_policy.action="drop_rows"
   - encoding_strategy.method="none"
   - Only classify a field as an identifier when it has strong evidence such as a key-like name, near-unique values, or an explicit identifier pattern.

5. Datetime fields:
   - intended_type="datetime"
   - semantic_tag="datetime"
   - scaling_allowed=false
   - imputation_strategy="none"
   - encoding_strategy.method="none"
   - For missing dates, prefer null_policy.action="none" or "flag_only".
   - Never invent timestamps.

6. Percentage fields:
   - semantic_tag="percentage"
   - intended_type="float"
   - scaling_allowed=true unless the values are already normalized or the column is a business metric that should remain interpretable.
   - Use median imputation only when missingness is limited and the values are numeric.

7. Count fields:
   - semantic_tag="count"
   - intended_type="int" when values are whole-number counts; otherwise use "float".
   - Use median imputation only when missingness is limited and the field is numeric.
    - If the field is sequential in row order and missingness is sparse, forward fill can be appropriate.

8. Low-cardinality categorical fields:
   - If the field is a nominal label with fewer than 20 unique values:
     - semantic_tag="categorical_label"
     - encoding_strategy.method="one_hot"
     - imputation_strategy="mode" for limited missingness
   - Use ordinal encoding only when a genuine order exists and a complete explicit order list is present.
   - Never infer ordinal order from alphabetical order.

9. Geographic fields:
   - Use semantic_tag="geographic" for city, state, country, region, postal code, latitude, or longitude fields.
   - Do not scale identifiers such as postal codes.
   - Use encoding_strategy.method="none" for latitude and longitude.
   - Prefer null_policy.action="flag_only" because geographic fills often invent location meaning.

10. Free-text fields:
    - semantic_tag="text"
    - encoding_strategy.method="none"
    - Do not use one-hot encoding for descriptions, addresses, notes, messages, or other high-cardinality text.
    - Prefer null_policy.action="flag_only"; use "impute_unknown_label" only when the field is clearly categorical rather than free text.

11. Physical measurements:
    - Use semantic_tag="physical_measurement" for quantities like weight, distance, temperature, or size.
    - For limited missingness, prefer null_policy.action="impute_median".
    - For heavier missingness, prefer null_policy.action="flag_only".

12. Unknown or ambiguous fields:
    - semantic_tag="unknown"
    - scaling_allowed=false
    - encoding_strategy.method="none"
    - imputation_strategy="none"
    - null_policy.action="flag_only"
    - Explain the ambiguity in notes.

Missing-value rules:

- Use the observed missing_rate_pct from the input.
- Choose null handling from the column's semantic role and business risk, not from broad type alone.
- Choose one null_policy.action appropriate for the current column's missingness.
- Set threshold_pct to the missingness level at which the chosen policy becomes preferable.
- For 0% missingness, use action="none" and threshold_pct=0.
- For sparse or ambiguous columns, use action="flag_only".
- For columns with extremely high missingness, action="drop_column" is acceptable.
- For identifiers, use action="drop_rows".
- For low-cardinality categories with limited missingness, use action="impute_mode".
- For ordinary numeric fields with limited missingness, use action="impute_median".
- For approximately normal numeric fields with low missingness, action="impute_mean" is acceptable.
- For sequential time-series-like numeric fields with sparse gaps, action="impute_forward_fill" is acceptable.
- For numeric fields with strong correlated predictors and moderate missingness, action="impute_knn" or "impute_iterative" is acceptable.
- Never use impute_mean or impute_median for currency fields.
- The null_policy.action and imputation_strategy must be consistent:
  - flag_only       -> imputation_strategy="none"
  - drop_rows       -> imputation_strategy="drop"
  - impute_mean     -> imputation_strategy="mean"
  - impute_median   -> imputation_strategy="median"
  - impute_mode     -> imputation_strategy="mode"
  - impute_unknown_label -> imputation_strategy="unknown_label"
    - impute_forward_fill -> imputation_strategy="forward_fill"
    - impute_knn      -> imputation_strategy="knn"
    - impute_iterative -> imputation_strategy="iterative"
    - drop_column     -> imputation_strategy="drop_column"
  - none            -> imputation_strategy="none"

Encoding rules:

- Identifiers, datetimes, free text, booleans, and high-cardinality labels use method="none".
- Nominal categories with fewer than 20 unique values use method="one_hot".
- Use method="ordinal" only with a real domain order and a complete explicit order list.
- Always include a short reason for the selected encoding strategy.

Be conservative. When evidence conflicts, use semantic_tag="unknown" and flag the column instead of guessing."""


def _infer_intended_types(df: pd.DataFrame, raw_profile: dict) -> dict:
    """Pure Python type sniffing. No LLM. 80% coercion threshold."""
    inferred = {}
    for col in df.columns:
        profile = raw_profile["columns"][col]
        raw_dtype = profile["dtype"]

        if raw_dtype in ("int64", "int32", "float64", "float32"):
            inferred[col] = "numeric"
        elif raw_dtype == "bool":
            inferred[col] = "boolean"
        elif raw_dtype == "object":
            parseability = profile.get("parseability", {}) if isinstance(profile.get("parseability"), dict) else {}
            numeric_parseability_pct = float(parseability.get("numeric_pct", 0.0) or 0.0)
            datetime_parseability_pct = float(parseability.get("datetime_pct", 0.0) or 0.0)

            if numeric_parseability_pct >= 80.0:
                inferred[col] = "numeric"
            elif datetime_parseability_pct >= 80.0:
                inferred[col] = "datetime"
            else:
                inferred[col] = "string"
        elif "datetime" in raw_dtype:
            inferred[col] = "datetime"
        else:
            inferred[col] = "unknown"

    return inferred


def _json_safe_value(value):
    """Convert pandas and numpy values into JSON-serializable primitives."""
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, pd.Timedelta):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (str, int, float, bool)):
        return value
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return str(value)


def _column_correlation_summary(column_name: str, raw_profile: dict) -> dict:
    """Return strong numeric correlation partners for a column."""
    numeric_correlations = (
        raw_profile.get("column_relationships", {}).get("numeric_correlations", [])
        if isinstance(raw_profile.get("column_relationships", {}), dict)
        else []
    )
    partners = []
    max_abs_r = 0.0
    for pair in numeric_correlations:
        if not isinstance(pair, dict):
            continue
        left = pair.get("col1")
        right = pair.get("col2")
        if column_name not in {left, right}:
            continue
        partner = right if left == column_name else left
        r = float(pair.get("r", 0.0) or 0.0)
        max_abs_r = max(max_abs_r, abs(r))
        partners.append({"column": partner, "r": round(r, 4)})

    partners.sort(key=lambda item: abs(float(item.get("r", 0.0))), reverse=True)
    return {
        "max_abs_r": round(max_abs_r, 4),
        "partners": partners[:3],
    }


def _build_llm_prompt(df: pd.DataFrame, inferred_types: dict, raw_profile: dict, columns: list[str] | None = None) -> str:
    """Minimal prompt — column metadata + 3 samples only. No full CSV."""
    columns = list(df.columns) if columns is None else columns
    col_info = []
    for col in columns:
        profile = raw_profile["columns"][col]
        distribution = raw_profile.get("distribution_analysis", {}).get(col, {})
        correlation_summary = _column_correlation_summary(col, raw_profile)
        col_info.append({
            "name": col,
            "inferred_type": inferred_types[col],
            "missing_rate_pct": profile["missing_rate_pct"],
            "unique_count": profile["unique_count"],
            "samples": [_json_safe_value(value) for value in profile.get("sample_values", [])[:3]],
            "distribution_type": distribution.get("distribution_type"),
            "is_normal_distribution": distribution.get("is_normal_distribution"),
            "skewness": distribution.get("skewness"),
            "outlier_pct": profile.get("outlier_analysis", {}).get("outlier_pct"),
            "strong_numeric_correlations": correlation_summary["partners"],
        })
    return json.dumps(col_info, indent=2)


def _split_columns_into_batches(columns: list[str], batch_size: int) -> list[list[str]]:
    """Split a column list into deterministic batches for LLM requests."""
    return [columns[index:index + batch_size] for index in range(0, len(columns), batch_size)]


def _parse_schema_blueprint_response(raw_text: str) -> dict:
    """Parse a model response that may contain raw JSON or a fenced code block."""
    if "```" in raw_text:
        parts = raw_text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            try:
                return json.loads(part)
            except Exception:
                continue
        raise json.JSONDecodeError("No valid JSON block found", raw_text, 0)

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(raw_text[start:end + 1])
        raise


def _call_llm_for_schema_blueprint_with_retry(
    df: pd.DataFrame,
    inferred_types: dict,
    raw_profile: dict,
    columns: list[str],
) -> dict:
    """Call the LLM and retry with smaller batches if the response is truncated."""
    if len(columns) <= 1:
        return _call_llm_for_schema_blueprint(df, inferred_types, raw_profile, columns)

    try:
        return _call_llm_for_schema_blueprint(df, inferred_types, raw_profile, columns)
    except json.JSONDecodeError:
        midpoint = max(1, len(columns) // 2)
        left = _call_llm_for_schema_blueprint_with_retry(df, inferred_types, raw_profile, columns[:midpoint])
        right = _call_llm_for_schema_blueprint_with_retry(df, inferred_types, raw_profile, columns[midpoint:])
        merged = _merge_schema_blueprints(left, right)
        return merged


def _call_llm_for_schema_blueprint(
    df: pd.DataFrame,
    inferred_types: dict,
    raw_profile: dict,
    columns: list[str],
) -> dict:
    """Ask Groq for schema metadata, falling back to Gemini on provider failure."""
    user_prompt = _build_llm_prompt(df, inferred_types, raw_profile, columns)
    user_content = f"Produce schema blueprint for these columns:\n{user_prompt}"

    try:
        response = _get_groq_client().chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SEMANTIC_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
            max_tokens=LLM_MAX_TOKENS,
        )
        raw_text = response.choices[0].message.content.strip()
        return _parse_schema_blueprint_response(raw_text)
    except Exception as groq_error:
        print(f"[Agent 2] Groq unavailable; trying Gemini: {groq_error}")

    try:
        response = _get_gemini_client().models.generate_content(
            model=GEMINI_MODEL,
            contents=user_content,
            config={
                "system_instruction": SEMANTIC_SYSTEM_PROMPT,
                "temperature": 0.1,
                "max_output_tokens": LLM_MAX_TOKENS,
            },
        )
        raw_text = response.text.strip()
        return _parse_schema_blueprint_response(raw_text)
    except Exception as gemini_error:
        raise RuntimeError(f"Groq and Gemini calls failed: {gemini_error}") from gemini_error


def _merge_schema_blueprints(base_blueprint: dict, incoming_blueprint: dict) -> dict:
    """Merge one partial blueprint into another in place."""
    for column_name, metadata in incoming_blueprint.items():
        if column_name not in base_blueprint or not isinstance(base_blueprint[column_name], dict):
            base_blueprint[column_name] = metadata
        else:
            base_blueprint[column_name].update(metadata)
    return base_blueprint


def _infer_semantic_tag_from_metadata(column_name: str, profile: dict, inferred_type: str) -> str:
    """Infer a semantic tag from Agent 1 metadata and the column name.

    This is the main fallback when the LLM does not provide a confident tag.
    It combines column-name hints, sample values, parseability, and cardinality.
    """
    name = column_name.lower()
    tokens = _name_tokens(column_name)
    samples = [str(value).strip().lower() for value in profile.get("sample_values", []) if value is not None]
    parseability = profile.get("parseability", {}) if isinstance(profile.get("parseability"), dict) else {}
    format_hints = profile.get("format_hints", {}) if isinstance(profile.get("format_hints"), dict) else {}
    cardinality_ratio = float(profile.get("cardinality_ratio", 0.0) or 0.0)
    candidate_key_hint = bool(profile.get("candidate_key_hint", False))
    candidate_key_score = float(profile.get("candidate_key_score", 0.0) or 0.0)
    numeric_parseability_pct = float(parseability.get("numeric_pct", 0.0) or 0.0)
    datetime_parseability_pct = float(parseability.get("datetime_pct", 0.0) or 0.0)

    if inferred_type == "datetime" or datetime_parseability_pct >= 80.0 or bool(tokens & {"date", "time", "timestamp", "created", "updated"}):
        return "datetime"
    if inferred_type == "numeric" or numeric_parseability_pct >= 80.0 or format_hints.get("currency_like"):
        if bool(tokens & {"sales", "revenue", "profit", "cost", "price", "amount", "budget", "tax", "discount", "total"}) or format_hints.get("currency_like"):
            return "currency"
        if bool(tokens & {"percent", "pct", "rate", "margin", "ratio"}):
            return "percentage"
        if bool(tokens & {"count", "qty", "quantity", "units", "number", "num"}):
            return "count"
    if candidate_key_hint or candidate_key_score >= 0.98 or format_hints.get("identifier_like"):
        return "identifier"

    for tag, keywords in _NAME_HINTS:
        if tokens & keywords:
            if tag == "text" and inferred_type == "string":
                return tag
            if tag != "text":
                return tag

    if format_hints.get("currency_like") or any("@" in sample for sample in samples):
        if format_hints.get("currency_like") and inferred_type in {"numeric", "string"}:
            return "currency"
        return "text"
    if format_hints.get("date_like") or any(sample[:4].isdigit() and "-" in sample for sample in samples):
        return "datetime"

    if inferred_type == "string":
        unique_count = int(profile.get("unique_count", 0) or 0)
        unique_non_null_count = int(profile.get("unique_non_null_count", unique_count) or unique_count)
        if unique_count < 20 or cardinality_ratio <= 0.2:
            return "categorical_label"
        if unique_non_null_count > 0 and (candidate_key_score >= 0.9 or cardinality_ratio >= 0.8):
            return "text"
        return "categorical_label" if unique_count < 20 else "text"

    return "unknown"


def _assess_column_suitability(
    column_name: str,
    profile: dict,
    semantic_tag: str,
    intended_type: str,
    total_rows: int,
) -> dict:
    """Assess whether a column is suitable for analysis using Agent 1 metadata."""
    missing_rate = float(profile.get("missing_rate_pct", 0.0))
    unique_count = int(profile.get("unique_count", 0) or 0)
    duplicate_pressure_pct = round((1 - (unique_count / max(total_rows, 1))) * 100, 2)

    if semantic_tag == "identifier":
        is_suitable = missing_rate <= 5.0 and duplicate_pressure_pct <= 5.0
        reason_category = "identifier_duplicates" if duplicate_pressure_pct > 5.0 else "identifier_clean"
    elif semantic_tag in {"categorical_label", "geographic", "text"}:
        is_suitable = missing_rate <= 30.0 and unique_count > 0
        reason_category = "low_cardinality_category" if unique_count < 20 else "text_or_label"
    elif semantic_tag == "datetime":
        is_suitable = missing_rate <= 25.0
        reason_category = "datetime_missingness"
    elif semantic_tag in {"currency", "percentage", "count"} or intended_type in {"float", "int"}:
        is_suitable = missing_rate <= 35.0
        reason_category = "numeric_missingness"
    else:
        is_suitable = missing_rate <= 20.0 and duplicate_pressure_pct <= 95.0
        reason_category = "unknown_semantics"

    if not is_suitable and missing_rate > 60.0:
        reason_category = "too_sparse"

    return {
        "column_name": column_name,
        "is_suitable": is_suitable,
        "missing_rate_pct": round(missing_rate, 2),
        "duplicate_pressure_pct": duplicate_pressure_pct,
        "unique_count": unique_count,
        "reason_category": reason_category,
    }


def _imputation_strategy_from_null_policy_action(action: str) -> str:
    """Normalize a null-policy action into the imputation contract used by Agent 3."""
    mapping = {
        "flag_only": "none",
        "drop_rows": "drop",
        "impute_mean": "mean",
        "impute_median": "median",
        "impute_mode": "mode",
        "impute_unknown_label": "unknown_label",
        "impute_forward_fill": "forward_fill",
        "impute_knn": "knn",
        "impute_iterative": "iterative",
        "drop_column": "drop_column",
        "none": "none",
    }
    return mapping.get(str(action or "").lower(), "none")


def _null_policy_action_from_imputation_strategy(strategy: str) -> str | None:
    """Map an imputation strategy back to a null-policy action when possible."""
    mapping = {
        "none": "none",
        "drop": "drop_rows",
        "mean": "impute_mean",
        "median": "impute_median",
        "mode": "impute_mode",
        "unknown_label": "impute_unknown_label",
        "forward_fill": "impute_forward_fill",
        "knn": "impute_knn",
        "iterative": "impute_iterative",
        "drop_column": "drop_column",
    }
    return mapping.get(str(strategy or "").lower())


def _resolve_null_policy(profile: dict, meta: dict, raw_profile: dict | None = None, column_name: str | None = None) -> tuple[dict, str]:
    """Preserve valid model-provided policy when safe; otherwise fall back to local semantics."""
    semantic_tag = str(meta.get("semantic_tag", "unknown")).lower()
    explicit_strategy = str(meta.get("imputation_strategy", "")).lower()
    explicit_null_policy = meta.get("null_policy") if isinstance(meta.get("null_policy"), dict) else None

    if semantic_tag == "identifier":
        meta["is_identifier"] = True

    derived_null_policy = _derive_null_policy(profile, meta, raw_profile=raw_profile, column_name=column_name)
    derived_strategy = _imputation_strategy_from_null_policy_action(derived_null_policy.get("action"))

    guardrail_tags = {"identifier", "currency", "financial", "datetime"}
    if bool(meta.get("is_identifier", False)) or semantic_tag in guardrail_tags:
        return derived_null_policy, derived_strategy

    if explicit_null_policy:
        explicit_action = str(explicit_null_policy.get("action", "")).lower()
        if explicit_action in {
            "flag_only",
            "drop_rows",
            "impute_mean",
            "impute_median",
            "impute_mode",
            "impute_unknown_label",
            "impute_forward_fill",
            "impute_knn",
            "impute_iterative",
            "drop_column",
            "none",
        }:
            normalized_strategy = _imputation_strategy_from_null_policy_action(explicit_action)
            if explicit_strategy in {"", normalized_strategy}:
                normalized_null_policy = dict(explicit_null_policy)
                normalized_null_policy.setdefault("threshold_pct", float(profile.get("missing_rate_pct", 0.0)))
                normalized_null_policy.setdefault("reason", "model-selected null policy")
                return normalized_null_policy, normalized_strategy

    explicit_action = _null_policy_action_from_imputation_strategy(explicit_strategy)
    if explicit_action and explicit_strategy not in {"", "none"}:
        return {
            "action": explicit_action,
            "threshold_pct": float(profile.get("missing_rate_pct", 0.0)),
            "reason": str(meta.get("notes") or "model-selected imputation strategy"),
        }, explicit_strategy

    return derived_null_policy, derived_strategy


def _derive_null_policy(profile: dict, meta: dict, raw_profile: dict | None = None, column_name: str | None = None) -> dict:
    """Choose a null-handling policy from semantic meaning and observed data signals."""
    missing_rate = float(profile.get("missing_rate_pct", 0.0))
    unique_count = int(profile.get("unique_count", 0) or 0)
    intended_type = str(meta.get("intended_type", "string"))
    semantic_tag = str(meta.get("semantic_tag", "unknown")).lower()
    is_identifier = bool(meta.get("is_identifier", False))
    raw_profile = raw_profile or {}
    distribution = raw_profile.get("distribution_analysis", {}).get(column_name, {}) if column_name else {}
    correlation_summary = _column_correlation_summary(column_name, raw_profile) if column_name else {"max_abs_r": 0.0, "partners": []}
    outlier_analysis = profile.get("outlier_analysis", {}) if isinstance(profile.get("outlier_analysis"), dict) else {}
    sample_values = [_json_safe_value(value) for value in profile.get("sample_values", []) if value is not None]
    sample_diversity = len({str(value).strip().lower() for value in sample_values if str(value).strip()})
    is_normal_distribution = bool(distribution.get("is_normal_distribution", False))
    distribution_type = str(distribution.get("distribution_type", "")).lower()
    has_significant_outliers = bool(outlier_analysis.get("has_significant_outliers", False))
    max_abs_correlation = float(correlation_summary.get("max_abs_r", 0.0) or 0.0)

    if missing_rate <= 0:
        return {
            "action": "none",
            "threshold_pct": 0.0,
            "reason": "no missing values detected",
        }

    if is_identifier:
        return {
            "action": "drop_rows",
            "threshold_pct": 0.0,
            "reason": "identifier columns should not be imputed because missing keys break row identity",
        }

    if semantic_tag in {"currency", "financial"}:
        return {
            "action": "flag_only",
            "threshold_pct": 0.0,
            "reason": "currency and financial fields keep nulls for analyst review instead of synthetic fills",
        }

    if semantic_tag == "datetime" or intended_type == "datetime":
        if missing_rate >= 25.0:
            return {
                "action": "flag_only",
                "threshold_pct": 25.0,
                "reason": "datetime gaps can distort time-based analysis when missingness is moderate or high",
            }
        return {
            "action": "none",
            "threshold_pct": 25.0,
            "reason": "small datetime gaps are left unchanged to avoid inventing timestamps",
        }

    if semantic_tag in {"geographic", "text"}:
        return {
            "action": "flag_only",
            "threshold_pct": 20.0,
            "reason": f"{semantic_tag} fields preserve nulls because filling them would invent domain meaning",
        }

    if semantic_tag == "unknown" and intended_type not in {"float", "int", "boolean"}:
        return {
            "action": "flag_only",
            "threshold_pct": 0.0,
            "reason": "column semantics are unclear, so manual review is safer than automatic imputation",
        }

    if missing_rate >= 60.0:
        return {
            "action": "drop_column",
            "threshold_pct": 60.0,
            "reason": "column is too sparse to impute reliably, so dropping it is safer than synthesizing most of its values",
        }

    if semantic_tag == "categorical_label":
        if missing_rate >= 40.0:
            return {
                "action": "flag_only",
                "threshold_pct": 40.0,
                "reason": "categorical column is too sparse for a reliable single-label fill",
            }
        if unique_count and unique_count <= 5 and missing_rate <= 15.0 and sample_diversity <= 2:
            return {
                "action": "impute_mode",
                "threshold_pct": 15.0,
                "reason": "categorical samples show a likely dominant label, so mode is a reasonable fill",
            }
        if unique_count and unique_count <= 20 and missing_rate <= 25.0:
            return {
                "action": "impute_unknown_label",
                "threshold_pct": 25.0,
                "reason": "categorical labels appear diverse enough that preserving missingness as 'Unknown' is safer than forcing the mode",
            }
        return {
            "action": "flag_only",
            "threshold_pct": 30.0,
            "reason": "categorical columns with heavier missingness are safer to review than to auto-fill",
        }

    if semantic_tag in {"percentage", "count", "physical_measurement"}:
        if len(correlation_summary.get("partners", [])) >= 2 and max_abs_correlation >= 0.9 and 10.0 <= missing_rate <= 35.0:
            return {
                "action": "impute_iterative",
                "threshold_pct": 35.0,
                "reason": "multiple strong correlated predictors are available, so iterative multivariate imputation is justified",
            }
        if max_abs_correlation >= 0.85 and 10.0 <= missing_rate <= 30.0:
            return {
                "action": "impute_knn",
                "threshold_pct": 30.0,
                "reason": "a strong correlated numeric neighbor is available, so KNN imputation is preferable to a simple univariate fill",
            }
        if missing_rate <= 10.0 and raw_profile.get("distribution_analysis") and any(
            str(raw_profile.get("columns", {}).get(other_col, {}).get("dtype", "")).startswith("datetime")
            or "datetime" in str(raw_profile.get("columns", {}).get(other_col, {}).get("dtype", "")).lower()
            for other_col in raw_profile.get("columns", {})
        ):
            return {
                "action": "impute_forward_fill",
                "threshold_pct": 10.0,
                "reason": "a datetime context exists and the gap is sparse, so forward fill can preserve local sequence continuity",
            }
        if missing_rate >= 30.0:
            return {
                "action": "flag_only",
                "threshold_pct": 30.0,
                "reason": f"{semantic_tag} fields with heavier missingness should be reviewed before synthetic numeric fills",
            }
        if is_normal_distribution and not has_significant_outliers and missing_rate <= 20.0:
            return {
                "action": "impute_mean",
                "threshold_pct": 20.0,
                "reason": f"{semantic_tag} values look approximately normal, so mean imputation preserves the center better than median",
            }
        return {
            "action": "impute_median",
            "threshold_pct": 30.0,
            "reason": f"{semantic_tag} values are skewed, sparse, or outlier-prone enough that median is safer than mean",
        }

    if intended_type == "boolean":
        if missing_rate <= 10.0:
            return {
                "action": "impute_mode",
                "threshold_pct": 10.0,
                "reason": "boolean fields with sparse gaps can use the dominant state conservatively",
            }
        return {
            "action": "flag_only",
            "threshold_pct": 10.0,
            "reason": "boolean fields with non-trivial missingness are better flagged than defaulted",
        }

    if intended_type == "string":
        if unique_count and unique_count <= 20 and missing_rate <= 20.0:
            return {
                "action": "impute_mode",
                "threshold_pct": 20.0,
                "reason": "string fields that behave like compact labels can use mode as a conservative fill",
            }
        return {
            "action": "flag_only",
            "threshold_pct": 20.0,
            "reason": "high-cardinality string fields are safer to review than to auto-impute",
        }

    if intended_type in {"float", "int"}:
        if len(correlation_summary.get("partners", [])) >= 2 and max_abs_correlation >= 0.9 and 10.0 <= missing_rate <= 35.0:
            return {
                "action": "impute_iterative",
                "threshold_pct": 35.0,
                "reason": "multiple strong correlated predictors are available, so iterative multivariate imputation is justified",
            }
        if max_abs_correlation >= 0.85 and 10.0 <= missing_rate <= 30.0:
            return {
                "action": "impute_knn",
                "threshold_pct": 30.0,
                "reason": "a strong correlated numeric neighbor is available, so KNN imputation is preferable to a simple univariate fill",
            }
        if missing_rate >= 35.0:
            return {
                "action": "flag_only",
                "threshold_pct": 35.0,
                "reason": "numeric columns with heavy missingness should be reviewed before any synthetic fill",
            }
        if is_normal_distribution and not has_significant_outliers and missing_rate <= 20.0:
            return {
                "action": "impute_mean",
                "threshold_pct": 20.0,
                "reason": "numeric values look approximately normal, so mean imputation preserves the center efficiently",
            }
        if distribution_type == "right_skewed" or has_significant_outliers:
            return {
                "action": "impute_median",
                "threshold_pct": 35.0,
                "reason": "numeric values are skewed or contain outliers, so median is safer than mean",
            }
        return {
            "action": "impute_median",
            "threshold_pct": 35.0,
            "reason": "numeric values do not look strongly normal, so median is the conservative default",
        }

    return {
        "action": "flag_only",
        "threshold_pct": 20.0,
        "reason": "column semantics are unclear, so manual review is safer than automatic imputation",
    }


def _derive_encoding_strategy(profile: dict, meta: dict) -> dict:
    """Choose an encoding strategy that matches the inferred semantic role."""
    unique_count = int(profile.get("unique_count", 0) or 0)
    semantic_tag = str(meta.get("semantic_tag", "unknown"))
    intended_type = str(meta.get("intended_type", "string"))
    is_identifier = bool(meta.get("is_identifier", False))
    analysis_allowed = bool(meta.get("analysis_allowed", True))

    explicit = meta.get("encoding_strategy")
    if isinstance(explicit, dict):
        method = str(explicit.get("method", "none")).lower()
        if method in {"one_hot", "ordinal", "none"}:
            strategy = {"method": method}
            order = explicit.get("order")
            if method == "ordinal" and isinstance(order, list) and order:
                strategy["order"] = order
            reason = explicit.get("reason")
            if reason:
                strategy["reason"] = str(reason)
            if method != "ordinal" or strategy.get("order"):
                return strategy

    if not analysis_allowed or is_identifier:
        return {
            "method": "none",
            "reason": "excluded from analysis or identifier columns should not be encoded",
        }

    if semantic_tag in {"datetime", "text"} or intended_type in {"datetime", "boolean"}:
        return {
            "method": "none",
            "reason": "datetime, boolean, and free-text columns should not be encoded",
        }

    if semantic_tag == "categorical_label" or intended_type in {"string", "category"}:
        if unique_count <= 1:
            return {
                "method": "none",
                "reason": "constant or empty categories do not need encoding",
            }
        if unique_count <= 20:
            return {
                "method": "one_hot",
                "reason": "low-cardinality nominal category defaulted to one-hot encoding",
            }
        return {
            "method": "none",
            "reason": "high-cardinality label left unencoded to avoid sparse noise",
        }

    return {
        "method": "none",
        "reason": "non-categorical columns are not encoded",
    }


def _enrich_missingness_metadata(df: pd.DataFrame, raw_profile: dict, schema_blueprint: dict, inferred_types: dict) -> dict:
    """Populate each column's blueprint with derived analysis metadata."""
    total_rows = int(raw_profile.get("shape", {}).get("rows", len(df)) or len(df))
    for col in df.columns:
        profile = raw_profile.get("columns", {}).get(col, {})
        meta = schema_blueprint.setdefault(col, {})

        inferred_type = inferred_types.get(col, meta.get("intended_type", "string"))

        if meta.get("semantic_tag", "unknown") in {None, "", "unknown"}:
            meta["semantic_tag"] = _infer_semantic_tag_from_metadata(col, profile, inferred_type)

        if not meta.get("intended_type"):
            if inferred_type == "numeric":
                meta["intended_type"] = "float"
            else:
                meta["intended_type"] = inferred_type

        assessment = _assess_column_suitability(
            column_name=col,
            profile=profile,
            semantic_tag=str(meta.get("semantic_tag", "unknown")),
            intended_type=str(meta.get("intended_type", "string")),
            total_rows=total_rows,
        )
        meta["column_assessment"] = assessment

        meta["null_policy"], meta["imputation_strategy"] = _resolve_null_policy(
            profile,
            meta,
            raw_profile=raw_profile,
            column_name=col,
        )

        if not isinstance(meta.get("encoding_strategy"), dict):
            meta["encoding_strategy"] = _derive_encoding_strategy(profile, meta)

        null_policy = meta["null_policy"]
        null_policy.setdefault("action", "flag_only")
        null_policy.setdefault("threshold_pct", float(profile.get("missing_rate_pct", 0.0)))
        null_policy.setdefault("reason", "missingness policy inferred from column semantics")

        if "notes" not in meta or not meta["notes"]:
            meta["notes"] = null_policy["reason"]

    return schema_blueprint


def _fallback_blueprint(df: pd.DataFrame, inferred_types: dict) -> dict:
    """Build a conservative schema blueprint when the LLM path fails."""
    def _normalize_intended_type(t: str) -> str:
        if t == "numeric":
            return "float"
        if t in {"datetime", "string", "boolean"}:
            return t
        return "string"

    return {
        col: {
            "intended_type": _normalize_intended_type(inferred_types[col]),
            "semantic_tag": "unknown",
            "is_identifier": False,
            "scaling_allowed": inferred_types[col] == "numeric",
            "imputation_strategy": "none",
            "null_policy": {
                "action": "flag_only",
                "threshold_pct": 20.0,
                "reason": "fallback policy inferred without LLM semantics",
            },
            "encoding_strategy": {
                "method": "one_hot" if inferred_types[col] == "string" else "none",
                "reason": "fallback encoding inferred without LLM semantics" if inferred_types[col] == "string" else "non-categorical fallback",
            },
            "analysis_allowed": True,
            "notes": "fallback — LLM call failed"
        }
        for col in df.columns
    }


def _apply_missingness_policy(
    df: pd.DataFrame,
    raw_profile: dict,
    schema_blueprint: dict,
    inferred_types: dict | None = None,
) -> dict:
    """Attach analysis eligibility and null/encoding policies to each column."""
    excluded = []
    schema_blueprint = _enrich_missingness_metadata(df, raw_profile, schema_blueprint, inferred_types or {})
    for col in df.columns:
        profile = raw_profile.get("columns", {}).get(col, {})
        missing_rate = float(profile.get("missing_rate_pct", 0.0))
        meta = schema_blueprint.setdefault(col, {})

        assessment = meta.get("column_assessment", {}) if isinstance(meta.get("column_assessment"), dict) else {}
        analysis_allowed = bool(assessment.get("is_suitable", True)) and missing_rate <= MISSINGNESS_ANALYSIS_THRESHOLD_PCT
        meta["analysis_allowed"] = analysis_allowed
        if not analysis_allowed:
            excluded.append((col, missing_rate))
            note = meta.get("notes", "")
            missing_note = f"excluded from analysis: missing_rate_pct={missing_rate:.2f}% exceeds {MISSINGNESS_ANALYSIS_THRESHOLD_PCT:.0f}%"
            meta["notes"] = f"{note}; {missing_note}".strip("; ") if note else missing_note

        if not isinstance(meta.get("encoding_strategy"), dict):
            meta["encoding_strategy"] = _derive_encoding_strategy(profile, meta)

        meta["confidence"] = _calculate_semantic_confidence(
            col,
            profile,
            str(inferred_types.get(col, meta.get("intended_type", "unknown"))),
            str(meta.get("semantic_tag", "unknown")),
            profile.get("format_hints", {}) if isinstance(profile.get("format_hints"), dict) else {},
        )
    return schema_blueprint, excluded


def _print_semantic_summary(df: pd.DataFrame, schema_blueprint: dict) -> None:
    """Print a vertical human-readable summary of the generated blueprint."""
    print("[Agent 2] Semantic tags by column:")
    for col in df.columns:
        meta = schema_blueprint.get(col, {})
        null_policy = meta.get("null_policy", {}) if isinstance(meta.get("null_policy"), dict) else {}
        assessment = meta.get("column_assessment", {}) if isinstance(meta.get("column_assessment"), dict) else {}
        imputation_reason = null_policy.get("reason", meta.get("notes", "n/a"))
        print(f"\n  ┌─ {col}")
        print(f"  │  semantic_tag     : {meta.get('semantic_tag', 'unknown')}")
        print(f"  │  intended_type    : {meta.get('intended_type', 'unknown')}")
        print(f"  │  imputation       : {meta.get('imputation_strategy', 'unknown')}")
        print(f"  │  imputation_reason: {imputation_reason}")
        print(f"  │  encoding         : {meta.get('encoding_strategy', {}).get('method', 'none')}")
        print(f"  │  identifier       : {meta.get('is_identifier', False)}")
        print(f"  │  analysis_allowed : {meta.get('analysis_allowed', True)}")
        print(f"  │  confidence       : {meta.get('confidence', {}).get('confidence_score', 'n/a')}")
        print(f"  │  null_action      : {null_policy.get('action', 'none')}")
        print(f"  │  suitable         : {assessment.get('is_suitable', True)}")
        print(f"  └─ reason           : {assessment.get('reason_category', 'n/a')}")


def agent2_semantic_tagger(state: dict) -> dict:
    """Generate schema metadata for each column and return the updated state."""
    errors = state.get("errors", [])
    raw_profile = state.get("raw_profile", {})
    df = state.get("_df_cache")

    if df is None:
        errors.append("Agent2: No DataFrame in state. Agent 1 failed.")
        return {**state, "errors": errors}

    # Step 1: use cheap local heuristics before involving the LLM.
    inferred_types = _infer_intended_types(df, raw_profile)
    type_counts = {}
    for inferred_type in inferred_types.values():
        type_counts[inferred_type] = type_counts.get(inferred_type, 0) + 1
    print(f"[Agent 2] Type sniffing summary: {type_counts}")

    # Step 2: request semantic tags in batches when the schema is large.

    try:
        columns = list(df.columns)
        column_batches = [columns] if len(columns) <= LLM_SINGLE_CALL_THRESHOLD else _split_columns_into_batches(columns, LLM_BATCH_SIZE)
        schema_blueprint = {}
        for batch_columns in column_batches:
            batch_blueprint = _call_llm_for_schema_blueprint_with_retry(df, inferred_types, raw_profile, batch_columns)
            _merge_schema_blueprints(schema_blueprint, batch_blueprint)

        schema_blueprint, excluded = _apply_missingness_policy(df, raw_profile, schema_blueprint, inferred_types)
        data_quality_signals = _assess_data_quality_signals(df, raw_profile)
        schema_blueprint["__metadata__"] = {
            "data_quality_assessment": data_quality_signals,
            "preprocessing_recommendation": data_quality_signals["preprocessing_recommendation"],
            "risk_assessment": data_quality_signals["risk_assessment"],
        }
        schema_blueprint = SchemaBlueprint(schema_blueprint)

        print(f"[Agent 2] Blueprint built for {len(schema_blueprint)} columns")
        _print_semantic_summary(df, schema_blueprint)
        if excluded:
            excluded_summary = ", ".join(f"{col} ({rate:.2f}%)" for col, rate in excluded)
            print(f"[Agent 2] Excluded from analysis (> {MISSINGNESS_ANALYSIS_THRESHOLD_PCT:.0f}% missing): {excluded_summary}")

    except json.JSONDecodeError as e:
        print(f"[Agent 2] LLM returned invalid JSON; using metadata heuristics instead: {e}")
        schema_blueprint = _fallback_blueprint(df, inferred_types)
        schema_blueprint, excluded = _apply_missingness_policy(df, raw_profile, schema_blueprint, inferred_types)
        data_quality_signals = _assess_data_quality_signals(df, raw_profile)
        schema_blueprint["__metadata__"] = {
            "data_quality_assessment": data_quality_signals,
            "preprocessing_recommendation": data_quality_signals["preprocessing_recommendation"],
            "risk_assessment": data_quality_signals["risk_assessment"],
        }
        schema_blueprint = SchemaBlueprint(schema_blueprint)
        _print_semantic_summary(df, schema_blueprint)
        if excluded:
            excluded_summary = ", ".join(f"{col} ({rate:.2f}%)" for col, rate in excluded)
            print(f"[Agent 2] Excluded from analysis (> {MISSINGNESS_ANALYSIS_THRESHOLD_PCT:.0f}% missing): {excluded_summary}")
    except Exception as e:
        print(f"[Agent 2] Groq call failed; using metadata heuristics instead: {e}")
        schema_blueprint = _fallback_blueprint(df, inferred_types)
        schema_blueprint, excluded = _apply_missingness_policy(df, raw_profile, schema_blueprint, inferred_types)
        data_quality_signals = _assess_data_quality_signals(df, raw_profile)
        schema_blueprint["__metadata__"] = {
            "data_quality_assessment": data_quality_signals,
            "preprocessing_recommendation": data_quality_signals["preprocessing_recommendation"],
            "risk_assessment": data_quality_signals["risk_assessment"],
        }
        schema_blueprint = SchemaBlueprint(schema_blueprint)
        _print_semantic_summary(df, schema_blueprint)
        if excluded:
            excluded_summary = ", ".join(f"{col} ({rate:.2f}%)" for col, rate in excluded)
            print(f"[Agent 2] Excluded from analysis (> {MISSINGNESS_ANALYSIS_THRESHOLD_PCT:.0f}% missing): {excluded_summary}")

    return {
        **state,
        "schema_blueprint": schema_blueprint,
        "errors": errors,
    }