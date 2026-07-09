# agents/agent2_semantic_tagger.py
import pandas as pd
import json
from groq import Groq

client = Groq()  # reads GROQ_API_KEY from env

GROQ_MODEL = "llama-3.3-70b-versatile" 
MISSINGNESS_ANALYSIS_THRESHOLD_PCT = 20.0

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
    "notes": "brief reason"
  }
}

Rules:
- Currency/financial columns: scaling_allowed=false, imputation_strategy=median
- Identifier columns: is_identifier=true, imputation_strategy=drop
- Datetime columns: scaling_allowed=false, imputation_strategy=none
- Categorical with <20 unique: semantic_tag=categorical_label, imputation_strategy=mode"""


def _infer_intended_types(df: pd.DataFrame, raw_profile: dict) -> dict:
    """Pure Python type sniffing. No LLM. 80% coercion threshold."""
    inferred = {}
    for col in df.columns:
        raw_dtype = raw_profile["columns"][col]["dtype"]

        if raw_dtype in ("int64", "int32", "float64", "float32"):
            inferred[col] = "numeric"
        elif raw_dtype == "bool":
            inferred[col] = "boolean"
        elif raw_dtype == "object":
            coerced = pd.to_numeric(df[col], errors="coerce")
            non_null = df[col].notna().sum()
            if non_null > 0 and (coerced.notna().sum() / non_null) >= 0.80:
                inferred[col] = "numeric"
            else:
                try:
                    parsed = pd.to_datetime(df[col], errors="coerce", infer_datetime_format=True)
                    if parsed.notna().sum() / max(non_null, 1) >= 0.80:
                        inferred[col] = "datetime"
                    else:
                        inferred[col] = "string"
                except Exception:
                    inferred[col] = "string"
        elif "datetime" in raw_dtype:
            inferred[col] = "datetime"
        else:
            inferred[col] = "unknown"

    return inferred


def _build_llm_prompt(df: pd.DataFrame, inferred_types: dict, raw_profile: dict) -> str:
    """Minimal prompt — column metadata + 3 samples only. No full CSV."""
    col_info = []
    for col in df.columns:
        profile = raw_profile["columns"][col]
        col_info.append({
            "name": col,
            "inferred_type": inferred_types[col],
            "missing_rate_pct": profile["missing_rate_pct"],
            "unique_count": profile["unique_count"],
            "samples": profile["sample_values"][:3],
        })
    return json.dumps(col_info, indent=2)


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
            "analysis_allowed": True,
            "notes": "fallback — LLM call failed"
        }
        for col in df.columns
    }


def _apply_missingness_policy(df: pd.DataFrame, raw_profile: dict, schema_blueprint: dict) -> dict:
    excluded = []
    for col in df.columns:
        profile = raw_profile.get("columns", {}).get(col, {})
        missing_rate = float(profile.get("missing_rate_pct", 0.0))
        analysis_allowed = missing_rate <= MISSINGNESS_ANALYSIS_THRESHOLD_PCT
        meta = schema_blueprint.setdefault(col, {})
        meta["analysis_allowed"] = analysis_allowed
        if not analysis_allowed:
            excluded.append((col, missing_rate))
            note = meta.get("notes", "")
            missing_note = f"excluded from analysis: missing_rate_pct={missing_rate:.2f}% exceeds {MISSINGNESS_ANALYSIS_THRESHOLD_PCT:.0f}%"
            meta["notes"] = f"{note}; {missing_note}".strip("; ") if note else missing_note
    return schema_blueprint, excluded


def _print_semantic_summary(df: pd.DataFrame, schema_blueprint: dict) -> None:
    print("[Agent 2] Semantic tags by column:")
    for col in df.columns:
        meta = schema_blueprint.get(col, {})
        print(
            f"  - {col}: semantic_tag={meta.get('semantic_tag', 'unknown')}, "
            f"intended_type={meta.get('intended_type', 'unknown')}, "
            f"imputation={meta.get('imputation_strategy', 'unknown')}, "
            f"identifier={meta.get('is_identifier', False)}, "
            f"analysis_allowed={meta.get('analysis_allowed', True)}"
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

    # Step 2: single Groq LLM call for semantic tagging
    user_prompt = _build_llm_prompt(df, inferred_types, raw_profile)

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SEMANTIC_SYSTEM_PROMPT},
                {"role": "user", "content": f"Produce schema blueprint for these columns:\n{user_prompt}"}
            ],
            temperature=0.1,       # low temp → more deterministic JSON
            max_tokens=2000,
        )

        raw_text = response.choices[0].message.content.strip()

        # Strip markdown fences if Groq model adds them anyway
        if "```" in raw_text:
            parts = raw_text.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                try:
                    schema_blueprint = json.loads(part)
                    break
                except Exception:
                    continue
            else:
                raise json.JSONDecodeError("No valid JSON block found", raw_text, 0)
        else:
            schema_blueprint = json.loads(raw_text)

        schema_blueprint, excluded = _apply_missingness_policy(df, raw_profile, schema_blueprint)

        print(f"[Agent 2] Blueprint built for {len(schema_blueprint)} columns")
        _print_semantic_summary(df, schema_blueprint)
        if excluded:
            excluded_summary = ", ".join(f"{col} ({rate:.2f}%)" for col, rate in excluded)
            print(f"[Agent 2] Excluded from analysis (> {MISSINGNESS_ANALYSIS_THRESHOLD_PCT:.0f}% missing): {excluded_summary}")

    except json.JSONDecodeError as e:
        errors.append(f"Agent2: LLM returned invalid JSON — {e}")
        schema_blueprint = _fallback_blueprint(df, inferred_types)
        schema_blueprint, excluded = _apply_missingness_policy(df, raw_profile, schema_blueprint)
        _print_semantic_summary(df, schema_blueprint)
        if excluded:
            excluded_summary = ", ".join(f"{col} ({rate:.2f}%)" for col, rate in excluded)
            print(f"[Agent 2] Excluded from analysis (> {MISSINGNESS_ANALYSIS_THRESHOLD_PCT:.0f}% missing): {excluded_summary}")
    except Exception as e:
        errors.append(f"Agent2: Groq call failed — {e}")
        schema_blueprint = _fallback_blueprint(df, inferred_types)
        schema_blueprint, excluded = _apply_missingness_policy(df, raw_profile, schema_blueprint)
        _print_semantic_summary(df, schema_blueprint)
        if excluded:
            excluded_summary = ", ".join(f"{col} ({rate:.2f}%)" for col, rate in excluded)
            print(f"[Agent 2] Excluded from analysis (> {MISSINGNESS_ANALYSIS_THRESHOLD_PCT:.0f}% missing): {excluded_summary}")

    return {
        **state,
        "schema_blueprint": schema_blueprint,
        "errors": errors,
    }