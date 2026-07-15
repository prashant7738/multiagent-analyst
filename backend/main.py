from typing import TypedDict, Any


class GraphState(TypedDict):
    # ── inputs ────────────────────────────────────────────────────────────────
    csv_path: str

    # ── Agent 1 outputs ───────────────────────────────────────────────────────
    raw_profile: dict          # structural profile: shape, dtypes, missing rates
    _df_cache: Any             # raw DataFrame passed between agents

    # ── Agent 2 outputs ───────────────────────────────────────────────────────
    schema_blueprint: dict     # per-column semantic tags and metadata

    # ── Agent 3 outputs ───────────────────────────────────────────────────────
    preprocessing_config: dict # runtime thresholds and scoring weights for preprocessing
    preprocessing_profile: str # strict|balanced|lenient, or auto-selected profile
    dataset_domain: str        # inferred dataset domain for profile selection
    cleaned_df: Any            # fully preprocessed DataFrame for Agent 4
    cleaned_csv_path: str      # exported cleaned dataset path
    scaling_params: dict       # {col: {min, max}} for Agent 4 inverse-transform
    preprocessing_log: list    # full audit trail of every preprocessing action
    data_quality: dict         # 0-100 quality score for Agent 5 and Agent 6
    column_ledger: dict        # per-column transformation tracking and validation failures

    # ── Agent 4 outputs ───────────────────────────────────────────────────────
    stats: dict
    chart_paths: list

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