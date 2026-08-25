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


# Agent 3 keeps audit-trail/derived columns alongside the originals (e.g.
# "Income_raw"/"Income_scaled" next to the scaled "Income", or
# "*_range_failed" validation flags) instead of overwriting in place, so the
# cleaned dataset's column count is not directly comparable to the raw file's.
# These suffixes let the API surface an "analysis-facing" column count too,
# so a much larger cleaned column count isn't mistaken for a bug.
_INTERNAL_COLUMN_SUFFIXES = (
    "_raw", "_scaled", "_was_clipped", "_parse_failed", "_range_failed",
)


def _count_internal_columns(columns: list[str]) -> int:
    return sum(1 for c in columns if c.endswith(_INTERNAL_COLUMN_SUFFIXES))


def build_result(job_id: str, state: dict[str, Any], filename: str | None) -> dict[str, Any]:
    """Project a final GraphState into the API result contract."""
    state = state or {}

    analysis_config = state.get("analysis_config", {}) or {}
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
    # Prefer raw_shape (captured once by Agent 1 on ingestion, before any
    # transform) over re-deriving from raw_profile - same numbers, single
    # source of truth so "raw" row/column counts never drift downstream.
    shape = state.get("raw_shape") or raw_profile.get("shape", {}) or {}
    cleaned_df = state.get("cleaned_df")
    cleaned_shape = dataframe_summary(cleaned_df) if cleaned_df is not None else {}
    internal_col_count = _count_internal_columns(cleaned_shape.get("columns", []))
    if cleaned_shape:
        cleaned_shape["internal_audit_columns"] = internal_col_count
        cleaned_shape["analysis_columns"] = cleaned_shape["cols"] - internal_col_count
    schema_metadata = schema_blueprint.get("__metadata__", {}) if isinstance(schema_blueprint, dict) else {}
    summary = {
        "filename": filename,
        "preprocessing_profile": state.get("preprocessing_profile") or analysis_config.get("preprocessing_profile"),
        "analysis_config": analysis_config,
        "rows": shape.get("rows"),
        "columns": shape.get("cols"),
        "overall_missing_rate_pct": raw_profile.get("overall_missing_rate_pct"),
        "duplicate_rate_pct": raw_profile.get("duplicate_rate_pct"),
        "quality_score": data_quality.get("overall_quality_score"),
        "cleaned_shape": cleaned_shape,
        "column_count_tagged": len(schema_blueprint) if hasattr(schema_blueprint, "__len__") else None,
        # "llm" (Groq/Gemini classified each column) or "fallback" (both providers failed
        # this run, so metadata-only heuristics were used instead) — see agent_2.py.
        "semantic_tagging_source": schema_metadata.get("tagging_source"),
        "semantic_tagging_error": schema_metadata.get("tagging_error"),
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
        "analysis_config": analysis_config,
        "errors": errors,
    }

    return json_safe(result)
