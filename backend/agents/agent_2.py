# agents/agent2_semantic_tagger.py
import re
import os
import pandas as pd
import json
from groq import Groq

_GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=_GROQ_API_KEY) if _GROQ_API_KEY else None  # optional; heuristics still work without LLM

GROQ_MODEL = "llama-3.3-70b-versatile" 
MISSINGNESS_ANALYSIS_THRESHOLD_PCT = 20.0
LLM_BATCH_SIZE = 15
LLM_SINGLE_CALL_THRESHOLD = 20
LLM_MAX_TOKENS = 2000

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
    return set(re.findall(r"[a-z0-9]+", column_name.lower()))

SEMANTIC_SYSTEM_PROMPT = """You are a senior data analyst. Given column names, inferred types, and sample rows from a CSV,
produce a JSON schema blueprint. Return ONLY valid JSON, no markdown, no explanation, no backticks.

For each column output:
{
  "column_name": {
    "intended_type": "float|int|string|datetime|boolean|category",
    "semantic_tag": "currency|identifier|datetime|geographic|physical_measurement|categorical_label|text|percentage|count|unknown",
    "is_identifier": true|false,
    "scaling_allowed": true|false,
    "imputation_strategy": "mean|median|mode|unknown_label|drop|none",
        "encoding_strategy": {
            "method": "one_hot|ordinal|none",
            "order": ["optional", "category", "order", "list"],
            "reason": "brief reason"
        },
        "null_policy": {
            "action": "flag_only|drop_rows|impute_mean|impute_median|impute_mode|impute_unknown_label|none",
            "threshold_pct": number,
            "reason": "brief reason"
        },
    "notes": "brief reason"
  }
}

Rules:
- Currency/financial columns: scaling_allowed=false, imputation_strategy=median
- Identifier columns: is_identifier=true, imputation_strategy=drop
- Datetime columns: scaling_allowed=false, imputation_strategy=none
- Categorical with <20 unique: semantic_tag=categorical_label, imputation_strategy=mode, encoding_strategy=one_hot unless a real order list is provided
- Ordinal encoding is only valid when the column has a real order and an explicit ordered list is provided
- Use encoding_strategy=none for identifiers, free text, datetime columns, and very high-cardinality labels
- null_policy must explain what to do when missingness is low, moderate, or high.
- Prefer flag_only for sparse or ambiguous columns, drop_rows for identifiers, impute_mode for low-cardinality categories, impute_median for numeric/currency, and none for datetime columns when imputation would distort time semantics."""


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


def _build_llm_prompt(df: pd.DataFrame, inferred_types: dict, raw_profile: dict, columns: list[str] | None = None) -> str:
    """Minimal prompt — column metadata + 3 samples only. No full CSV."""
    columns = list(df.columns) if columns is None else columns
    col_info = []
    for col in columns:
        profile = raw_profile["columns"][col]
        col_info.append({
            "name": col,
            "inferred_type": inferred_types[col],
            "missing_rate_pct": profile["missing_rate_pct"],
            "unique_count": profile["unique_count"],
            "samples": profile["sample_values"][:3],
        })
    return json.dumps(col_info, indent=2)


def _split_columns_into_batches(columns: list[str], batch_size: int) -> list[list[str]]:
    return [columns[index:index + batch_size] for index in range(0, len(columns), batch_size)]


def _parse_schema_blueprint_response(raw_text: str) -> dict:
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

    return json.loads(raw_text)


def _call_llm_for_schema_blueprint(
    df: pd.DataFrame,
    inferred_types: dict,
    raw_profile: dict,
    columns: list[str],
) -> dict:
    user_prompt = _build_llm_prompt(df, inferred_types, raw_profile, columns)

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": SEMANTIC_SYSTEM_PROMPT},
            {"role": "user", "content": f"Produce schema blueprint for these columns:\n{user_prompt}"},
        ],
        temperature=0.1,
        max_tokens=LLM_MAX_TOKENS,
    )

    raw_text = response.choices[0].message.content.strip()
    return _parse_schema_blueprint_response(raw_text)


def _merge_schema_blueprints(base_blueprint: dict, incoming_blueprint: dict) -> dict:
    for column_name, metadata in incoming_blueprint.items():
        if column_name not in base_blueprint or not isinstance(base_blueprint[column_name], dict):
            base_blueprint[column_name] = metadata
        else:
            base_blueprint[column_name].update(metadata)
    return base_blueprint


def _infer_semantic_tag_from_metadata(column_name: str, profile: dict, inferred_type: str) -> str:
    """Infer a semantic tag from Agent 1 metadata and the column name."""
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
    """Assess whether a column is suitable for analysis using metadata from Agent 1."""
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


def _derive_null_policy(profile: dict, meta: dict) -> dict:
    missing_rate = float(profile.get("missing_rate_pct", 0.0))
    unique_count = int(profile.get("unique_count", 0) or 0)
    intended_type = str(meta.get("intended_type", "string"))
    semantic_tag = str(meta.get("semantic_tag", "unknown"))
    is_identifier = bool(meta.get("is_identifier", False))

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

    if missing_rate >= 60.0:
        return {
            "action": "flag_only",
            "threshold_pct": 60.0,
            "reason": "column is too sparse to impute reliably",
        }

    if semantic_tag in {"categorical_label", "text"} or intended_type == "string":
        if unique_count and unique_count < 20:
            return {
                "action": "impute_mode",
                "threshold_pct": 20.0,
                "reason": "low-cardinality categorical columns usually tolerate mode imputation",
            }
        if missing_rate >= 30.0:
            return {
                "action": "flag_only",
                "threshold_pct": 30.0,
                "reason": "high missingness in free text or high-cardinality labels is better flagged than imputed",
            }
        return {
            "action": "impute_mode",
            "threshold_pct": 20.0,
            "reason": "categorical/text columns with modest missingness can use mode as a conservative fill",
        }

    if semantic_tag in {"currency", "percentage", "count"} or intended_type in {"float", "int"}:
        if missing_rate >= 35.0:
            return {
                "action": "flag_only",
                "threshold_pct": 35.0,
                "reason": "numeric columns with heavy missingness should be reviewed before any synthetic fill",
            }
        return {
            "action": "impute_median",
            "threshold_pct": 35.0,
            "reason": "median is robust for numeric fields with limited missingness",
        }

    return {
        "action": "flag_only",
        "threshold_pct": 20.0,
        "reason": "column semantics are unclear, so manual review is safer than automatic imputation",
    }


def _derive_encoding_strategy(profile: dict, meta: dict) -> dict:
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

        if not isinstance(meta.get("null_policy"), dict):
            meta["null_policy"] = _derive_null_policy(profile, meta)

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
    """Used when LLM call fails. Basic but functional."""
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
            "imputation_strategy": "median" if inferred_types[col] == "numeric" else "mode",
            "null_policy": {
                "action": "impute_median" if inferred_types[col] == "numeric" else "flag_only",
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
    return schema_blueprint, excluded


def _print_semantic_summary(df: pd.DataFrame, schema_blueprint: dict) -> None:
    print("[Agent 2] Semantic tags by column:")
    for col in df.columns:
        meta = schema_blueprint.get(col, {})
        null_policy = meta.get("null_policy", {}) if isinstance(meta.get("null_policy"), dict) else {}
        assessment = meta.get("column_assessment", {}) if isinstance(meta.get("column_assessment"), dict) else {}
        print(
            f"  - {col}: semantic_tag={meta.get('semantic_tag', 'unknown')}, "
            f"intended_type={meta.get('intended_type', 'unknown')}, "
            f"imputation={meta.get('imputation_strategy', 'unknown')}, "
            f"encoding={meta.get('encoding_strategy', {}).get('method', 'none')}, "
            f"identifier={meta.get('is_identifier', False)}, "
            f"analysis_allowed={meta.get('analysis_allowed', True)}, "
            f"null_action={null_policy.get('action', 'none')}, "
            f"suitable={assessment.get('is_suitable', True)}, "
            f"reason={assessment.get('reason_category', 'n/a')}"
        )


def agent2_semantic_tagger(state: dict) -> dict:
    errors = state.get("errors", [])
    raw_profile = state.get("raw_profile", {})
    df = state.get("_df_cache")

    if df is None:
        errors.append("Agent2: No DataFrame in state. Agent 1 failed.")
        return {**state, "errors": errors}

    # Step 1: pure Python type sniffing
    inferred_types = _infer_intended_types(df, raw_profile)
    type_counts = {}
    for inferred_type in inferred_types.values():
        type_counts[inferred_type] = type_counts.get(inferred_type, 0) + 1
    print(f"[Agent 2] Type sniffing summary: {type_counts}")

    # Step 2: Groq LLM calls for semantic tagging, chunked for larger schemas

    try:
        columns = list(df.columns)
        column_batches = [columns] if len(columns) <= LLM_SINGLE_CALL_THRESHOLD else _split_columns_into_batches(columns, LLM_BATCH_SIZE)
        schema_blueprint = {}
        for batch_columns in column_batches:
            batch_blueprint = _call_llm_for_schema_blueprint(df, inferred_types, raw_profile, batch_columns)
            _merge_schema_blueprints(schema_blueprint, batch_blueprint)

        schema_blueprint, excluded = _apply_missingness_policy(df, raw_profile, schema_blueprint, inferred_types)

        print(f"[Agent 2] Blueprint built for {len(schema_blueprint)} columns")
        _print_semantic_summary(df, schema_blueprint)
        if excluded:
            excluded_summary = ", ".join(f"{col} ({rate:.2f}%)" for col, rate in excluded)
            print(f"[Agent 2] Excluded from analysis (> {MISSINGNESS_ANALYSIS_THRESHOLD_PCT:.0f}% missing): {excluded_summary}")

    except json.JSONDecodeError as e:
        print(f"[Agent 2] LLM returned invalid JSON; using metadata heuristics instead: {e}")
        schema_blueprint = _fallback_blueprint(df, inferred_types)
        schema_blueprint, excluded = _apply_missingness_policy(df, raw_profile, schema_blueprint, inferred_types)
        _print_semantic_summary(df, schema_blueprint)
        if excluded:
            excluded_summary = ", ".join(f"{col} ({rate:.2f}%)" for col, rate in excluded)
            print(f"[Agent 2] Excluded from analysis (> {MISSINGNESS_ANALYSIS_THRESHOLD_PCT:.0f}% missing): {excluded_summary}")
    except Exception as e:
        print(f"[Agent 2] Groq call failed; using metadata heuristics instead: {e}")
        schema_blueprint = _fallback_blueprint(df, inferred_types)
        schema_blueprint, excluded = _apply_missingness_policy(df, raw_profile, schema_blueprint, inferred_types)
        _print_semantic_summary(df, schema_blueprint)
        if excluded:
            excluded_summary = ", ".join(f"{col} ({rate:.2f}%)" for col, rate in excluded)
            print(f"[Agent 2] Excluded from analysis (> {MISSINGNESS_ANALYSIS_THRESHOLD_PCT:.0f}% missing): {excluded_summary}")

    return {
        **state,
        "schema_blueprint": schema_blueprint,
        "errors": errors,
    }