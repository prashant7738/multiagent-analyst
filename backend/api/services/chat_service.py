"""Dataset chat service.

Lets a user ask natural-language questions about an already-analyzed dataset.
Answers are grounded in the deterministic facts already computed by Agents
1-6 (schema, stats, quality, validation, narrative) via ``job.result`` — the
LLM never sees raw rows, only these precomputed facts, so it has nothing to
hallucinate numbers from.

If the question implies a chart that doesn't already exist, the model is
asked to emit a small structured ``chart_request`` (chart type + columns +
aggregation). That request is validated against the schema blueprint and,
only if valid, rendered with matplotlib into a new PNG under
``outputs/charts`` — the same directory and URL scheme Agent 4 uses.
"""

from __future__ import annotations

import os
import uuid
import re
import time
from typing import Any, TYPE_CHECKING

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from agents.agent_2 import (
    GEMINI_MODEL,
    GROQ_MODEL,
    GROQ_REASONING_EFFORT,
    _get_groq_client,
    _call_gemini_json_with_failover,
    _parse_schema_blueprint_response,
)
from api.config import get_settings
from api.services import rag_service
from api.utils.serialization import chart_url, json_safe

if TYPE_CHECKING:
    from api.services.job_manager import Job, JobManager

CHARTS_DIR = "outputs/charts"
os.makedirs(CHARTS_DIR, exist_ok=True)

COLORS = {
    "primary": "#2563EB", "secondary": "#16A34A", "accent": "#DC2626",
    "warning": "#D97706", "purple": "#7C3AED",
    "bars": ["#2563EB", "#16A34A", "#DC2626", "#D97706", "#7C3AED",
             "#0891B2", "#DB2777", "#65A30D", "#EA580C", "#4F46E5"],
}

MAX_HISTORY_TURNS = 6  # recent user/assistant turns replayed to the model for context
MAX_LLM_TEXT_CHARS = 280
# Row docs pack many "col=value" pairs onto one line (a 21-column row already runs
# ~450 chars) - the 280/320 limit used for short fact sentences was silently cutting
# off the last several columns (price, discount, etc.) on every retrieved row before
# the model ever saw them. Rows get their own, larger budget instead.
MAX_LLM_ROW_TEXT_CHARS = 600
MAX_LLM_USER_CONTENT_CHARS = 12000
GEMINI_COOLDOWN_SECONDS = 60
ALLOWED_CHART_TYPES = {"bar", "line", "histogram", "box", "scatter"}

# Data-query engine (see "6 - AD-HOC DATA QUERIES" below): a fixed whitelist of pandas
# operations/filter operators the LLM can request by name. The LLM never supplies code -
# only these validated parameters - so there's no eval/exec surface here.
ALLOWED_QUERY_OPERATIONS = {"count", "sum", "mean", "median", "min", "max", "nunique", "missing"}
ALLOWED_QUERY_FILTER_OPS = {"==", "!=", ">", ">=", "<", "<=", "contains"}
MAX_QUERY_FILTERS = 5
MAX_QUERY_GROUP_RESULTS = 20

_GEMINI_RETRY_AT = 0.0
_GEMINI_DISABLED_BY_QUOTA = False


def _disable_gemini_due_to_quota(reason: str) -> None:
    global _GEMINI_DISABLED_BY_QUOTA, _GEMINI_RETRY_AT
    _GEMINI_DISABLED_BY_QUOTA = True
    _GEMINI_RETRY_AT = float("inf")
    print(f"[Chat] Gemini disabled for this process after quota error: {reason}")


def _gemini_is_disabled() -> bool:
    return _GEMINI_DISABLED_BY_QUOTA


# ─────────────────────────────────────────────────────────────────────────────
# 1 — GROUNDED CONTEXT (no LLM, no raw rows)
# ─────────────────────────────────────────────────────────────────────────────

def build_dataset_context(result: dict[str, Any]) -> dict[str, Any]:
    """Condense the already-computed analysis result into compact chat facts."""
    result = result or {}
    summary = result.get("summary", {}) or {}
    stats = result.get("stats", {}) or {}
    correlation = stats.get("correlation", {}) or {}
    regression = stats.get("regression", {}) or {}
    narrative = result.get("insight_narrative", {}) or {}
    schema_blueprint = result.get("schema_blueprint", {}) or {}

    schema = {
        col: {"semantic_tag": meta.get("semantic_tag"), "intended_type": meta.get("intended_type")}
        for col, meta in schema_blueprint.items()
        if isinstance(meta, dict) and col != "__metadata__"
    }
    significant_trends = {
        col: metrics for col, metrics in regression.items()
        if isinstance(metrics, dict) and metrics.get("significant")
    }
    significant_trends = dict(sorted(
        significant_trends.items(),
        key=lambda item: float(item[1].get("r_squared") or 0),
        reverse=True,
    )[:8])

    return {
        "dataset": {
            "filename": summary.get("filename"),
            "rows": summary.get("rows"),
            "columns": summary.get("columns"),
            "quality_score": summary.get("quality_score"),
        },
        "chart_plan": stats.get("chart_plan", {}),
        "available_columns": schema,
        "descriptive_stats": stats.get("descriptive", {}),
        "strong_correlations": (correlation.get("strong_pairs") or [])[:8],
        "growth_rates": stats.get("growth_rates", {}),
        "seasonality": stats.get("seasonality", {}),
        "top_bottom_rankings": stats.get("top_bottom", {}),
        "anomaly_summary": stats.get("anomaly_summary", {}),
        "significant_trends": significant_trends,
        "category_distributions": stats.get("distributions", {}),
        "validation": result.get("validation", {}),
        "reliability": result.get("reliability", {}),
        "executive_summary": narrative.get("executive_summary"),
        "key_findings": narrative.get("key_findings", []),
        "existing_charts": [c.get("name") for c in (result.get("charts") or [])],
    }


def _condense_history(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    trimmed = (history or [])[-(MAX_HISTORY_TURNS * 2):]
    return [
        {"role": m.get("role"), "content": m.get("content")}
        for m in trimmed
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]


def _truncate_text(value: Any, limit: int = MAX_LLM_TEXT_CHARS) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _is_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(term in text for term in ("429", "resource_exhausted", "quota exceeded", "rate limit"))


def _quota_retry_delay_seconds(exc: Exception) -> int:
    text = str(exc)
    match = re.search(r"retry in\s+(\d+(?:\.\d+)?)s", text, re.IGNORECASE)
    if match:
        try:
            return max(5, int(float(match.group(1))))
        except ValueError:
            pass
    retry_match = re.search(r"retryDelay['\"]?:\s*['\"]?(\d+)s", text, re.IGNORECASE)
    if retry_match:
        try:
            return max(5, int(retry_match.group(1)))
        except ValueError:
            pass
    return GEMINI_COOLDOWN_SECONDS


# ─────────────────────────────────────────────────────────────────────────────
# 2 — RAG CHAT (Groq to Gemini fallback, same provider chain as Agent 6)
# ─────────────────────────────────────────────────────────────────────────────

RAG_CHAT_SYSTEM_PROMPT = """You are a data analyst assistant answering questions about one \
already-analyzed dataset using RETRIEVED evidence, not the whole dataset.

You will be given two kinds of retrieved documents:
- "facts": deterministic statistics/analysis computed over the FULL dataset (schema, descriptive \
stats, correlations, growth rates, rankings, anomalies, regression trends, categorical value \
counts / distributions, quality/validation scores, narrative summary, and charts already \
generated). Trust these completely for anything aggregate or dataset-wide — including "most \
common / most used / share of" questions about a categorical column when a "Value counts for \
'<column>'" fact is present.
- "rows": a SAMPLE of actual data rows (only some of the dataset's rows are indexed, not all of \
them). Use these ONLY for concrete record-level lookups or examples. NEVER claim a row-level \
answer is complete or exhaustive beyond what is shown here - if the retrieved rows don't contain \
the specific record asked about, say honestly that it isn't among the indexed sample.

IMPORTANT - before you say a precise number is unavailable, check this first: if the question \
asks for a PRECISE count, sum, average, min/max, distinct count, count of missing/blank values, \
or a filtered/grouped aggregate that ISN'T verbatim in the retrieved facts (e.g. "how many \
orders were cancelled", "average discount for Electronics", "total revenue from UPI payments", \
"orders over 20% discount", "how many rows are missing a region") - this is NOT a case of "not \
enough information". Do NOT estimate it from the small row sample, and do NOT say it's \
unavailable. Set "needs_data_query" to true and fill "data_query" using ONLY column names that \
appear in the retrieved documents - the "All N queryable columns" overview fact lists every \
column you may use, including derived ones like profit margin. It will be computed exactly \
against the full cleaned dataset and your answer will be regenerated with the real number \
afterward. Set "answer" to a brief holding message like "Let me get the exact number for you." \
in this case.

Example - question: "How many orders in the Electronics category had a discount over 20%?"
{
  "answer": "Let me get the exact number for you.",
  "needs_new_chart": false, "chart_request": null,
  "needs_data_query": true,
  "data_query": {
    "operation": "count", "column": null,
    "filters": [{"column": "category", "op": "==", "value": "Electronics"},
                {"column": "discount", "op": ">", "value": "0.2"}],
    "group_by": null
  }
}

Rules:
- Use ONLY the numbers, column names, and facts present in the retrieved documents (or a \
requested data_query result). Never invent a number, column, or record that isn't there.
- If the question is genuinely unanswerable from the dataset (not a data_query case above), say \
so honestly instead of guessing.
- Be concise, conversational, and business-readable.
- If an existing chart (see the "existing_charts" fact) already answers the question, reference \
it and do not request a new one.
- If the question needs a NEW chart that isn't already available, set "needs_new_chart" to true \
and fill "chart_request" using ONLY column names mentioned in the retrieved documents.

Return ONLY a JSON object with exactly these keys:
{
  "answer": "conversational answer to the user's question, grounded in the retrieved documents",
  "needs_new_chart": true or false,
  "chart_request": {
    "chart_type": "bar" | "line" | "histogram" | "box" | "scatter",
    "x_column": "column name",
    "y_column": "column name, or null for histogram/box",
    "group_by": "column name, or null",
    "aggregation": "sum" | "mean" | "count" | "median",
    "title": "short chart title"
  } or null,
  "needs_data_query": true or false,
  "data_query": {
    "operation": "count" | "sum" | "mean" | "median" | "min" | "max" | "nunique" | "missing",
    "column": "column name to aggregate (required for everything except a plain count); for 'missing' this is the column whose blank/NaN rows are counted",
    "filters": [{"column": "column name", "op": "==" | "!=" | ">" | ">=" | "<" | "<=" | "contains", "value": "..."}],
    "group_by": "column name for a per-group breakdown, or null for a single overall number"
  } or null
}
"""


def _build_rag_user_content(retrieved: dict[str, Any], question: str, history: list[dict[str, str]]) -> str:
    import json

    facts = retrieved.get("facts") or []
    rows = retrieved.get("rows") or []
    # Most facts are one short sentence; the column list and per-column value
    # counts are the useful-when-long exceptions the data-query engine relies on.
    _fact_budget = {"columns_overview": 1600, "category_distribution": 700}
    compact_facts = [
        {"type": doc.get("doc_type"),
         "text": _truncate_text(doc.get("doc_text"), _fact_budget.get(doc.get("doc_type"), 320))}
        for doc in facts
        if doc.get("doc_text")
    ]
    compact_rows = [
        {"row_index": doc.get("row_index"), "text": _truncate_text(doc.get("doc_text"), MAX_LLM_ROW_TEXT_CHARS)}
        for doc in rows
        if doc.get("doc_text")
    ]
    compact_history = [
        {"role": turn.get("role"), "content": _truncate_text(turn.get("content"), 400)}
        for turn in history[-4:]
        if turn.get("role") in ("user", "assistant") and turn.get("content")
    ]

    user_content = (
        f"Retrieved facts (computed over the FULL dataset):\n"
        f"{json.dumps(compact_facts, separators=(',', ':'), default=str)}\n\n"
        f"Retrieved sample rows (NOT the whole dataset - {len(compact_rows)} row(s) shown):\n"
        f"{json.dumps(compact_rows, separators=(',', ':'), default=str)}\n\n"
        f"Conversation so far:\n{json.dumps(compact_history, separators=(',', ':'), default=str)}\n\n"
        f"User question: {question}"
    )

    if len(user_content) > MAX_LLM_USER_CONTENT_CHARS:
        # Drop sample rows first (facts carry the aggregate answer for most
        # questions), then trim history, before falling back to a minimal cut.
        user_content = (
            f"Retrieved facts (computed over the FULL dataset):\n"
            f"{json.dumps(compact_facts, separators=(',', ':'), default=str)}\n\n"
            f"Conversation so far:\n{json.dumps(compact_history[-2:], separators=(',', ':'), default=str)}\n\n"
            f"User question: {question}"
        )
    if len(user_content) > MAX_LLM_USER_CONTENT_CHARS:
        user_content = user_content[:MAX_LLM_USER_CONTENT_CHARS]

    return user_content


def _call_groq_then_gemini_json(
    *,
    system_prompt: str,
    user_content: str,
    groq_max_tokens: int = 1024,
    gemini_max_tokens: int = 512,
    temperature: float = 0.3,
) -> dict[str, Any]:
    """Ask Groq for a JSON response, falling back to Gemini on provider failure.

    Shared by the main RAG chat turn and the data-query answer-rephrasing follow-up
    call below - same provider chain, same quota/cooldown handling, different prompt.
    """
    try:
        response = _get_groq_client().chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=temperature,
            max_tokens=groq_max_tokens,
            reasoning_effort=GROQ_REASONING_EFFORT,
        )
        raw_text = response.choices[0].message.content.strip()
        parsed = _parse_schema_blueprint_response(raw_text)
        parsed["source"] = "groq"
        return parsed
    except Exception as groq_error:
        print(f"[Chat] Groq unavailable; trying Gemini: {groq_error}")

    global _GEMINI_RETRY_AT
    if _gemini_is_disabled():
        raise RuntimeError("Gemini disabled after quota exhaustion; using fallback")

    now = time.monotonic()
    if now < _GEMINI_RETRY_AT:
        remaining = int(round(_GEMINI_RETRY_AT - now))
        raise RuntimeError(f"Gemini temporarily skipped after quota error; retry in {remaining}s")

    try:
        parsed = _call_gemini_json_with_failover(
            contents=user_content,
            system_instruction=system_prompt,
            temperature=temperature,
            max_output_tokens=gemini_max_tokens,
        )
        parsed["source"] = "gemini"
        return parsed
    except Exception as gemini_error:
        if _is_quota_error(gemini_error):
            _disable_gemini_due_to_quota(str(gemini_error))
        raise


def _call_llm_for_rag_chat(retrieved: dict[str, Any], question: str, history: list[dict[str, str]]) -> dict[str, Any]:
    """Ask Groq for a grounded RAG chat answer, falling back to Gemini on provider failure."""
    user_content = _build_rag_user_content(retrieved, question, history)
    return _call_groq_then_gemini_json(
        system_prompt=RAG_CHAT_SYSTEM_PROMPT,
        user_content=user_content,
        groq_max_tokens=1024,
        gemini_max_tokens=512,
        temperature=0.3,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3 — DETERMINISTIC FALLBACK (no LLM providers available)
# ─────────────────────────────────────────────────────────────────────────────

def _fallback_answer(context: dict[str, Any], question: str) -> dict[str, Any]:
    """Keyword-matched, LLM-free answer built directly from the grounded facts.
    Never proposes a new chart — that requires a model to ground column choices."""
    q = question.lower()
    dataset = context.get("dataset", {})

    if any(k in q for k in ("correlat", "relationship", "related")):
        pairs = context.get("strong_correlations") or []
        if pairs:
            lines = [f"{p['col1']} and {p['col2']} ({p['strength']} {p['direction']}, r={p['pearson_r']})" for p in pairs[:3]]
            answer = "Here are the strongest relationships I found: " + "; ".join(lines) + "."
        else:
            answer = "I didn't find any strong correlations between the numeric columns in this dataset."
    elif any(k in q for k in ("trend", "growth", "season")):
        growth = context.get("growth_rates") or {}
        season = context.get("seasonality") or {}
        if season.get("monthly"):
            best = season["monthly"].get("best_month", {})
            worst = season["monthly"].get("worst_month", {})
            answer = f"The strongest month was {best.get('month')} and the weakest was {worst.get('month')}."
        elif growth.get("monthly"):
            latest = growth["monthly"][-1]
            answer = f"The most recent month-over-month growth was {latest.get('mom_growth_pct')}%."
        else:
            answer = "I couldn't find a clear growth or seasonality signal for this dataset."
    elif any(k in q for k in ("top", "best", "rank", "worst", "bottom")):
        rankings = context.get("top_bottom_rankings") or {}
        if rankings:
            col = next(iter(rankings))
            top = (rankings[col].get("top") or [None])[0]
            answer = f"For {col}, the top performer is {top.get(col)} at {top.get('revenue_share_pct')}% share." if top else "I have ranking data but couldn't extract a clear leader."
        else:
            answer = "I don't have ranking data for this dataset."
    elif any(k in q for k in ("most common", "most used", "most frequent", "most popular",
                              "distribution", "breakdown", "proportion", "share of")):
        dists = context.get("category_distributions") or {}
        if dists:
            chosen = next((c for c in dists if c.lower() in q), None) or next(iter(dists))
            records = dists.get(chosen) or []
            if records:
                def _label(rec: dict[str, Any]) -> str:
                    val = rec.get(chosen)
                    return "(missing)" if val is None or str(val).strip().lower() in ("", "nan", "none") else str(val)
                top = records[0]
                spread = ", ".join(f"{_label(r)} ({r.get('pct')}%)" for r in records[:3])
                answer = (
                    f"For {chosen}, the most common value is {_label(top)} at {top.get('pct')}% "
                    f"({top.get('count')} rows). Top values: {spread}."
                )
            else:
                answer = f"I have a breakdown for {chosen} but couldn't read a clear leader."
        else:
            answer = "I don't have a categorical breakdown for this dataset."
    elif any(k in q for k in ("anomal", "outlier", "unusual", "weird")):
        anomaly = context.get("anomaly_summary") or {}
        if anomaly.get("unique_flagged_rows"):
            answer = f"{anomaly.get('unique_flagged_rows')} rows ({anomaly.get('unique_flagged_row_pct')}%) look unusual compared to the rest."
        else:
            answer = "No significant anomalies were flagged in this dataset."
    elif any(k in q for k in ("quality", "trust", "confidence", "reliable")):
        answer = (
            f"This dataset scored {dataset.get('quality_score')} on data quality, "
            f"with an overall pipeline confidence of {context.get('reliability', {}).get('overall_confidence')}."
        )
    elif any(k in q for k in ("missing", "null", "blank", "empty", "incomplete", "gaps")):
        stats = context.get("descriptive_stats") or {}
        worst = sorted(
            ((c, m.get("missing_pct")) for c, m in stats.items() if m.get("missing_pct")),
            key=lambda kv: kv[1] or 0, reverse=True,
        )[:3]
        if worst:
            lines = ", ".join(f"{c} ({pct}% missing)" for c, pct in worst)
            answer = f"The columns with the most missing values are: {lines}."
        else:
            answer = (
                f"Overall data quality is {dataset.get('quality_score')}; no numeric column stands "
                "out as heavily incomplete. Ask for a specific column to get an exact count."
            )
    elif any(k in q for k in ("what column", "which column", "what field", "list column",
                              "schema", "what data", "columns are")):
        cols = context.get("available_columns") or {}
        if cols:
            listed = ", ".join(
                f"{c} ({m.get('intended_type') or m.get('semantic_tag') or 'unknown'})"
                for c, m in list(cols.items())[:40]
            )
            more = "" if len(cols) <= 40 else f" (+{len(cols) - 40} more)"
            answer = f"This dataset has {len(cols)} columns: {listed}{more}."
        else:
            answer = f"This dataset has {dataset.get('columns')} columns."
    else:
        summary = context.get("executive_summary")
        answer = summary or (
            f"This dataset has {dataset.get('rows')} rows and {dataset.get('columns')} columns. "
            "Ask me about correlations, trends, rankings, distributions, missing values, "
            "anomalies, or data quality for more detail."
        )

    return {"answer": answer, "needs_new_chart": False, "chart_request": None, "source": "fallback"}


def build_fallback_chat_response(job: "Job", question: str) -> dict[str, Any]:
    """Build a safe fallback response directly from the stored analysis result."""
    context = build_dataset_context(job.result or {})
    return _fallback_answer(context, question)


# ─────────────────────────────────────────────────────────────────────────────
# 4 — AD-HOC CHART GENERATION (constrained, validated, no arbitrary code)
# ─────────────────────────────────────────────────────────────────────────────

def _column_usable(df: pd.DataFrame, schema_blueprint: dict, col: str | None) -> bool:
    if not col or col not in df.columns:
        return False
    meta = schema_blueprint.get(col, {}) if isinstance(schema_blueprint, dict) else {}
    return meta.get("analysis_allowed") is not False


def _save_chat_chart(fig, job_id: str) -> str:
    filename = f"chat_{job_id[:8]}_{uuid.uuid4().hex[:8]}.png"
    path = os.path.join(CHARTS_DIR, filename)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def render_chart_request(
    df: pd.DataFrame,
    schema_blueprint: dict,
    chart_request: dict[str, Any],
    job_id: str,
) -> tuple[bool, str]:
    """Validate and render an on-demand chart. Returns (ok, path_or_reason)."""
    chart_type = str(chart_request.get("chart_type", "")).lower()
    x_col = chart_request.get("x_column")
    y_col = chart_request.get("y_column")
    group_by = chart_request.get("group_by")
    agg = str(chart_request.get("aggregation") or "sum").lower()
    title = chart_request.get("title") or "Requested Chart"

    if chart_type not in ALLOWED_CHART_TYPES:
        return False, f"unsupported chart type '{chart_type}'"
    if agg not in {"sum", "mean", "count", "median"}:
        agg = "sum"

    try:
        if chart_type == "histogram":
            if not _column_usable(df, schema_blueprint, x_col) or not pd.api.types.is_numeric_dtype(df[x_col]):
                return False, f"column '{x_col}' is not a usable numeric column"
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.hist(df[x_col].dropna(), bins=20, color=COLORS["primary"], alpha=0.85)
            ax.set_title(title, fontsize=13, fontweight="bold")
            ax.set_xlabel(x_col)
            fig.tight_layout()
            return True, _save_chat_chart(fig, job_id)

        if chart_type == "box":
            if not _column_usable(df, schema_blueprint, x_col) or not pd.api.types.is_numeric_dtype(df[x_col]):
                return False, f"column '{x_col}' is not a usable numeric column"
            if group_by and _column_usable(df, schema_blueprint, group_by) and df[group_by].nunique(dropna=True) <= 10:
                groups = [g.dropna().values for _, g in df.groupby(group_by)[x_col]]
                labels = [str(k) for k in df.groupby(group_by)[x_col].groups.keys()]
                fig, ax = plt.subplots(figsize=(max(6, len(labels) * 1.2), 4))
                bp = ax.boxplot(groups, patch_artist=True, tick_labels=labels)
                for patch, color in zip(bp["boxes"], COLORS["bars"]):
                    patch.set_facecolor(color)
                    patch.set_alpha(0.7)
            else:
                fig, ax = plt.subplots(figsize=(5, 4))
                bp = ax.boxplot([df[x_col].dropna().values], patch_artist=True, tick_labels=[x_col])
                bp["boxes"][0].set_facecolor(COLORS["primary"])
                bp["boxes"][0].set_alpha(0.7)
            ax.set_title(title, fontsize=13, fontweight="bold")
            fig.tight_layout()
            return True, _save_chat_chart(fig, job_id)

        if chart_type == "scatter":
            if not _column_usable(df, schema_blueprint, x_col) or not pd.api.types.is_numeric_dtype(df[x_col]):
                return False, f"column '{x_col}' is not a usable numeric column"
            if not _column_usable(df, schema_blueprint, y_col) or not pd.api.types.is_numeric_dtype(df[y_col]):
                return False, f"column '{y_col}' is not a usable numeric column"
            fig, ax = plt.subplots(figsize=(7, 5))
            ax.scatter(df[x_col], df[y_col], color=COLORS["primary"], alpha=0.6, s=24)
            ax.set_xlabel(x_col)
            ax.set_ylabel(y_col)
            ax.set_title(title, fontsize=13, fontweight="bold")
            fig.tight_layout()
            return True, _save_chat_chart(fig, job_id)

        # bar / line — need a groupable x_column and a numeric y_column
        if not _column_usable(df, schema_blueprint, x_col):
            return False, f"column '{x_col}' is not usable for this chart"
        if not _column_usable(df, schema_blueprint, y_col) or not pd.api.types.is_numeric_dtype(df[y_col]):
            return False, f"column '{y_col}' is not a usable numeric column"

        grouped = df.groupby(x_col)[y_col].agg(agg).reset_index().sort_values(y_col, ascending=False)
        grouped = grouped.head(15)
        labels = [str(v) for v in grouped[x_col]]

        fig, ax = plt.subplots(figsize=(max(6, len(labels) * 0.8), 4))
        if chart_type == "line":
            ax.plot(labels, grouped[y_col], marker="o", color=COLORS["primary"], linewidth=2)
        else:
            ax.bar(labels, grouped[y_col], color=COLORS["bars"][: len(labels)], alpha=0.88)
        ax.set_title(title, fontsize=13, fontweight="bold")
        ax.set_xlabel(x_col)
        ax.set_ylabel(f"{agg}({y_col})")
        plt.xticks(rotation=45, ha="right")
        fig.tight_layout()
        return True, _save_chat_chart(fig, job_id)

    except Exception as exc:  # noqa: BLE001 — chart generation must never crash the chat request
        return False, f"chart rendering failed ({exc})"


# ─────────────────────────────────────────────────────────────────────────────
# 5 — AD-HOC DATA QUERIES (constrained aggregate/filter queries, no arbitrary code)
# ─────────────────────────────────────────────────────────────────────────────
#
# Facts and the 8-row sample can't answer precise counts/sums/filtered aggregates
# ("how many orders were cancelled", "average discount for Electronics") - facts only
# cover what Agents 1-6 already precomputed, and the row sample is too small and too
# narrow (only ~30% of rows by default) to aggregate from reliably. This runs a real,
# validated pandas query against the FULL dataset instead.
#
# Source (see _load_job_dataframe): Agent 3's in-memory cleaned frame when it's
# still resident — type-coerced, deduplicated, text-normalized, with derived
# business-metric / date-part columns and scaled columns swapped back to their
# raw values — otherwise a re-read of the per-job upload (job.csv_path, NOT the
# shared cleaned_data.csv export, which agent_3._export_cleaned_dataset
# overwrites for every job). Encoded one-hot/ordinal columns stay unqueryable
# via the schema_blueprint analysis_allowed=False guard.

_QUERY_DF_CACHE: dict[str, tuple[float, pd.DataFrame]] = {}  # job_id -> (csv mtime, df)
_QUERY_DF_CACHE_MAX = 4  # bound resident full DataFrames — one per recent chat session


def _load_job_dataframe(job: "Job") -> pd.DataFrame | None:
    """Return the DataFrame ad-hoc data queries run against.

    Prefers Agent 3's cleaned frame when it's still in memory: it has the
    type-coerced values (so ``discount > 0.2`` actually compares numerically),
    deduplicated rows (so counts match the analysis), normalized text (so
    ``nunique`` isn't split by "Card"/"card"/" CARD "), and the derived
    business-metric / date-part columns (so "average profit margin" is
    answerable even when no literal margin column was uploaded).

    Falls back to re-reading the original per-job upload — cached per job_id,
    mtime-invalidated, and capped at ``_QUERY_DF_CACHE_MAX`` entries — for jobs
    whose in-memory state is gone (e.g. after a process restart).
    """
    state = getattr(job, "state", None) or {}
    cleaned = state.get("cleaned_df")
    if isinstance(cleaned, pd.DataFrame) and not cleaned.empty:
        # Agent 3 overwrites scaling-allowed numeric columns in place with their
        # 0-1 Min-Max values (keeping a "<col>_raw" backup). Swap those back so
        # an aggregate like "average rating" returns the real number, not ~0.4.
        scaling_params = state.get("scaling_params") or {}
        restorable = {
            col: p["raw_col"]
            for col, p in scaling_params.items()
            if isinstance(p, dict) and p.get("raw_col") in cleaned.columns and col in cleaned.columns
        }
        if restorable:
            cleaned = cleaned.copy()
            for col, raw_col in restorable.items():
                cleaned[col] = cleaned[raw_col]
        return cleaned

    if not job.csv_path or not os.path.exists(job.csv_path):
        return None
    mtime = os.path.getmtime(job.csv_path)
    cached = _QUERY_DF_CACHE.get(job.job_id)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    df = pd.read_csv(job.csv_path, low_memory=False)
    if len(_QUERY_DF_CACHE) >= _QUERY_DF_CACHE_MAX and job.job_id not in _QUERY_DF_CACHE:
        _QUERY_DF_CACHE.pop(next(iter(_QUERY_DF_CACHE)))  # evict oldest (insertion order)
    _QUERY_DF_CACHE[job.job_id] = (mtime, df)
    return df


def _coerce_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _apply_query_filter(df: pd.DataFrame, column: str, op: str, value: Any) -> pd.Series:
    """Return a boolean mask for one filter clause. Numeric comparison when the column
    and value both parse as numbers, case-insensitive text match otherwise."""
    series = df[column]
    if op == "contains":
        # regex=False: treat the value as a literal substring. Without it "c."
        # or "(" from the LLM would be interpreted as a regex (or raise).
        return series.astype(str).str.contains(str(value), case=False, na=False, regex=False)

    numeric_series = _coerce_numeric(series)
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        numeric_value = None

    if numeric_value is not None and numeric_series.notna().any():
        if op == "==":
            return numeric_series == numeric_value
        if op == "!=":
            return numeric_series != numeric_value
        if op == ">":
            return numeric_series > numeric_value
        if op == ">=":
            return numeric_series >= numeric_value
        if op == "<":
            return numeric_series < numeric_value
        if op == "<=":
            return numeric_series <= numeric_value

    str_series = series.astype(str).str.strip().str.lower()
    str_value = str(value).strip().lower()
    if op == "==":
        return str_series == str_value
    if op == "!=":
        return str_series != str_value
    raise ValueError(f"operator '{op}' requires a numeric column, but '{column}' isn't one")


def run_data_query(job: "Job", schema_blueprint: dict, query: dict[str, Any]) -> tuple[bool, Any]:
    """Validate and execute a constrained aggregate query against the job's full dataset.

    No arbitrary code execution: column names must exist in the loaded DataFrame and pass
    _column_usable (rejecting encoded one-hot/ordinal columns); operations and filter
    operators come from a fixed whitelist and are dispatched through explicit branches,
    never through a dynamic eval of LLM-supplied text. The LLM only ever supplies these
    structured parameters - never code.

    Returns (True, result_dict) on success or (False, reason) on validation/execution failure.
    """
    df = _load_job_dataframe(job)
    if df is None:
        return False, "the original dataset file for this job is no longer available"

    operation = str(query.get("operation") or "").lower()
    column = query.get("column")
    group_by = query.get("group_by")
    filters = query.get("filters") or []

    if operation not in ALLOWED_QUERY_OPERATIONS:
        return False, f"unsupported operation '{operation}'"
    if column and (column not in df.columns or not _column_usable(df, schema_blueprint, column)):
        return False, f"column '{column}' is not usable for queries"
    if group_by and (group_by not in df.columns or not _column_usable(df, schema_blueprint, group_by)):
        return False, f"column '{group_by}' is not usable for queries"
    if operation != "count" and not column:
        return False, f"operation '{operation}' requires a column"
    if not isinstance(filters, list) or len(filters) > MAX_QUERY_FILTERS:
        return False, f"too many filters (max {MAX_QUERY_FILTERS})"

    working = df
    applied_filters: list[str] = []
    for f in filters:
        if not isinstance(f, dict):
            continue
        fcol, fop, fval = f.get("column"), str(f.get("op") or "").lower(), f.get("value")
        if fcol not in df.columns or not _column_usable(df, schema_blueprint, fcol):
            return False, f"invalid filter column '{fcol}'"
        if fop not in ALLOWED_QUERY_FILTER_OPS:
            return False, f"invalid filter operator '{fop}'"
        try:
            mask = _apply_query_filter(working, fcol, fop, fval)
        except Exception as exc:  # noqa: BLE001 — surfaced as a clean validation failure
            return False, f"filter on '{fcol}' failed ({exc})"
        working = working[mask]
        applied_filters.append(f"{fcol} {fop} {fval}")

    total_groups = 0
    try:
        if group_by:
            if operation == "count":
                series = working.groupby(group_by).size()
            elif operation == "nunique":
                series = working.groupby(group_by)[column].nunique()
            elif operation == "missing":
                series = working[column].isna().groupby(working[group_by]).sum()
            else:
                series = _coerce_numeric(working[column]).groupby(working[group_by]).agg(operation)
            series = series.sort_values(ascending=False)
            total_groups = int(series.shape[0])
            series = series.head(MAX_QUERY_GROUP_RESULTS)
            result: Any = {str(k): v for k, v in series.items()}
        elif operation == "count":
            result = len(working)
        elif operation == "nunique":
            result = working[column].nunique()
        elif operation == "missing":
            result = int(working[column].isna().sum())
        else:
            result = getattr(_coerce_numeric(working[column]), operation)()
    except Exception as exc:  # noqa: BLE001 — a query must never crash the chat request
        return False, f"query execution failed ({exc})"

    payload = {
        "operation": operation,
        "column": column,
        "group_by": group_by,
        "filters_applied": applied_filters,
        "matched_rows": len(working),
        "result": result,
    }
    if group_by:
        payload["groups_total"] = total_groups
        payload["groups_shown"] = len(result)
        payload["truncated"] = total_groups > len(result)
    return True, json_safe(payload)


DATA_QUERY_ANSWER_SYSTEM_PROMPT = """You are a data analyst. You previously requested a precise \
computed result to answer the user's question, and it has now been computed exactly from the \
FULL dataset (not a sample). Write a short, conversational final answer using ONLY this computed \
result plus the other retrieved facts already provided - do not invent, recompute, or \
second-guess any number.

If "group_by" is set, "result" is a dict of {group value: aggregated value}, sorted highest \
first. When "truncated" is true it holds only "groups_shown" of "groups_total" groups - say \
explicitly that it's the top N of M. If "operation" is "missing", the numbers are counts of \
blank/NaN values.

Return ONLY a JSON object with exactly this key:
{"answer": "conversational final answer to the user's original question"}
"""


def _call_llm_for_query_answer(
    question: str,
    computed_result: dict[str, Any],
    retrieved: dict[str, Any],
    history: list[dict[str, str]],
) -> dict[str, Any]:
    """Ask Groq/Gemini to phrase the final answer now that the exact number is known."""
    import json

    compact_facts = [
        {"type": doc.get("doc_type"), "text": _truncate_text(doc.get("doc_text"), 320)}
        for doc in (retrieved.get("facts") or [])
        if doc.get("doc_text")
    ]
    compact_history = [
        {"role": turn.get("role"), "content": _truncate_text(turn.get("content"), 400)}
        for turn in history[-4:]
        if turn.get("role") in ("user", "assistant") and turn.get("content")
    ]
    user_content = (
        f"Original question: {question}\n\n"
        f"Computed result (exact, from the full dataset):\n"
        f"{json.dumps(computed_result, separators=(',', ':'), default=str)}\n\n"
        f"Other retrieved facts:\n{json.dumps(compact_facts, separators=(',', ':'), default=str)}\n\n"
        f"Conversation so far:\n{json.dumps(compact_history, separators=(',', ':'), default=str)}"
    )
    return _call_groq_then_gemini_json(
        system_prompt=DATA_QUERY_ANSWER_SYSTEM_PROMPT,
        user_content=user_content,
        groq_max_tokens=512,
        gemini_max_tokens=256,
        temperature=0.2,
    )


def _apply_data_query(
    job: "Job",
    question: str,
    answer: str,
    source: str,
    llm_out: dict[str, Any],
    retrieved: dict[str, Any],
    history: list[dict[str, str]],
) -> tuple[str, str]:
    """Execute a requested data query (if any) and rephrase the answer with the exact result.

    A data query must never hard-fail a chat turn: an invalid request, an execution error,
    or both LLM providers failing on the rephrasing call all fall back to leaving the
    first-pass answer in place (with a short explanatory note) rather than raising.
    """
    if not (llm_out.get("needs_data_query") and llm_out.get("data_query")):
        return answer, source

    state = job.state or {}
    schema_blueprint = state.get("schema_blueprint", {}) or {}
    ok, result_or_reason = run_data_query(job, schema_blueprint, llm_out["data_query"])
    if not ok:
        return answer + f"\n\n(I couldn't compute that precisely — {result_or_reason}.)", source

    try:
        phrased = _call_llm_for_query_answer(question, result_or_reason, retrieved, history)
        new_answer = phrased.get("answer")
        if new_answer:
            return new_answer, phrased.get("source", source)
    except Exception as exc:  # noqa: BLE001 — never hard-fail on the rephrasing call
        print(f"[Chat] Data query computed but rephrasing failed, using raw result: {exc}")

    note = (
        f"\n\n(Computed result: {result_or_reason.get('result')!r}, "
        f"from {result_or_reason.get('matched_rows')} matching row(s)."
    )
    if result_or_reason.get("truncated"):
        note += (
            f" Showing the top {result_or_reason.get('groups_shown')} of "
            f"{result_or_reason.get('groups_total')} groups."
        )
    return answer + note + ")", source


# ─────────────────────────────────────────────────────────────────────────────
# 6 — PUBLIC ENTRYPOINT
# ─────────────────────────────────────────────────────────────────────────────

def _apply_chart_request(job: "Job", answer: str, llm_out: dict[str, Any]) -> tuple[str, dict[str, str] | None, bool]:
    """Render a requested chart (if any) and fold any failure reason into the answer text."""
    chart_dict: dict[str, str] | None = None
    chart_generated = False

    if llm_out.get("needs_new_chart") and llm_out.get("chart_request"):
        state = job.state or {}
        df = state.get("cleaned_df")
        schema_blueprint = state.get("schema_blueprint", {}) or {}
        if isinstance(df, pd.DataFrame):
            ok, path_or_reason = render_chart_request(df, schema_blueprint, llm_out["chart_request"], job.job_id)
            if ok:
                chart_dict = chart_url(path_or_reason)
                chart_generated = True
            else:
                answer += f"\n\n(I couldn't generate that chart — {path_or_reason}.)"
        else:
            answer += "\n\n(The underlying dataset for this job is no longer available for new charts.)"

    return answer, chart_dict, chart_generated


def ask_question(manager: "JobManager", job: "Job", question: str) -> dict[str, Any]:
    """Answer a user's question about ``job``'s analyzed dataset using retrieval-augmented chat.

    Falls back to a deterministic, facts-only answer whenever the vector index isn't
    configured, is still being built, or failed to build - the chat feature must never
    hard-fail a turn just because RAG infrastructure is unavailable.
    """
    settings = get_settings()
    context = build_dataset_context(job.result or {})

    if not settings.database_url:
        out = _fallback_answer(context, question)
        out["answer"] += (
            " (Detailed row-level answers aren't available right now because no database is "
            "configured for this deployment - I'm using the summary analysis facts instead.)"
        )
        out["index_status"] = "unavailable"
        return out

    status = getattr(job, "rag_status", "not_built")

    if status == "not_built":
        rag_service.start_rag_build(manager, job)
        return {
            "answer": (
                "Give me a moment to index this dataset for detailed Q&A — I'm reading through "
                "the rows now. Ask again in a few seconds."
            ),
            "source": "fallback",
            "chart": None,
            "chart_generated": False,
            "index_status": "building",
        }

    if status == "building":
        # A build whose worker thread died (host spun down mid-run) would sit in
        # "building" forever. Reap it if it's been silent too long, then kick off
        # a fresh one so this isn't a permanent dead end.
        if manager.maybe_expire_rag_build(job.job_id):
            rag_service.start_rag_build(manager, job)
            return {
                "answer": (
                    "The previous indexing run stalled, so I've restarted it. "
                    "Ask again in a few seconds."
                ),
                "source": "fallback",
                "chart": None,
                "chart_generated": False,
                "index_status": "building",
            }
        return {
            "answer": "Still indexing this dataset for detailed Q&A — try again in a few seconds.",
            "source": "fallback",
            "chart": None,
            "chart_generated": False,
            "index_status": "building",
        }

    if status == "failed":
        out = _fallback_answer(context, question)
        reason = getattr(job, "rag_error", None) or "unknown error"
        out["answer"] += f" (Detailed row-level indexing failed ({reason}); using summary facts instead.)"
        out["index_status"] = "failed"
        return out

    # status == "ready"
    history = _condense_history(job.chat_history)

    try:
        retrieved = rag_service.retrieve(job.job_id, question)
    except Exception as exc:  # noqa: BLE001 — never hard-fail a chat turn on retrieval errors
        print(f"[Chat] RAG retrieval failed, using fallback: {exc}")
        out = _fallback_answer(context, question)
        out["answer"] += " (Detailed retrieval hit an error; using summary facts instead.)"
        out["index_status"] = "ready"
        return out

    try:
        llm_out = _call_llm_for_rag_chat(retrieved, question, history)
    except Exception as exc:  # noqa: BLE001 — never hard-fail a chat turn
        print(f"[Chat] Both LLM providers unavailable, using fallback: {exc}")
        llm_out = _fallback_answer(context, question)
        llm_out["answer"] = (
            f"{llm_out['answer']} (Live AI answer generation is temporarily unavailable; "
            "using summary facts instead.)"
        )

    answer = llm_out.get("answer") or "I couldn't generate an answer for that question."
    source = llm_out.get("source", "fallback")
    answer, source = _apply_data_query(job, question, answer, source, llm_out, retrieved, history)
    answer, chart_dict, chart_generated = _apply_chart_request(job, answer, llm_out)

    return {
        "answer": answer,
        "source": source,
        "chart": chart_dict,
        "chart_generated": chart_generated,
        "index_status": "ready",
    }
