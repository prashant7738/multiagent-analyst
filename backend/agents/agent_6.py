# agents/agent_6.py
"""
Agent 6 — Executive Report Generator.

Consumes validated `stats` (Agent 4) and `validation_result` (Agent 5) from the
shared GraphState and renders a self-contained, professional HTML report:

    outputs/final_insight_report.html

Design guarantees:
- Insights are produced by llama-3.3-70b-versatile (Groq) but are *grounded* —
  the model only ever receives, and is instructed to only ever discuss, metrics
  that actually exist in `stats`. A deterministic fallback covers LLM failures.
- Charts from `chart_paths` are base64-embedded so the report is portable
  (no external image files required). Missing files are skipped gracefully.
- A reliability disclaimer is injected automatically when the data quality
  score is low.
"""

import os
import json
import base64
import mimetypes

from jinja2 import Environment, BaseLoader, select_autoescape
from groq import Groq

from agents.agent_1 import GraphState
from main import update_reliability

client = None
gemini_client = None
GROQ_MODEL = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-2.5-flash"

OUTPUT_DIR = "outputs"
REPORT_NAME = "final_insight_report.html"

# Below this quality score we surface a reliability disclaimer in the report.
QUALITY_DISCLAIMER_THRESHOLD = 60.0


def _get_groq_client():
    """Create the Groq client only when a report actually needs it."""
    global client
    if client is not None:
        return client
    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY is not set")
    client = Groq()
    return client


def _get_gemini_client():
    """Create the Gemini client only when Groq cannot generate insights."""
    global gemini_client
    if gemini_client is not None:
        return gemini_client
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("Gemini_API_Key") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    from google import genai
    gemini_client = genai.Client(api_key=api_key)
    return gemini_client


# ─────────────────────────────────────────────────────────────────────────────
# IMAGE HANDLING — local path → base64 data URI
# ─────────────────────────────────────────────────────────────────────────────

def _encode_image(path: str) -> dict | None:
    """
    Read a local image and return a dict describing it, with the raw bytes
    encoded as a base64 data URI so it can be embedded directly in HTML.

    Returns None if the file is missing or cannot be read, so callers can
    silently skip broken chart references.
    """
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None

    mime = mimetypes.guess_type(path)[0] or "image/png"
    encoded = base64.b64encode(raw).decode("ascii")
    name = os.path.splitext(os.path.basename(path))[0]
    title = name.replace("_", " ").title()

    return {
        "title": title,
        "data_uri": f"data:{mime};base64,{encoded}",
    }


def _embed_charts(chart_paths: list) -> list:
    """Convert every readable chart path into an embeddable base64 image."""
    charts = []
    for path in chart_paths or []:
        img = _encode_image(path)
        if img is not None:
            charts.append(img)
    return charts


# ─────────────────────────────────────────────────────────────────────────────
# INSIGHT GENERATION (LLM) — grounded on present metrics only
# ─────────────────────────────────────────────────────────────────────────────

INSIGHT_SYSTEM_PROMPT = """You are a senior data analyst writing a business intelligence report.
You receive PRE-COMPUTED statistics (JSON) from an automated analytics pipeline and a list of
chart titles that appear alongside your write-up.

WRITE LIKE A SENIOR ANALYST, NOT A CALCULATOR:
- Do NOT restate raw statistics (mean, median, min, max, standard deviation, row counts). Those
  already appear in the report's tables — repeating them adds no value.
- Explain WHY each pattern matters for the business, not merely that it exists.
- Weave MULTIPLE signals together (correlation + distribution shape + category mix + time trend)
  before drawing a conclusion. Prefer a synthesized insight over an isolated metric.
- COMPARE categories against one another (dominance, concentration, imbalance) instead of listing
  them one by one.
- Surface the things that change decisions: revenue concentration, class imbalance, skewed
  distributions, seasonality, growth or decline, anomalies, and strong/weak relationships.
- Reference the relevant chart by name when it supports a point (e.g. "as the correlation heatmap
  shows" or "visible in the monthly seasonality chart").
- RANK findings by business impact — the most consequential insight comes first.

GROUNDING RULES (critical — do not violate):
- Use ONLY the columns, categories, and numbers present in the provided JSON.
- Never invent figures, columns, trends, or business context that the data does not support.
- If a claim is not backed by the data, leave it out. Do not speculate beyond the evidence.

Every finding must combine: (1) the observation, (2) the supporting evidence from the data,
(3) the business interpretation, and (4) a recommendation when one is genuinely warranted.

Return ONLY valid JSON in exactly this shape (no markdown, no backticks):
{
  "executive_summary": "one flowing paragraph, 3-5 sentences, covering the most decision-relevant takeaways",
  "key_findings": [
    {
      "title": "short analytical headline (max ~8 words)",
      "narrative": "a concise analytical paragraph: observation, evidence, and business interpretation woven together",
      "recommendation": "one actionable recommendation, or an empty string if none applies",
      "impact": "high|medium|low"
    }
  ]
}
Order key_findings from highest to lowest business impact."""


def _cv(m: dict):
    """Coefficient of variation (std / |mean|) — a scale-free spread signal."""
    mean = m.get("mean")
    std = m.get("std")
    if mean in (None, 0) or std is None:
        return None
    try:
        return round(abs(std) / abs(mean), 3)
    except Exception:
        return None


def _skew_descriptor(skew):
    """Human label for a skewness value."""
    if skew is None:
        return None
    a = abs(skew)
    if a >= 1.0:
        strength = "heavily"
    elif a >= 0.5:
        strength = "moderately"
    else:
        return "roughly symmetric"
    return f"{strength} {'right' if skew > 0 else 'left'}-skewed"


def _compact_stats_for_llm(stats: dict) -> dict:
    """
    Build a trimmed, analysis-ready view of `stats` for the model. Instead of raw
    descriptive numbers, it passes *derived signals* (distribution shape,
    concentration, imbalance, correlation, seasonality spread, trend, anomaly rate)
    so the model synthesizes rather than restates. Every value is computed directly
    from validated stats — the model can only cite what it receives.
    """
    payload: dict = {}

    # distribution shape (skew + spread), not raw central tendency
    descriptive = stats.get("descriptive") or {}
    shape = {}
    for col, m in descriptive.items():
        desc = _skew_descriptor(m.get("skewness"))
        if desc is None and _cv(m) is None:
            continue
        shape[col] = {"shape": desc, "skewness": m.get("skewness"), "cv": _cv(m)}
    if shape:
        payload["distribution_shape"] = shape

    strong_pairs = (stats.get("correlation") or {}).get("strong_pairs") or []
    if strong_pairs:
        payload["strong_correlations"] = strong_pairs

    # revenue concentration per categorical dimension
    top_bottom = stats.get("top_bottom") or {}
    concentration = {}
    for cat_col, data in top_bottom.items():
        top = (data or {}).get("top") or []
        if not top:
            continue
        top3_share = round(sum(float(t.get("revenue_share_pct", 0) or 0) for t in top[:3]), 2)
        leader = top[0]
        concentration[cat_col] = {
            "total_categories": (data or {}).get("total_categories"),
            "top3_revenue_share_pct": top3_share,
            "leader": {"name": leader.get(cat_col),
                       "revenue_share_pct": leader.get("revenue_share_pct")},
        }
    if concentration:
        payload["revenue_concentration"] = concentration

    # class imbalance from category distributions
    distributions = stats.get("distributions") or {}
    imbalance = {}
    for col, rows in distributions.items():
        if not rows:
            continue
        top_row = max(rows, key=lambda r: float(r.get("pct", 0) or 0))
        imbalance[col] = {
            "categories": len(rows),
            "largest_category": top_row.get(col),
            "largest_share_pct": top_row.get("pct"),
        }
    if imbalance:
        payload["class_imbalance"] = imbalance

    # seasonality spread (peak vs trough), not the full series
    seasonality = stats.get("seasonality") or {}
    season_view = {}
    monthly = seasonality.get("monthly") or {}
    if monthly.get("best_month") and monthly.get("worst_month"):
        best = monthly["best_month"]
        worst = monthly["worst_month"]
        wv = float(worst.get("avg_revenue", 0) or 0)
        bv = float(best.get("avg_revenue", 0) or 0)
        season_view["monthly"] = {
            "best_month": best, "worst_month": worst,
            "peak_to_trough_ratio": round(bv / wv, 2) if wv else None,
        }
    if monthly.get("quarterly") or seasonality.get("quarterly"):
        q = seasonality.get("quarterly") or {}
        if q.get("best_quarter"):
            season_view["quarterly"] = {
                "best_quarter": q.get("best_quarter"),
                "worst_quarter": q.get("worst_quarter"),
            }
    if season_view:
        payload["seasonality"] = season_view

    # significant time trends only
    regression = stats.get("regression") or {}
    trends = {col: {"trend": r.get("trend"), "r_squared": r.get("r_squared"),
                    "significant": r.get("significant")}
              for col, r in regression.items() if r.get("significant")}
    if trends:
        payload["significant_trends"] = trends

    # anomaly footprint
    anomalies = stats.get("anomalies") or {}
    if anomalies:
        payload["anomalies"] = {
            col: {"count": a.get("count"), "col_mean": a.get("col_mean")}
            for col, a in anomalies.items()
        }

    return payload


def _fallback_insights(stats: dict, chart_titles: list | None = None) -> dict:
    """
    Deterministic, data-grounded analytical insights used when the LLM is
    unavailable or returns invalid JSON. Each finding synthesizes signals
    (concentration, skew, correlation, seasonality, trend, anomalies) into an
    observation + interpretation + recommendation, and is ranked by impact.
    """
    chart_titles = chart_titles or []

    def _has_chart(keyword):
        return any(keyword.lower() in t.lower() for t in chart_titles)

    findings = []  # each: (score, dict)

    # 1 — revenue concentration across categories
    for cat_col, data in (stats.get("top_bottom") or {}).items():
        top = (data or {}).get("top") or []
        if not top:
            continue
        top3 = round(sum(float(t.get("revenue_share_pct", 0) or 0) for t in top[:3]), 1)
        total_cats = (data or {}).get("total_categories") or len(top)
        leader = top[0]
        chart_ref = (f" This concentration is visible in the top-{len(top)} {cat_col} chart."
                     if _has_chart(cat_col) or _has_chart("top") else "")
        if top3 >= 50 and total_cats > 3:
            findings.append((100 + top3, {
                "title": f"Revenue concentrated in few {cat_col} groups",
                "narrative": (
                    f"The top three {cat_col} groups account for roughly {top3}% of total "
                    f"revenue out of {total_cats} groups, led by \"{leader.get(cat_col)}\" "
                    f"at {leader.get('revenue_share_pct')}%. This is a highly concentrated "
                    f"portfolio, which means performance is disproportionately exposed to a "
                    f"handful of segments and to any disruption affecting them.{chart_ref}"),
                "recommendation": (
                    f"Protect and deepen the leading {cat_col} segments while testing "
                    f"initiatives to grow the long tail and reduce single-segment dependence."),
                "impact": "high",
            }))

    # 2 — strong correlations (synthesized, not just listed)
    strong_pairs = (stats.get("correlation") or {}).get("strong_pairs") or []
    if strong_pairs:
        top_pair = max(strong_pairs, key=lambda p: abs(float(p.get("pearson_r", 0) or 0)))
        chart_ref = " as the correlation heatmap illustrates" if _has_chart("correlation") else ""
        direction = top_pair.get("direction")
        implication = ("tend to rise and fall together" if direction == "positive"
                       else "move in opposite directions")
        findings.append((90 + abs(float(top_pair.get("pearson_r", 0) or 0)) * 10, {
            "title": f"{top_pair.get('col1')} strongly linked to {top_pair.get('col2')}",
            "narrative": (
                f"{top_pair.get('col1')} and {top_pair.get('col2')} show a {top_pair.get('strength')} "
                f"{direction} relationship (r={top_pair.get('pearson_r')}){chart_ref}, meaning the "
                f"two {implication}. Relationships this strong are candidates for driver analysis "
                f"and can make one metric a useful early indicator for the other."),
            "recommendation": (
                f"Use {top_pair.get('col1')} as a leading signal when planning around "
                f"{top_pair.get('col2')}, and validate whether the link is causal before acting."),
            "impact": "high" if top_pair.get("strength") == "strong" else "medium",
        }))

    # 3 — skewed distributions
    skewed = []
    for col, m in (stats.get("descriptive") or {}).items():
        sk = m.get("skewness")
        if sk is not None and abs(sk) >= 1.0:
            skewed.append((col, sk))
    if skewed:
        col, sk = max(skewed, key=lambda x: abs(x[1]))
        desc = _skew_descriptor(sk)
        chart_ref = (" The revenue histogram makes this long tail apparent."
                     if _has_chart("histogram") else "")
        findings.append((70 + abs(sk), {
            "title": f"{col} distribution is {desc}",
            "narrative": (
                f"{col} is {desc} (skew {sk}), so a small number of records sit far above the "
                f"typical value and pull the average upward.{chart_ref} In practice the mean "
                f"overstates the common case, and the median is the more reliable figure for "
                f"planning and target-setting."),
            "recommendation": (
                f"Plan against the median for {col} and treat the high-value tail as a distinct "
                f"segment rather than blending it into headline averages."),
            "impact": "medium",
        }))

    # 4 — seasonality
    monthly = (stats.get("seasonality") or {}).get("monthly") or {}
    if monthly.get("best_month") and monthly.get("worst_month"):
        best, worst = monthly["best_month"], monthly["worst_month"]
        bv = float(best.get("avg_revenue", 0) or 0)
        wv = float(worst.get("avg_revenue", 0) or 0)
        ratio = round(bv / wv, 1) if wv else None
        spread = f" — about {ratio}x the level of {worst.get('month')}" if ratio else ""
        chart_ref = (" The monthly seasonality chart traces this cycle."
                     if _has_chart("seasonality") else "")
        findings.append((60 + (ratio or 0), {
            "title": "Demand shows clear seasonal swings",
            "narrative": (
                f"Average revenue peaks in {best.get('month')}{spread} and bottoms out in "
                f"{worst.get('month')}.{chart_ref} A gap this size points to recurring, "
                f"demand-driven purchasing behavior rather than random month-to-month noise, "
                f"which makes the pattern plannable."),
            "recommendation": (
                f"Align inventory, staffing, and campaigns to the {best.get('month')} peak and "
                f"use the {worst.get('month')} trough for maintenance and off-season promotions."),
            "impact": "medium",
        }))

    # 5 — significant time trend
    for col, r in (stats.get("regression") or {}).items():
        if not r.get("significant"):
            continue
        trend = r.get("trend")
        chart_ref = (" seen in the revenue trend regression chart"
                     if _has_chart("trend") else "")
        findings.append((55 + float(r.get("r_squared", 0) or 0) * 10, {
            "title": f"{col} on a significant {trend} trajectory",
            "narrative": (
                f"{col} shows a statistically significant {trend} trend over time "
                f"(R²={r.get('r_squared')}, p={r.get('p_value')}){chart_ref}. Because the "
                f"movement is directional rather than incidental, it is a reliable input for "
                f"forward-looking forecasts."),
            "recommendation": (
                f"Factor the {trend} trend in {col} into forward forecasts and revisit targets "
                f"that assume a flat baseline."),
            "impact": "medium",
        }))
        break  # one representative trend is enough

    # 6 — anomalies
    anomalies = stats.get("anomalies") or {}
    if anomalies:
        col, a = max(anomalies.items(), key=lambda kv: kv[1].get("count", 0))
        findings.append((40 + a.get("count", 0), {
            "title": f"Outliers detected in {col}",
            "narrative": (
                f"{a.get('count')} values in {col} fall well outside the normal range around a "
                f"mean of {a.get('col_mean')}. Outliers of this kind can distort averages and "
                f"models, and often flag either genuine exceptional events or data-entry issues "
                f"worth investigating."),
            "recommendation": (
                f"Review the flagged {col} records to confirm whether they are legitimate extreme "
                f"cases or errors before they influence reporting."),
            "impact": "low",
        }))

    # 7 — class imbalance in a categorical field
    for col, rows in (stats.get("distributions") or {}).items():
        if not rows or len(rows) < 2:
            continue
        top_row = max(rows, key=lambda r: float(r.get("pct", 0) or 0))
        share = float(top_row.get("pct", 0) or 0)
        if share >= 60:
            findings.append((45 + share, {
                "title": f"{col} is dominated by one category",
                "narrative": (
                    f"\"{top_row.get(col)}\" alone represents {share}% of records in {col}, so the "
                    f"field is heavily imbalanced. Aggregate metrics for {col} will largely reflect "
                    f"this single group and can mask the behavior of smaller categories."),
                "recommendation": (
                    f"Segment {col} analysis so minority categories are assessed on their own terms "
                    f"rather than being averaged away by the dominant group."),
                "impact": "low",
            }))
            break

    findings.sort(key=lambda x: x[0], reverse=True)
    key_findings = [f for _, f in findings]

    # keep the most impactful tiers first, preserving score order within a tier
    _impact_rank = {"high": 0, "medium": 1, "low": 2}
    key_findings.sort(key=lambda f: _impact_rank.get(f.get("impact"), 1))

    # executive summary synthesized from the top findings
    if key_findings:
        headline = key_findings[0]["title"].lower()
        themes = [f["title"].lower() for f in key_findings[:3]]
        executive_summary = (
            "This analysis moves beyond descriptive figures to isolate the patterns most likely to "
            f"affect decisions. The most consequential is that {headline}"
            + (f", alongside signals around {', '.join(themes[1:])}" if len(themes) > 1 else "")
            + ". The findings below are ordered by business impact, each pairing the evidence in the "
            "data with an interpretation and, where warranted, a recommended action."
        )
    else:
        executive_summary = (
            "The validated dataset did not surface strong concentration, correlation, seasonality, "
            "or anomaly patterns; the descriptive tables and charts below provide the available "
            "reference detail."
        )

    return {"executive_summary": executive_summary, "key_findings": key_findings}


def _normalize_insights(insights: dict, stats: dict, chart_titles: list) -> dict:
    """Ensure the LLM payload has the expected shape; backfill from fallback."""
    fallback = _fallback_insights(stats, chart_titles)
    summary = insights.get("executive_summary") or fallback["executive_summary"]

    raw_findings = insights.get("key_findings")
    findings = []
    if isinstance(raw_findings, list):
        for item in raw_findings:
            if not isinstance(item, dict):
                continue
            narrative = (item.get("narrative") or "").strip()
            title = (item.get("title") or "").strip()
            if not narrative or not title:
                continue
            impact = str(item.get("impact", "medium")).lower()
            if impact not in ("high", "medium", "low"):
                impact = "medium"
            findings.append({
                "title": title,
                "narrative": narrative,
                "recommendation": (item.get("recommendation") or "").strip(),
                "impact": impact,
            })

    if not findings:
        findings = fallback["key_findings"]

    return {"executive_summary": summary, "key_findings": findings}


def _generate_insights(stats: dict, errors: list, chart_titles: list | None = None) -> dict:
    """
    Ask Groq to synthesize analytical findings from the pre-computed signals.
    Falls back to deterministic analytical insights on any failure so the report
    always renders with meaningful commentary.
    """
    chart_titles = chart_titles or []
    compact = _compact_stats_for_llm(stats)
    if not compact:
        return _fallback_insights(stats, chart_titles)

    user_payload = {
        "signals": compact,
        "available_charts": chart_titles,
    }

    try:
        user_content = (
            "Produce the analytical report JSON from these derived signals. "
            "Synthesize across signals, rank by impact, reference charts by name, and "
            "do not restate raw statistics:\n"
            + json.dumps(user_payload, indent=2, default=str)
        )
        try:
            response = _get_groq_client().chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": INSIGHT_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.3,
                max_tokens=2000,
            )
            raw_text = response.choices[0].message.content.strip()
        except Exception as groq_error:
            print(f"[Agent 6] Groq unavailable; trying Gemini: {groq_error}")
            response = _get_gemini_client().models.generate_content(
                model=GEMINI_MODEL,
                contents=user_content,
                config={
                    "system_instruction": INSIGHT_SYSTEM_PROMPT,
                    "temperature": 0.3,
                    "max_output_tokens": 2000,
                },
            )
            raw_text = response.text.strip()

        # Strip markdown fences if the model adds them anyway.
        if "```" in raw_text:
            for part in raw_text.split("```"):
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                try:
                    insights = json.loads(part)
                    break
                except Exception:
                    continue
            else:
                raise json.JSONDecodeError("No valid JSON block found", raw_text, 0)
        else:
            insights = json.loads(raw_text)

        return _normalize_insights(insights, stats, chart_titles)

    except json.JSONDecodeError as e:
        errors.append(f"Agent6: LLM returned invalid JSON — {e}")
        return _fallback_insights(stats, chart_titles)
    except Exception as e:
        errors.append(f"Agent6: Groq call failed — {e}")
        return _fallback_insights(stats, chart_titles)


# ─────────────────────────────────────────────────────────────────────────────
# HTML TEMPLATE (Jinja2)
# ─────────────────────────────────────────────────────────────────────────────

REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Executive Insight Report</title>
<style>
  :root {
    --bg: #f1f5f9;
    --card: #ffffff;
    --ink: #1e293b;
    --muted: #64748b;
    --border: #e2e8f0;
    --primary: #2563eb;
    --good: #16a34a;
    --warn: #d97706;
    --bad: #dc2626;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
  }
  .wrap { max-width: 960px; margin: 0 auto; padding: 40px 24px 80px; }
  header.hero {
    background: linear-gradient(135deg, #1e3a8a, #2563eb);
    color: #fff;
    border-radius: 16px;
    padding: 40px 36px;
    margin-bottom: 28px;
    box-shadow: 0 10px 30px rgba(37,99,235,.25);
  }
  header.hero h1 { margin: 0 0 8px; font-size: 30px; letter-spacing: -.5px; }
  header.hero p { margin: 0; opacity: .9; font-size: 15px; }
  .card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 28px 30px;
    margin-bottom: 24px;
    box-shadow: 0 1px 3px rgba(15,23,42,.06);
  }
  .card h2 {
    margin: 0 0 16px;
    font-size: 19px;
    color: var(--ink);
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .card h2::before {
    content: "";
    width: 6px; height: 22px;
    background: var(--primary);
    border-radius: 3px;
  }
  ul.clean { margin: 0; padding-left: 20px; }
  ul.clean li { margin: 6px 0; }
  .summary { font-size: 16px; color: var(--ink); }
  .disclaimer {
    background: #fef3c7;
    border: 1px solid #fcd34d;
    color: #92400e;
    border-radius: 12px;
    padding: 16px 20px;
    margin-bottom: 24px;
    font-size: 14px;
  }
  .disclaimer strong { color: #78350f; }
  .badges { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 6px; }
  .badge {
    background: #f8fafc;
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 6px 14px;
    font-size: 13px;
    color: var(--muted);
  }
  .badge b { color: var(--ink); }
  .badge.good b { color: var(--good); }
  .badge.warn b { color: var(--warn); }
  .badge.bad  b { color: var(--bad); }
  table.metrics {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
  }
  table.metrics th, table.metrics td {
    text-align: left;
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
  }
  table.metrics th { color: var(--muted); font-weight: 600; background: #f8fafc; }
  table.metrics tr:last-child td { border-bottom: none; }
  .charts { display: grid; grid-template-columns: 1fr; gap: 22px; }
  figure.chart {
    margin: 0;
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
    background: #fff;
  }
  figure.chart img { display: block; width: 100%; height: auto; }
  figure.chart figcaption {
    padding: 10px 14px;
    font-size: 13px;
    color: var(--muted);
    border-top: 1px solid var(--border);
    background: #f8fafc;
  }
  footer.meta {
    text-align: center;
    color: var(--muted);
    font-size: 13px;
    margin-top: 40px;
  }
  .finding {
    border: 1px solid var(--border);
    border-left: 4px solid var(--primary);
    border-radius: 12px;
    padding: 18px 20px;
    margin-bottom: 16px;
    background: #fbfdff;
  }
  .finding:last-child { margin-bottom: 0; }
  .finding-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 8px;
  }
  .finding h3 { margin: 0; font-size: 16px; color: var(--ink); }
  .finding p { margin: 0; color: var(--ink); }
  .finding.impact-high  { border-left-color: var(--bad); }
  .finding.impact-medium{ border-left-color: var(--warn); }
  .finding.impact-low   { border-left-color: var(--good); }
  .impact-tag {
    flex: none;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: .04em;
    text-transform: uppercase;
    padding: 3px 10px;
    border-radius: 999px;
    color: #fff;
  }
  .impact-high  .impact-tag { background: var(--bad); }
  .impact-medium .impact-tag { background: var(--warn); }
  .impact-low   .impact-tag { background: var(--good); }
  .rec {
    margin-top: 10px;
    padding: 10px 14px;
    background: #eff6ff;
    border-radius: 8px;
    font-size: 14px;
    color: #1e3a8a;
  }
  .rec b { color: #1e3a8a; }
  .empty { color: var(--muted); font-style: italic; }
</style>
</head>
<body>
<div class="wrap">

  <header class="hero">
    <h1>Executive Insight Report</h1>
    <p>Automated analysis generated by the MultiAgent DataAnalyst pipeline.</p>
    <div class="badges">
      <span class="badge {{ quality_class }}">Data Quality: <b>{{ quality_score }}/100</b></span>
      <span class="badge {{ validation_class }}">Validation: <b>{{ validation_label }}</b></span>
      {% if confidence_score is not none %}
      <span class="badge">Confidence: <b>{{ confidence_score }}</b></span>
      {% endif %}
    </div>
  </header>

  {% if show_disclaimer %}
  <div class="disclaimer">
    <strong>Reliability notice:</strong> the underlying data quality score is
    {{ quality_score }}/100, which is below the recommended threshold of
    {{ quality_threshold }}. Insights below should be treated as directional
    and verified against source systems before acting on them.
  </div>
  {% endif %}

  <section class="card">
    <h2>Executive Summary</h2>
    <p class="summary">{{ insights.executive_summary }}</p>
  </section>

  <section class="card">
    <h2>Key Findings</h2>
    {% if insights.key_findings %}
      {% for f in insights.key_findings %}
      <div class="finding impact-{{ f.impact }}">
        <div class="finding-head">
          <h3>{{ f.title }}</h3>
          <span class="impact-tag">{{ f.impact }} impact</span>
        </div>
        <p>{{ f.narrative }}</p>
        {% if f.recommendation %}
        <div class="rec"><b>Recommendation:</b> {{ f.recommendation }}</div>
        {% endif %}
      </div>
      {% endfor %}
    {% else %}
      <p class="empty">No decision-relevant patterns were detected in the validated data.</p>
    {% endif %}
  </section>

  {% if descriptive %}
  <section class="card">
    <h2>Descriptive Statistics</h2>
    <table class="metrics">
      <thead>
        <tr><th>Metric</th><th>Mean</th><th>Median</th><th>Std</th><th>Min</th><th>Max</th></tr>
      </thead>
      <tbody>
        {% for col, m in descriptive.items() %}
        <tr>
          <td><b>{{ col }}</b></td>
          <td>{{ m.mean }}</td><td>{{ m.median }}</td><td>{{ m.std }}</td>
          <td>{{ m.min }}</td><td>{{ m.max }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </section>
  {% endif %}

  {% if charts %}
  <section class="card">
    <h2>Visualizations</h2>
    <div class="charts">
      {% for chart in charts %}
      <figure class="chart">
        <img src="{{ chart.data_uri }}" alt="{{ chart.title }}">
        <figcaption>{{ chart.title }}</figcaption>
      </figure>
      {% endfor %}
    </div>
  </section>
  {% endif %}

  <footer class="meta">
    Generated automatically &middot; {{ chart_count }} chart(s) embedded &middot;
    Report is fully self-contained.
  </footer>

</div>
</body>
</html>
"""


def _render_html(context: dict) -> str:
    """Render the report template with autoescaping enabled for safety."""
    env = Environment(
        loader=BaseLoader(),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.from_string(REPORT_TEMPLATE)
    return template.render(**context)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN AGENT FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def agent6_report_generator(state: GraphState) -> GraphState:
    """
    Generate the final self-contained HTML report from validated pipeline state.

    Reads:  stats, chart_paths, data_quality, validation_result
    Writes: outputs/final_insight_report.html
    Sets:   final_report_path
    """
    errors = state.get("errors", [])
    stats = state.get("stats") or {}
    chart_paths = state.get("chart_paths") or []
    data_quality = state.get("data_quality") or {}
    validation_result = state.get("validation_result") or {}

    if not stats:
        errors.append("Agent6: No stats in state. Agent 4 produced no analysis.")
        return {**state, "errors": errors}

    print("[Agent 6] Generating executive report...")

    # 1 — embed charts as base64 (missing files skipped)
    charts = _embed_charts(chart_paths)
    print(f"[Agent 6] Embedded {len(charts)}/{len(chart_paths)} charts")

    # 2 — narrate the numbers (grounded LLM, deterministic fallback);
    #     pass chart titles so findings can reference the visuals by name
    chart_titles = [c["title"] for c in charts]
    insights = _generate_insights(stats, errors, chart_titles)

    # 3 — quality + validation badges / disclaimer
    quality_score = data_quality.get("overall_quality_score", 0)
    show_disclaimer = float(quality_score or 0) < QUALITY_DISCLAIMER_THRESHOLD
    if quality_score >= 80:
        quality_class = "good"
    elif quality_score >= QUALITY_DISCLAIMER_THRESHOLD:
        quality_class = "warn"
    else:
        quality_class = "bad"

    passed = validation_result.get("passed", False)

    context = {
        "insights": insights,
        "charts": charts,
        "chart_count": len(charts),
        "descriptive": stats.get("descriptive") or {},
        "quality_score": quality_score,
        "quality_threshold": QUALITY_DISCLAIMER_THRESHOLD,
        "quality_class": quality_class,
        "show_disclaimer": show_disclaimer,
        "validation_label": "Passed" if passed else "Review Required",
        "validation_class": "good" if passed else "warn",
        "confidence_score": validation_result.get("confidence_score"),
    }

    # 4 — render + write
    html = _render_html(context)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    report_path = os.path.join(OUTPUT_DIR, REPORT_NAME)
    try:
        with open(report_path, "w", encoding="utf-8") as fh:
            fh.write(html)
    except OSError as e:
        errors.append(f"Agent6: Failed to write report — {e}")
        return {**state, "errors": errors}

    print(f"[Agent 6] Report written to {report_path}")

    state_with_reliability = update_reliability(
        state,
        "agent6",
        1.0 if report_path else 0.0,
        evidence=[f"report_path={report_path}", f"charts_embedded={len(charts)}"],
        decision_readiness="ready" if report_path else "blocked",
    )

    return {
        **state_with_reliability,
        "final_report_path": report_path,
        "errors": errors,
    }
