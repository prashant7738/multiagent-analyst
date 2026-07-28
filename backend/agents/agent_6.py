"""Agent 6: Insight Report Generator.

Final pipeline node. Synthesizes the outputs of Agents 1-5 (data quality,
statistics, charts, validation) into a single grounded document:

  1. Deterministic fact extraction (no LLM) - pulls concrete numbers out of
     `stats`, `data_quality`, `validation_report`, and `reliability` so the
     narrative step below has nothing to hallucinate from thin air.
  2. LLM narrative generation (Groq, falling back to Gemini, same provider
     chain as Agent 2) - asked to write an executive summary, key findings,
     risks/caveats, and recommendations using ONLY the extracted facts.
  3. A deterministic bullet-list fallback narrative if both LLM providers
     fail, so this agent never hard-fails the pipeline.
  4. Jinja2 HTML rendering + WeasyPrint PDF conversion. If PDF conversion
     itself fails (e.g. missing system libs), the HTML file is kept as the
     report so a document is still produced.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from agents.agent_1 import GraphState
from agents.agent_2 import (
    GEMINI_MODEL,
    GROQ_MODEL,
    _get_gemini_client,
    _get_groq_client,
    _parse_schema_blueprint_response,
)
from main import update_reliability

REPORTS_DIR = "outputs/reports"
TEMPLATE_DIR = str(Path(__file__).resolve().parent.parent / "templates")
TEMPLATE_NAME = "insight_report.html.jinja"

TOP_CORRELATIONS_LIMIT = 5
TOP_RANKING_LIMIT = 3
TOP_REGRESSION_LIMIT = 5


def _verbose_logging_enabled():
    val = os.getenv("PIPELINE_VERBOSE", "0").strip().lower()
    return val in {"1", "true", "yes", "on"}


# ─────────────────────────────────────────────────────────────────────────────
# 1 — DETERMINISTIC FACT EXTRACTION (no LLM)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_dataset_facts(state):
    raw_profile = state.get("raw_profile", {}) or {}
    shape = raw_profile.get("shape", {}) or {}
    cleaned_df = state.get("cleaned_df")
    return {
        "csv_path": state.get("csv_path", ""),
        "raw_rows": shape.get("rows"),
        "raw_cols": shape.get("cols"),
        "cleaned_rows": int(cleaned_df.shape[0]) if cleaned_df is not None else None,
        "cleaned_cols": int(cleaned_df.shape[1]) if cleaned_df is not None else None,
    }


def _extract_quality_facts(state):
    data_quality = state.get("data_quality", {}) or {}
    return {
        "overall_quality_score": data_quality.get("overall_quality_score"),
        "completeness_pct": data_quality.get("completeness_pct"),
        "duplicates_removed": data_quality.get("duplicates_removed"),
    }


def _extract_correlation_facts(stats):
    strong_pairs = (stats.get("correlation", {}) or {}).get("strong_pairs", []) or []
    ranked = sorted(strong_pairs, key=lambda p: abs(p.get("pearson_r", 0)), reverse=True)
    return ranked[:TOP_CORRELATIONS_LIMIT]


def _extract_growth_facts(stats):
    growth_rates = stats.get("growth_rates", {}) or {}
    facts = {}

    monthly = growth_rates.get("monthly", [])
    if monthly:
        latest = monthly[-1]
        facts["latest_month"] = {
            "label": latest.get("label"),
            "mom_growth_pct": latest.get("mom_growth_pct"),
        }

    quarterly = growth_rates.get("quarterly", [])
    if quarterly:
        latest_q = quarterly[-1]
        facts["latest_quarter"] = {
            "label": latest_q.get("label"),
            "qoq_growth_pct": latest_q.get("qoq_growth_pct"),
        }

    seasonality = stats.get("seasonality", {}) or {}
    if "monthly" in seasonality:
        facts["best_month"] = seasonality["monthly"].get("best_month")
        facts["worst_month"] = seasonality["monthly"].get("worst_month")
    if "quarterly" in seasonality:
        facts["best_quarter"] = seasonality["quarterly"].get("best_quarter")
        facts["worst_quarter"] = seasonality["quarterly"].get("worst_quarter")

    return facts


def _extract_ranking_facts(stats):
    top_bottom = stats.get("top_bottom", {}) or {}
    facts = {}
    for cat_col, data in top_bottom.items():
        facts[cat_col] = {
            "top": (data.get("top") or [])[:TOP_RANKING_LIMIT],
            "bottom": (data.get("bottom") or [])[:TOP_RANKING_LIMIT],
            "total_categories": data.get("total_categories"),
        }
    return facts


def _extract_anomaly_facts(stats):
    return stats.get("anomaly_summary", {}) or {}


def _extract_regression_facts(stats):
    regression = stats.get("regression", {}) or {}
    significant = [
        {"column": col, **metrics}
        for col, metrics in regression.items()
        if isinstance(metrics, dict) and metrics.get("significant")
    ]
    significant.sort(key=lambda r: r.get("r_squared", 0), reverse=True)
    return significant[:TOP_REGRESSION_LIMIT]


def _extract_validation_facts(state):
    validation_report = state.get("validation_report", {}) or {}
    semantic_agreement = validation_report.get("semantic_tagging_agreement", {}) or {}
    return {
        "overall_validation_score": validation_report.get("overall_validation_score"),
        "passed": validation_report.get("passed"),
        "flagged_issue_count": len(validation_report.get("flagged_issues", []) or []),
        "cohen_kappa": semantic_agreement.get("cohen_kappa"),
    }


def _extract_reliability_facts(state):
    reliability = state.get("reliability", {}) or {}
    return {
        "overall_confidence": reliability.get("overall_confidence"),
        "decision_readiness": reliability.get("decision_readiness"),
    }


def _extract_insight_facts(state):
    """Pure-Python fact extraction. No LLM calls, no hallucination risk."""
    stats = state.get("stats", {}) or {}
    return {
        "dataset": _extract_dataset_facts(state),
        "data_quality": _extract_quality_facts(state),
        "top_correlations": _extract_correlation_facts(stats),
        "growth": _extract_growth_facts(stats),
        "rankings": _extract_ranking_facts(stats),
        "anomalies": _extract_anomaly_facts(stats),
        "significant_trends": _extract_regression_facts(stats),
        "validation": _extract_validation_facts(state),
        "reliability": _extract_reliability_facts(state),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2 — LLM NARRATIVE GENERATION (Groq -> Gemini fallback)
# ─────────────────────────────────────────────────────────────────────────────

INSIGHT_SYSTEM_PROMPT = """You are a senior data analyst writing the narrative section of an \
automated data analysis report. You will be given a JSON object of facts that have already \
been computed deterministically from the dataset - descriptive stats, correlations, growth \
rates, rankings, anomalies, regression trends, and data-quality/validation scores.

Rules:
- Use ONLY the numbers and facts given in the JSON. Never invent a number, column name, or \
statistic that is not present in the input.
- If a section of the facts is empty or missing, do not mention it.
- Be concise and business-readable, not academic.

Return ONLY a JSON object with exactly these keys:
{
  "executive_summary": "2-4 sentence overview of the dataset and its most important signal",
  "key_findings": ["4-6 bullet strings, each citing a concrete number from the facts"],
  "risks_and_caveats": ["1-3 bullet strings about data quality/validation concerns, if any"],
  "recommendations": ["3-5 concrete, actionable bullet strings grounded in the findings"]
}
"""


def _call_llm_for_narrative(insight_facts: dict) -> dict:
    """Ask Groq for the narrative, falling back to Gemini on provider failure."""
    user_content = f"Write the report narrative for these facts:\n{json.dumps(insight_facts, indent=2, default=str)}"

    try:
        response = _get_groq_client().chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": INSIGHT_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            max_tokens=1024,
        )
        raw_text = response.choices[0].message.content.strip()
        narrative = _parse_schema_blueprint_response(raw_text)
        narrative["source"] = "groq"
        return narrative
    except Exception as groq_error:
        print(f"[Agent 6] Groq unavailable; trying Gemini: {groq_error}")

    try:
        response = _get_gemini_client().models.generate_content(
            model=GEMINI_MODEL,
            contents=user_content,
            config={
                "system_instruction": INSIGHT_SYSTEM_PROMPT,
                "temperature": 0.2,
                "max_output_tokens": 1024,
            },
        )
        raw_text = response.text.strip()
        narrative = _parse_schema_blueprint_response(raw_text)
        narrative["source"] = "gemini"
        return narrative
    except Exception as gemini_error:
        raise RuntimeError(f"Groq and Gemini calls failed: {gemini_error}") from gemini_error


def _fallback_narrative(insight_facts: dict) -> dict:
    """Deterministic, LLM-free narrative built directly from the facts. Guarantees the
    agent never fails outright when both LLM providers are unavailable."""
    dataset = insight_facts.get("dataset", {})
    quality = insight_facts.get("data_quality", {})
    validation = insight_facts.get("validation", {})

    executive_summary = (
        f"Dataset with {dataset.get('cleaned_rows')} rows and {dataset.get('cleaned_cols')} columns "
        f"after cleaning, with an overall data quality score of {quality.get('overall_quality_score')}."
    )

    key_findings = []
    for pair in insight_facts.get("top_correlations", []):
        key_findings.append(
            f"{pair['col1']} and {pair['col2']} show a {pair['strength']} {pair['direction']} "
            f"correlation (r={pair['pearson_r']})."
        )
    for trend in insight_facts.get("significant_trends", []):
        key_findings.append(
            f"{trend['column']} shows a statistically significant {trend['trend']} trend "
            f"(r²={trend['r_squared']})."
        )
    anomalies = insight_facts.get("anomalies", {})
    if anomalies.get("unique_flagged_rows"):
        key_findings.append(
            f"{anomalies.get('unique_flagged_rows')} rows "
            f"({anomalies.get('unique_flagged_row_pct')}%) were flagged as statistical anomalies."
        )
    if not key_findings:
        key_findings.append("No strong correlations, significant trends, or anomalies were detected.")

    risks_and_caveats = []
    if validation.get("flagged_issue_count"):
        risks_and_caveats.append(
            f"Agent 5 validation flagged {validation.get('flagged_issue_count')} issue(s); "
            f"review before relying on downstream conclusions."
        )
    if quality.get("overall_quality_score") is not None and quality["overall_quality_score"] < 80:
        risks_and_caveats.append(
            f"Data quality score ({quality['overall_quality_score']}) is below 80; "
            f"treat findings as directional rather than precise."
        )

    recommendations = [
        "Review the flagged anomalies for data-entry errors or genuine outlier events.",
        "Investigate the strongest correlation pairs for causal or business-process explanations.",
        "Re-run this pipeline as new data arrives to track whether trends persist.",
    ]

    return {
        "executive_summary": executive_summary,
        "key_findings": key_findings,
        "risks_and_caveats": risks_and_caveats,
        "recommendations": recommendations,
        "source": "fallback",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3 — RENDERING (Jinja2 -> HTML -> WeasyPrint PDF)
# ─────────────────────────────────────────────────────────────────────────────

def _render_html(insight_facts, narrative, chart_paths, state):
    # Chart paths are recorded relative to the process CWD (see agent_4.CHARTS_DIR).
    # Resolve to absolute paths so `file://` URIs work regardless of the report's
    # own output directory (used as WeasyPrint's base_url).
    resolved_chart_paths = [str(Path(p).resolve()) for p in (chart_paths or []) if Path(p).exists()]

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)
    template = env.get_template(TEMPLATE_NAME)
    return template.render(
        facts=insight_facts,
        narrative=narrative,
        chart_paths=resolved_chart_paths,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        dataset_name=Path(state.get("csv_path", "dataset")).name,
    )


def _write_report(html_string, reports_dir, errors):
    """Always write the HTML file; best-effort convert to PDF. Returns the report path
    (PDF if conversion succeeded, otherwise the HTML fallback) plus a pdf_written flag."""
    output_dir = Path(reports_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    html_path = output_dir / "insight_report.html"
    if html_path.exists():
        html_path.unlink()
    html_path.write_text(html_string, encoding="utf-8")

    pdf_path = output_dir / "insight_report.pdf"
    try:
        from weasyprint import HTML
        if pdf_path.exists():
            pdf_path.unlink()
        HTML(string=html_string, base_url=str(output_dir)).write_pdf(str(pdf_path))
        return str(pdf_path), True
    except Exception as pdf_error:
        errors.append(f"Agent6: PDF conversion failed, falling back to HTML report: {pdf_error}")
        return str(html_path), False


# ─────────────────────────────────────────────────────────────────────────────
# MAIN AGENT FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def agent6_insight_report_generator(state: GraphState) -> GraphState:
    errors = state.get("errors", [])
    cleaned_df = state.get("cleaned_df")
    stats = state.get("stats")
    validation_report = state.get("validation_report")

    if cleaned_df is None or not stats or not validation_report:
        errors.append("Agent6: Missing cleaned_df, stats, or validation_report. Upstream agent failed.")
        return {**state, "errors": errors}

    verbose = _verbose_logging_enabled()
    print("[Agent 6] Starting insight report generation")

    insight_facts = _extract_insight_facts(state)

    narrative_source = "llm"
    try:
        narrative = _call_llm_for_narrative(insight_facts)
    except Exception as llm_error:
        print(f"[Agent 6] LLM narrative generation failed, using deterministic fallback: {llm_error}")
        narrative = _fallback_narrative(insight_facts)
        narrative_source = "fallback"

    chart_paths = state.get("chart_paths", []) or []
    html_string = _render_html(insight_facts, narrative, chart_paths, state)
    report_path, pdf_written = _write_report(html_string, REPORTS_DIR, errors)

    if verbose:
        print(f"[Agent 6]   narrative_source={narrative.get('source', narrative_source)}")
        print(f"[Agent 6]   key_findings={len(narrative.get('key_findings', []))}")

    print(f"[Agent 6] Completed: report={report_path} pdf_written={pdf_written}")

    if narrative.get("source", narrative_source) == "fallback":
        confidence = 0.5 if not pdf_written else 0.7
    else:
        confidence = 0.85 if not pdf_written else 1.0

    state_with_reliability = update_reliability(
        state,
        "agent6",
        confidence,
        evidence=[
            f"narrative_source={narrative.get('source', narrative_source)}",
            f"pdf_written={pdf_written}",
            f"report_path={report_path}",
        ],
        decision_readiness="ready" if pdf_written else "needs_review",
    )

    return {
        **state_with_reliability,
        "insight_facts": insight_facts,
        "insight_narrative": narrative,
        "report_path": report_path,
        "errors": errors,
    }
