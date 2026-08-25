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
from api.utils.serialization import chart_url

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
MAX_LLM_USER_CONTENT_CHARS = 12000
GEMINI_COOLDOWN_SECONDS = 60
ALLOWED_CHART_TYPES = {"bar", "line", "histogram", "box", "scatter"}

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
# 2 — RAG CHAT (Groq -> Gemini fallback, same provider chain as Agent 6)
# ─────────────────────────────────────────────────────────────────────────────

RAG_CHAT_SYSTEM_PROMPT = """You are a data analyst assistant answering questions about one \
already-analyzed dataset using RETRIEVED evidence, not the whole dataset.

You will be given two kinds of retrieved documents:
- "facts": deterministic statistics/analysis computed over the FULL dataset (schema, descriptive \
stats, correlations, growth rates, rankings, anomalies, regression trends, quality/validation \
scores, narrative summary, and charts already generated). Trust these completely for anything \
aggregate or dataset-wide.
- "rows": a SAMPLE of actual data rows (only some of the dataset's rows are indexed, not all of \
them). Use these ONLY for concrete record-level lookups or examples. NEVER claim a row-level \
answer is complete or exhaustive beyond what is shown here - if the retrieved rows don't contain \
the specific record asked about, say honestly that it isn't among the indexed sample.

Rules:
- Use ONLY the numbers, column names, and facts present in the retrieved documents. Never invent \
a number, column, or record that isn't there.
- If the retrieved context doesn't contain enough information, say so honestly instead of guessing.
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
  } or null
}
"""


def _build_rag_user_content(retrieved: dict[str, Any], question: str, history: list[dict[str, str]]) -> str:
    import json

    facts = retrieved.get("facts") or []
    rows = retrieved.get("rows") or []
    compact_facts = [
        {"type": doc.get("doc_type"), "text": _truncate_text(doc.get("doc_text"), 320)}
        for doc in facts
        if doc.get("doc_text")
    ]
    compact_rows = [
        {"row_index": doc.get("row_index"), "text": _truncate_text(doc.get("doc_text"), 320)}
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


def _call_llm_for_rag_chat(retrieved: dict[str, Any], question: str, history: list[dict[str, str]]) -> dict[str, Any]:
    """Ask Groq for a grounded RAG chat answer, falling back to Gemini on provider failure."""
    user_content = _build_rag_user_content(retrieved, question, history)

    try:
        response = _get_groq_client().chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": RAG_CHAT_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            max_tokens=1024,
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
            system_instruction=RAG_CHAT_SYSTEM_PROMPT,
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
    answer, chart_dict, chart_generated = _apply_chart_request(job, answer, llm_out)

    return {
        "answer": answer,
        "source": source,
        "chart": chart_dict,
        "chart_generated": chart_generated,
        "index_status": "ready",
    }
