#!/usr/bin/env python
"""Render insight_report.html.jinja with mock data for a quick visual check,
without running the full agent pipeline. Registers the same Jinja filters
agent_6._render_html registers so the template's actual filter usage
(humnum, humpct, humcur, humratio, titleize, abbr_glossary) doesn't blow up."""

import re
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from datetime import datetime, timezone

from agents.report_style import (
    humanize_currency,
    humanize_number,
    humanize_pct,
    humanize_ratio,
    titleize,
)


def _glossary_abbr(text, glossary):
    """Mirrors agents.agent_6._glossary_abbr without importing that heavy module."""
    from markupsafe import Markup, escape
    if not isinstance(text, str) or not text or not glossary:
        return text
    result = escape(text)
    for term, explanation in glossary.items():
        pattern = re.compile(re.escape(str(term)), re.IGNORECASE)
        match = pattern.search(str(result))
        if not match:
            continue
        matched = str(escape(match.group(0)))
        tooltip = str(escape(explanation))
        abbr = Markup(f'<abbr class="glossary" title="{tooltip}">{matched}</abbr>')
        result = Markup(pattern.sub(lambda _m: str(abbr), str(result), count=1))
    return result


# Setup Jinja2
TEMPLATE_DIR = str(Path(__file__).resolve().parent / "templates")
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)
env.filters.update({
    "humnum": humanize_number,
    "humpct": humanize_pct,
    "humcur": lambda v, symbol="": humanize_currency(v, symbol),
    "humratio": humanize_ratio,
    "titleize": titleize,
    "abbr_glossary": _glossary_abbr,
})

# Mock data
mock_data = {
    "facts": {
        "data_quality": {"overall_quality_score": 88},
        "validation": {"passed": True, "overall_validation_score": 90, "cohen_kappa": 0.81},
        "reliability": {"overall_confidence": 0.86, "decision_readiness": "Ready for review"},
        "dataset_shape": [250, 9],
        "top_correlations": [
            {"col1": "Revenue", "col2": "Quantity", "pearson_r": 0.82, "strength": "Strong"},
            {"col1": "Profit", "col2": "Revenue", "pearson_r": 0.91, "strength": "Very Strong"},
        ],
        "significant_trends": [
            {"column": "Revenue", "trend": "Upward", "r_squared": 0.73, "p_value": 0.001},
        ],
    },
    "narrative": {
        "executive_summary": "Your dataset shows strong upward trends across key metrics with excellent data quality.",
        "key_findings": [
            "Revenue grows consistently month-over-month by 3-5%",
            "Top products account for 65% of total sales",
            "Customer acquisition cost is declining over time",
        ],
        "bottom_line": "Strong business growth with improving operational efficiency.",
        "plain_language_insights": [
            "Your sales are trending upward steadily throughout the period",
            "A small number of products drive most of your revenue",
            "You're getting better at acquiring customers cost-effectively",
        ],
        "recommendations": [
            "Focus marketing spend on the top 3 products to maximize ROI",
            "Investigate the seasonal dip in Q3 to find optimization opportunities",
        ],
        "risks_and_caveats": [
            "Data quality slightly affected by missing values in the discount column (5% of records)",
            "Trends assume consistent market conditions going forward",
        ],
        "glossary_terms": {"correlation": "How closely two things move together", "trend": "A consistent pattern of change over time"},
        "story": {"what_happened": "Sales grew 45% year-over-year", "why_it_matters": "Strong growth indicates market fit", "what_to_do_next": "Scale operations"},
    },
    "story": {"what_happened": "Sales grew 45% year-over-year", "why_it_matters": "Strong growth indicates market fit"},
    "glossary": {"correlation": "How closely two things move together"},
    "kpis": [
        {"label": "Total Revenue", "value": "$125K", "hint": "Q3 2026"},
        {"label": "Avg Order Value", "value": "$342", "hint": "Up 12% YoY"},
        {"label": "Customer Count", "value": "1,250", "hint": "Active"},
        {"label": "Growth Rate", "value": "+24%", "hint": "YoY"},
    ],
    "dataset_intro": [
        "250 sales records spanning 9 months",
        "Data includes transaction amounts, customer segments, and product categories",
        "No major data quality issues detected",
    ],
    "quality_verdict": {"label": "Excellent"},
    "chart_sections": [
        (
            "direction",
            {
                "heading": "Direction of Travel",
                "blurb": "Trends over time and repeating patterns",
                "charts": [
                    {
                        "id": "chart1",
                        "title": "Monthly Revenue Trend",
                        "subtitle": "Last 9 months",
                        "plain_summary": "Revenue shows a steady upward trend with minor seasonal fluctuations.",
                        "why_it_matters": "Consistent growth indicates healthy business momentum.",
                        "annotations": [
                            {"label": "Avg Growth", "value": "3.2%/month"},
                            {"label": "Peak Month", "value": "August"},
                        ],
                        "img_b64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                        "alt_text": "Revenue trend chart",
                    },
                ]
            }
        ),
    ],
    "has_interactive": False,
    "echarts_lib": "",
    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    "dataset_name": "sample_sales.csv",
}

# Render template
template = env.get_template("insight_report.html.jinja")
html = template.render(**mock_data)

# Save output
output_path = Path(__file__).resolve().parent / "outputs" / "reports" / "test_redesigned_report.html"
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(html, encoding="utf-8")

print("Template rendered successfully!")
print(f"Output saved to: {output_path}")
print(f"File size: {len(html):,} bytes")
