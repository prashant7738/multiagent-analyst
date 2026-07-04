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
    cleaned_df: Any            # fully preprocessed DataFrame for Agent 4
    cleaned_csv_path: str      # exported cleaned dataset path
    scaling_params: dict       # {col: {min, max}} for Agent 4 inverse-transform
    preprocessing_log: list    # full audit trail of every preprocessing action
    data_quality: dict         # 0-100 quality score for Agent 5 and Agent 6

    # ── Agent 4 outputs (to be filled) ───────────────────────────────────────
    stats: dict
    chart_paths: list

    # ── Agent 5 outputs (to be filled) ───────────────────────────────────────
    validation_result: dict

    # ── Agent 6 outputs (to be filled) ───────────────────────────────────────
    final_report_path: str

    # ── shared ────────────────────────────────────────────────────────────────
    errors: list