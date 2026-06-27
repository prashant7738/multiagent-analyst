from typing import TypedDict, Any


class GraphState(TypedDict):
    # ── inputs ────────────────────────────────────────────────────────────────
    csv_path: str

    # ── Agent 1 outputs ───────────────────────────────────────────────────────
    raw_profile: dict          
    _df_cache: Any            
    # ── Agent 2 outputs ───────────────────────────────────────────────────────
    schema_blueprint: dict     # per-column semantic metadata

    # ── Agent 3 outputs ───────────────────────────────────────────────────────
    cleaned_df: Any            # preprocessed DataFrame ready for analysis
    scaling_params: dict       # {col: {min: float, max: float}} for inverse-transform
    preprocessing_log: list    # audit trail of every preprocessing action

    # ── Agent 4 outputs (to be filled later) ─────────────────────────────────
    stats: dict
    chart_paths: list

    # ── Agent 5 outputs (to be filled later) ─────────────────────────────────
    validation_result: dict

    # ── Agent 6 outputs (to be filled later) ─────────────────────────────────
    final_report_path: str

    # ── shared ────────────────────────────────────────────────────────────────
    errors: list