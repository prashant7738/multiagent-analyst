from typing import TypedDict, Any


class GraphState(TypedDict):
    # ── inputs ────────────────────────────────────────────────────────────────
    csv_path: str

    # ── Agent 1 outputs ───────────────────────────────────────────────────────
    raw_profile: dict          # structural profile: shape, dtypes, missing rates
    raw_shape: dict            # {rows, cols} captured on ingestion, before any transform - the
                               # single source of truth for "raw" counts for every downstream agent
    _df_cache: Any             # raw DataFrame passed between agents

    # ── Agent 2 outputs ───────────────────────────────────────────────────────
    schema_blueprint: dict     # per-column semantic tags and metadata

    # ── Agent 3 outputs ───────────────────────────────────────────────────────
    analysis_config: dict    # runtime run settings selected by the user
    preprocessing_config: dict # runtime thresholds and scoring weights for preprocessing
    preprocessing_profile: str # strict|balanced|lenient, or auto-selected profile
    dataset_domain: str        # inferred dataset domain for profile selection
    cleaned_df: Any            # fully preprocessed DataFrame for Agent 4
    cleaned_csv_path: str      # exported cleaned dataset path
    scaling_params: dict       # {col: {min, max}} for Agent 4 inverse-transform
    preprocessing_log: list    # full audit trail of every preprocessing action
    data_quality: dict         # 0-100 quality score for Agent 5 and Agent 6
    column_ledger: dict        # per-column transformation tracking and validation failures
    category_normalization: dict  # per-column fuzzy category merges: {col: [{raw, canonical, row_count, edit_distance}]}
    rule_manifest: dict        # version/hash and definitions used for quality findings

    # ── Agent 4 outputs ───────────────────────────────────────────────────────
    stats: dict
    chart_paths: list
    chart_specs: list         # data-driven ChartSpec dicts (see agents/chart_spec.py)

    # ── run identity ──────────────────────────────────────────────────────────
    run_id: str               # short unique id scoping this run's outputs (charts/reports)

    # ── Agent 5 outputs ───────────────────────────────────────────────────────
    validation_report: dict   # Tier 1 contract checks + Cohen's kappa tagging agreement

    # ── Agent 6 outputs ───────────────────────────────────────────────────────
    insight_facts: dict       # deterministic facts extracted from Agents 1-5 for grounding
    insight_narrative: dict   # LLM (or fallback) executive summary / findings / recommendations
    report_path: str          # path to the generated insight report (PDF, or HTML fallback)

    # ── shared ────────────────────────────────────────────────────────────────
    errors: list
    reliability: dict  # stage confidence, decision readiness, and evidence trail


def update_reliability(state: dict, stage_name: str, confidence: float, evidence: list | None = None,
                      decision_readiness: str | None = None) -> dict:
    """Merge per-stage confidence/decision metadata into the shared state."""
    reliability = dict(state.get("reliability") or {})
    stage_confidence = dict(reliability.get("stage_confidence") or {})

    try:
        stage_confidence[stage_name] = round(float(confidence), 3)
    except (TypeError, ValueError):
        stage_confidence[stage_name] = 0.0

    values = [value for value in stage_confidence.values() if isinstance(value, (int, float))]
    overall_confidence = round(sum(values) / len(values), 3) if values else 0.0

    evidence_items = list(reliability.get("evidence") or [])
    if evidence:
        if isinstance(evidence, list):
            evidence_items.extend(evidence)
        else:
            evidence_items.append(evidence)

    if decision_readiness is None:
        if overall_confidence >= 0.85:
            decision_readiness = "ready"
        elif overall_confidence >= 0.65:
            decision_readiness = "needs_review"
        else:
            decision_readiness = "blocked"

    reliability.update({
        "stage_confidence": stage_confidence,
        "overall_confidence": overall_confidence,
        "decision_readiness": decision_readiness,
        "evidence": evidence_items,
    })

    return {**state, "reliability": reliability}