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
    _get_groq_client,
    _call_gemini_json_with_failover,
    _parse_schema_blueprint_response,
)
from api.utils.serialization import chart_url

if TYPE_CHECKING:
    from api.services.job_manager import Job

CHARTS_DIR = "outputs/charts"
os.makedirs(CHARTS_DIR, exist_ok=True)

COLORS = {
    "primary": "#2563EB", "secondary": "#16A34A", "accent": "#DC2626",
    "warning": "#D97706", "purple": "#7C3AED",
    "bars": ["#2563EB", "#16A34A", "#DC2626", "#D97706", "#7C3AED",
             "#0891B2", "#DB2777", "#65A30D", "#EA580C", "#4F46E5"],
}

MAX_HISTORY_TURNS = 6  # recent user/assistant turns replayed to the model for context
MAX_LLM_COLUMNS = 18
MAX_LLM_CORRELATIONS = 5
MAX_LLM_TRENDS = 4
MAX_LLM_FINDINGS = 4
MAX_LLM_TEXT_CHARS = 280
MAX_LLM_USER_CONTENT_CHARS = 12000
GEMINI_COOLDOWN_SECONDS = 60
ALLOWED_CHART_TYPES = {"bar", "line", "histogram", "box", "scatter"}
# "income" is intentionally excluded: a customer/personal income column is not
# company revenue (see agent_2.py's financial_role tagging), so treating it as
# a revenue synonym here would resurrect the same category error in chat answers.
REVENUE_QUERY_TERMS = ("revenue", "sales", "profit", "amount", "turnover")
RANKING_QUERY_TERMS = ("top", "best", "highest", "most", "max", "largest", "leader")
ACTION_QUERY_TERMS = ("what do i do", "what should i do", "recommend", "next step", "how do i improve", "action")

# Maps a topic to the phrases that imply the question needs that section of the
# dataset context. Only matched topics are sent to the LLM - unrelated sections
# (e.g. seasonality for a pure anomaly question) are left out of the prompt
# entirely, which is what actually keeps the request small turn over turn.
TOPIC_KEYWORDS = {
    "correlation": ("correlat", "relationship", "related", "linked", "connect"),
    "trend": ("trend", "growth", "increas", "decreas", "season", "over time", "month", "quarter", "year"),
    "ranking": ("top", "best", "highest", "most", "max", "largest", "leader", "worst", "bottom", "lowest", "least"),
    "anomaly": ("anomal", "outlier", "unusual", "weird", "odd", "suspicious"),
    "quality": ("quality", "trust", "confidence", "reliable", "valid", "accurate"),
    "distribution": ("distribut", "categor", "breakdown", "split", "segment"),
    "stats": ("average", "mean", "median", "std", "deviation", "statistic", "describe"),
}

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
        "significant_trends": {
            col: metrics for col, metrics in regression.items()
            if isinstance(metrics, dict) and metrics.get("significant")
        },
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


def _compact_context_for_llm(context: dict[str, Any]) -> dict[str, Any]:
    """Keep only the facts that help the model answer, not the entire analysis blob.

    This prevents provider-side input limit errors while preserving grounded
    signals for correlations, trends, rankings, anomalies, quality, and chart
    availability.
    """
    context = context or {}
    dataset = context.get("dataset", {}) or {}
    available_columns = context.get("available_columns", {}) or {}
    descriptive_stats = context.get("descriptive_stats", {}) or {}
    strong_correlations = context.get("strong_correlations", []) or []
    significant_trends = context.get("significant_trends", {}) or {}
    top_bottom_rankings = context.get("top_bottom_rankings", {}) or {}

    compact_columns = {
        col: meta
        for idx, (col, meta) in enumerate(available_columns.items())
        if idx < MAX_LLM_COLUMNS and isinstance(meta, dict)
    }

    compact_descriptive = {}
    for idx, (col, metrics) in enumerate(descriptive_stats.items()):
        if idx >= MAX_LLM_COLUMNS or not isinstance(metrics, dict):
            continue
        compact_descriptive[col] = {
            key: metrics.get(key)
            for key in ("count", "mean", "median", "std", "min", "max", "missing_pct", "unique")
            if key in metrics
        }

    compact_correlations = [
        {
            "col1": pair.get("col1"),
            "col2": pair.get("col2"),
            "pearson_r": pair.get("pearson_r"),
            "direction": pair.get("direction"),
            "strength": pair.get("strength"),
        }
        for pair in strong_correlations[:MAX_LLM_CORRELATIONS]
        if isinstance(pair, dict)
    ]

    compact_trends = {}
    for idx, (col, metrics) in enumerate(significant_trends.items()):
        if idx >= MAX_LLM_TRENDS or not isinstance(metrics, dict):
            continue
        compact_trends[col] = {
            key: metrics.get(key)
            for key in ("trend", "slope", "r_squared", "p_value", "n", "x_axis")
            if key in metrics
        }

    compact_rankings = {}
    for idx, (col, metrics) in enumerate(top_bottom_rankings.items()):
        if idx >= MAX_LLM_FINDINGS or not isinstance(metrics, dict):
            continue
        compact_rankings[col] = {
            "top": (metrics.get("top") or [])[:3],
            "bottom": (metrics.get("bottom") or [])[:3],
        }

    return {
        "dataset": dataset,
        "chart_plan": context.get("chart_plan", {}) or {},
        "available_columns": compact_columns,
        "descriptive_stats": compact_descriptive,
        "strong_correlations": compact_correlations,
        "growth_rates": context.get("growth_rates", {}) or {},
        "seasonality": context.get("seasonality", {}) or {},
        "top_bottom_rankings": compact_rankings,
        "anomaly_summary": context.get("anomaly_summary", {}) or {},
        "significant_trends": compact_trends,
        "category_distributions": context.get("category_distributions", {}) or {},
        "validation": context.get("validation", {}) or {},
        "reliability": context.get("reliability", {}) or {},
        "executive_summary": _truncate_text(context.get("executive_summary")),
        "key_findings": [
            _truncate_text(item)
            for item in (context.get("key_findings", []) or [])[:MAX_LLM_FINDINGS]
            if item
        ],
        "existing_charts": (context.get("existing_charts", []) or [])[:MAX_LLM_FINDINGS],
    }


def _detect_question_topics(question: str) -> set[str]:
    """Classify which dataset-context sections a question actually needs."""
    q = (question or "").lower()
    return {topic for topic, terms in TOPIC_KEYWORDS.items() if any(term in q for term in terms)}


def _build_topic_scoped_context(compact_context: dict[str, Any], topics: set[str]) -> dict[str, Any]:
    """Keep only the dataset-fact sections relevant to the detected topics.

    Base facts (dataset shape, columns, executive summary, existing charts)
    are always included since the model needs them to answer anything and to
    know what it can chart. Everything else is only attached when the
    question's topic calls for it, which is what actually shrinks the prompt
    on follow-up turns instead of resending the whole analysis every time.
    """
    scoped = {
        "dataset": compact_context.get("dataset", {}),
        "available_columns": compact_context.get("available_columns", {}),
        "executive_summary": compact_context.get("executive_summary"),
        "existing_charts": compact_context.get("existing_charts", []),
    }

    # An unrecognized/generic question ("tell me about this data") gets a
    # light default sample of every section rather than nothing at all - the
    # sections are already tightly capped by _compact_context_for_llm.
    include_all = not topics

    if include_all or "correlation" in topics:
        scoped["strong_correlations"] = compact_context.get("strong_correlations", [])
    if include_all or "trend" in topics:
        scoped["growth_rates"] = compact_context.get("growth_rates", {})
        scoped["seasonality"] = compact_context.get("seasonality", {})
        scoped["significant_trends"] = compact_context.get("significant_trends", {})
    if include_all or "ranking" in topics:
        scoped["top_bottom_rankings"] = compact_context.get("top_bottom_rankings", {})
    if include_all or "anomaly" in topics:
        scoped["anomaly_summary"] = compact_context.get("anomaly_summary", {})
    if include_all or "quality" in topics:
        scoped["validation"] = compact_context.get("validation", {})
        scoped["reliability"] = compact_context.get("reliability", {})
    if include_all or "distribution" in topics:
        scoped["category_distributions"] = compact_context.get("category_distributions", {})
    if include_all or "stats" in topics:
        scoped["descriptive_stats"] = compact_context.get("descriptive_stats", {})
    if include_all:
        scoped["key_findings"] = compact_context.get("key_findings", [])

    return scoped


def _build_llm_user_content(context: dict[str, Any], question: str, history: list[dict[str, str]]) -> str:
    import json

    compact_context = _compact_context_for_llm(context)
    topics = _detect_question_topics(question)
    scoped_context = _build_topic_scoped_context(compact_context, topics)
    compact_history = [
        {"role": turn.get("role"), "content": _truncate_text(turn.get("content"), 400)}
        for turn in history[-4:]
        if turn.get("role") in ("user", "assistant") and turn.get("content")
    ]

    user_content = (
        f"Dataset facts:\n{json.dumps(scoped_context, separators=(',', ':'), default=str)}\n\n"
        f"Conversation so far:\n{json.dumps(compact_history, separators=(',', ':'), default=str)}\n\n"
        f"User question: {question}"
    )

    if len(user_content) > MAX_LLM_USER_CONTENT_CHARS:
        minimal_context = {
            "dataset": scoped_context.get("dataset", {}),
            "available_columns": scoped_context.get("available_columns", {}),
            "executive_summary": scoped_context.get("executive_summary"),
            "existing_charts": scoped_context.get("existing_charts", []),
        }
        # Even scoped, keep at most one extra section under the hard cap -
        # whichever the topic router already decided was most relevant.
        for key in ("strong_correlations", "significant_trends", "top_bottom_rankings",
                    "anomaly_summary", "validation", "category_distributions", "descriptive_stats"):
            if key in scoped_context:
                minimal_context[key] = scoped_context[key]
                break
        user_content = (
            f"Dataset facts:\n{json.dumps(minimal_context, separators=(',', ':'), default=str)}\n\n"
            f"Conversation so far:\n{json.dumps(compact_history[-2:], separators=(',', ':'), default=str)}\n\n"
            f"User question: {question}"
        )

    return user_content


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


def _normalize_question(question: str) -> str:
    return question.lower().strip()


def _first_ranking(context: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    rankings = context.get("top_bottom_rankings") or {}
    if not isinstance(rankings, dict) or not rankings:
        return None, None
    col = next(iter(rankings))
    data = rankings.get(col) if isinstance(rankings.get(col), dict) else None
    return col, data


def _answer_ranking_question(context: dict[str, Any], question: str) -> dict[str, Any] | None:
    q = _normalize_question(question)
    if not any(term in q for term in RANKING_QUERY_TERMS) or not any(term in q for term in REVENUE_QUERY_TERMS):
        return None

    col, data = _first_ranking(context)
    if not data:
        return {
            "answer": "I couldn’t find ranking facts for this dataset, so I can’t identify the highest revenue segment yet.",
            "needs_new_chart": False,
            "chart_request": None,
            "source": "fallback",
        }

    top_rows = data.get("top") or []
    top_row = top_rows[0] if top_rows else None
    if not top_row:
        return {
            "answer": f"I have ranking data for {col}, but there isn’t a clear top performer in the stored facts.",
            "needs_new_chart": False,
            "chart_request": None,
            "source": "fallback",
        }

    top_value = top_row.get(col)
    share = top_row.get("revenue_share_pct")
    if share is not None:
        answer = (
            f"The highest-revenue segment I found is {top_value} in {col}, contributing {share}% of total revenue. "
            f"If your goal is to grow revenue, start by protecting and scaling that segment first."
        )
    else:
        answer = (
            f"The top segment I found is {top_value} in {col}. If your goal is to grow revenue, I’d start by "
            "protecting that leading segment and checking whether the next best segment can be expanded."
        )

    return {"answer": answer, "needs_new_chart": False, "chart_request": None, "source": "fallback"}


def _answer_anomaly_question(context: dict[str, Any], question: str) -> dict[str, Any] | None:
    q = _normalize_question(question)
    if not any(term in q for term in ("anomal", "outlier", "unusual", "weird", "odd", "suspicious")):
        return None

    anomaly = context.get("anomaly_summary") or {}
    flagged_rows = anomaly.get("unique_flagged_rows")
    flagged_pct = anomaly.get("unique_flagged_row_pct")
    flagged_cols = anomaly.get("flagged_columns")

    if flagged_rows:
        answer = (
            f"I found {flagged_rows} unusual rows, which is about {flagged_pct}% of the dataset. "
            "Those are worth checking for data-entry issues or one-off business events."
        )
        if flagged_cols is not None:
            answer += f" The anomaly scan also touched {flagged_cols} column(s)."
    else:
        answer = "I didn’t find a strong anomaly signal in the stored analysis facts."

    return {"answer": answer, "needs_new_chart": False, "chart_request": None, "source": "fallback"}


def _answer_action_question(context: dict[str, Any], question: str) -> dict[str, Any] | None:
    q = _normalize_question(question)
    if not any(term in q for term in ACTION_QUERY_TERMS):
        return None

    ranking_answer = _answer_ranking_question(context, question)
    if ranking_answer:
        return ranking_answer

    summary = context.get("executive_summary")
    if summary:
        return {
            "answer": f"The main takeaway is: {summary} If you want next steps, I can break that into revenue, risk, or anomaly actions.",
            "needs_new_chart": False,
            "chart_request": None,
            "source": "fallback",
        }

    return {
        "answer": "The stored facts aren’t enough to give a specific action yet. Try asking about revenue, anomalies, correlations, or trends.",
        "needs_new_chart": False,
        "chart_request": None,
        "source": "fallback",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2 — LLM CHAT (Groq -> Gemini fallback, same provider chain as Agent 6)
# ─────────────────────────────────────────────────────────────────────────────

CHAT_SYSTEM_PROMPT = """You are a data analyst assistant answering questions about one \
already-analyzed dataset. You will be given a JSON object of facts that were computed \
deterministically (schema, descriptive stats, correlations, growth rates, seasonality, \
rankings, anomalies, regression trends, quality/validation scores, and the charts already \
generated).

Rules:
- Use ONLY the numbers, column names, and facts present in the JSON. Never invent a number, \
column, or statistic that is not there.
- If the facts do not contain enough information to answer, say so honestly instead of guessing.
- Be concise, conversational, and business-readable.
- If an existing chart (see "existing_charts") already answers the question, reference it and \
do not request a new one.
- If the question needs a NEW chart that isn't already available, set "needs_new_chart" to true \
and fill "chart_request" using ONLY column names from "available_columns".

Return ONLY a JSON object with exactly these keys:
{
  "answer": "conversational answer to the user's question, grounded in the facts",
  "needs_new_chart": true or false,
  "chart_request": {
    "chart_type": "bar" | "line" | "histogram" | "box" | "scatter",
    "x_column": "column name from available_columns",
    "y_column": "column name from available_columns, or null for histogram/box",
    "group_by": "column name from available_columns, or null",
    "aggregation": "sum" | "mean" | "count" | "median",
    "title": "short chart title"
  } or null
}
"""


def _call_llm_for_chat(context: dict[str, Any], question: str, history: list[dict[str, str]]) -> dict[str, Any]:
    """Ask Groq for a grounded chat answer, falling back to Gemini on provider failure."""
    user_content = _build_llm_user_content(context, question, history)

    try:
        response = _get_groq_client().chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": CHAT_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            max_tokens=512,
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
            system_instruction=CHAT_SYSTEM_PROMPT,
            temperature=0.3,
            max_output_tokens=512,
        )
        parsed["source"] = "gemini"
        return parsed
    except Exception as gemini_error:
        if _is_quota_error(gemini_error):
            _disable_gemini_due_to_quota(str(gemini_error))
        raise


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
    else:
        summary = context.get("executive_summary")
        answer = summary or (
            f"This dataset has {dataset.get('rows')} rows and {dataset.get('columns')} columns. "
            "Ask me about correlations, trends, rankings, anomalies, or data quality for more detail."
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
# 5 — PUBLIC ENTRYPOINT
# ─────────────────────────────────────────────────────────────────────────────

def ask_question(job: "Job", question: str) -> dict[str, Any]:
    """Answer a user's question about ``job``'s analyzed dataset."""
    result = job.result or {}
    context = build_dataset_context(result)
    history = _condense_history(job.chat_history)

    deterministic_answer = (
        _answer_anomaly_question(context, question)
        or _answer_ranking_question(context, question)
        or _answer_action_question(context, question)
    )
    if deterministic_answer is not None:
        return deterministic_answer

    if _gemini_is_disabled():
        print("[Chat] Gemini previously disabled by quota; using deterministic fallback directly")
        return _fallback_answer(context, question)

    try:
        llm_out = _call_llm_for_chat(context, question, history)
    except Exception as exc:  # noqa: BLE001 — never hard-fail a chat turn
        print(f"[Chat] Both LLM providers unavailable, using fallback: {exc}")
        llm_out = _fallback_answer(context, question)

    answer = llm_out.get("answer") or "I couldn't generate an answer for that question."
    source = llm_out.get("source", "fallback")
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

    return {
        "answer": answer,
        "source": source,
        "chart": chart_dict,
        "chart_generated": chart_generated,
    }
