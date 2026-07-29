"""Convert the pipeline's final ``GraphState`` into a frontend-friendly result.

Nothing here recomputes agent output — it only *projects* existing GraphState
fields into JSON-safe shapes and rewrites file paths into API URLs.
"""

from __future__ import annotations

from typing import Any

from api.utils.serialization import chart_url, dataframe_summary, json_safe


def _split_validation_checks(tier1_checks: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    """Bucket Agent 5 tier-1 checks into passed / failed / warnings by status."""
    passed_checks: list[str] = []
    failed_checks: list[str] = []
    warnings: list[str] = []
    for name, result in (tier1_checks or {}).items():
        status = str(result.get("status", "")).lower() if isinstance(result, dict) else ""
        if status == "pass":
            passed_checks.append(name)
        elif status == "fail":
            failed_checks.append(name)
        elif status == "warn":
            warnings.append(name)
    return passed_checks, failed_checks, warnings


def _report_format(report_path: str) -> str | None:
    if not report_path:
        return None
    lowered = report_path.lower()
    if lowered.endswith(".pdf"):
        return "pdf"
    if lowered.endswith(".html"):
        return "html"
    return report_path.rsplit(".", 1)[-1] if "." in report_path else None


def build_result(job_id: str, state: dict[str, Any], filename: str | None) -> dict[str, Any]:
    """Project a final GraphState into the API result contract."""
    state = state or {}

    raw_profile = state.get("raw_profile", {}) or {}
    schema_blueprint = state.get("schema_blueprint", {}) or {}
    data_quality = state.get("data_quality", {}) or {}
    stats = state.get("stats", {}) or {}
    validation_report = state.get("validation_report", {}) or {}
    reliability = state.get("reliability", {}) or {}
    insight_narrative = state.get("insight_narrative", {}) or {}
    report_path = state.get("report_path", "") or ""
    errors = state.get("errors", []) or []

    # ── charts → /plots URLs ──────────────────────────────────────────────
    charts = [chart_url(path) for path in (state.get("chart_paths", []) or [])]

    # ── validation projection (no recompute) ──────────────────────────────
    tier1_checks = validation_report.get("tier1_checks", {}) or {}
    passed_checks, failed_checks, warnings = _split_validation_checks(tier1_checks)
    validation = {
        "passed": validation_report.get("passed"),
        "overall_validation_score": validation_report.get("overall_validation_score"),
        "tier1_checks": tier1_checks,
        "passed_checks": passed_checks,
        "failed_checks": failed_checks,
        "warnings": warnings,
        "flagged_issues": validation_report.get("flagged_issues", []) or [],
        "semantic_tagging_agreement": validation_report.get("semantic_tagging_agreement", {}) or {},
    }

    # ── reliability projection (exposed verbatim) ─────────────────────────
    reliability_out = {
        "stage_confidence": reliability.get("stage_confidence", {}) or {},
        "overall_confidence": reliability.get("overall_confidence"),
        "decision_readiness": reliability.get("decision_readiness"),
        "evidence": reliability.get("evidence", []) or [],
    }

    # ── report projection ─────────────────────────────────────────────────
    report = {
        "report_path": report_path or None,
        "available": bool(report_path),
        "format": _report_format(report_path),
        "download_url": f"/api/report/{job_id}" if report_path else None,
        "generated_at": state.get("report_generated_at"),
        "narrative_source": insight_narrative.get("source"),
    }

    # ── high-level summary block for quick display ────────────────────────
    shape = raw_profile.get("shape", {}) or {}
    cleaned_df = state.get("cleaned_df")
    summary = {
        "filename": filename,
        "rows": shape.get("rows"),
        "columns": shape.get("cols"),
        "overall_missing_rate_pct": raw_profile.get("overall_missing_rate_pct"),
        "duplicate_rate_pct": raw_profile.get("duplicate_rate_pct"),
        "quality_score": data_quality.get("overall_quality_score"),
        "cleaned_shape": dataframe_summary(cleaned_df) if cleaned_df is not None else {},
        "column_count_tagged": len(schema_blueprint) if hasattr(schema_blueprint, "__len__") else None,
        "chart_count": len(charts),
        "validation_passed": validation_report.get("passed"),
        "overall_confidence": reliability_out["overall_confidence"],
        "decision_readiness": reliability_out["decision_readiness"],
        "executive_summary": insight_narrative.get("executive_summary"),
        "has_report": bool(report_path),
    }

    result = {
        "job_id": job_id,
        "status": "completed",
        "filename": filename,
        "summary": summary,
        "raw_profile": raw_profile,
        "schema_blueprint": dict(schema_blueprint),
        "preprocessing_log": state.get("preprocessing_log", []) or [],
        "data_quality": data_quality,
        "stats": stats,
        "charts": charts,
        "validation": validation,
        "reliability": reliability_out,
        "report": report,
        "insight_narrative": insight_narrative,
        "errors": errors,
    }

    return json_safe(result)
