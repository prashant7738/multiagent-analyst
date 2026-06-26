from typing import TypedDict, Any


class GraphState(TypedDict):
    csv_path: str
    raw_profile: dict
    schema_blueprint: dict
    cleaned_df: Any
    stats: dict
    chart_paths: list
    validation_result: dict
    final_report_path: str
    errors: list