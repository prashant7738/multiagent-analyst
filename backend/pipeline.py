from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph, END
from agents.agent_1 import GraphState, agent1_structural_profiler
from agents.agent_2 import agent2_semantic_tagger
from agents.agent_3 import agent3_preprocessor
from agents.agent_4 import agent4_analysis


def should_continue_after_agent1(state: GraphState) -> str:
    if state.get("errors") and any("Agent1" in e for e in state["errors"]):
        return "end"
    if not state.get("raw_profile"):
        return "end"
    return "agent2"


def should_continue_after_agent2(state: GraphState) -> str:
    if state.get("errors") and any("Agent2" in e for e in state["errors"]):
        return "end"
    if not state.get("schema_blueprint"):
        return "end"
    return "agent3"


def should_continue_after_agent3(state: GraphState) -> str:
    if state.get("errors") and any("Agent3" in e for e in state["errors"]):
        return "end"
    if state.get("cleaned_df") is None:
        return "end"
    return "agent4"


def should_continue_after_agent4(state: GraphState) -> str:
    if state.get("errors") and any("Agent4" in e for e in state["errors"]):
        return "end"
    if not state.get("stats"):
        return "end"
    return "end"   # Agent 5 will replace this


def build_pipeline() -> StateGraph:
    graph = StateGraph(GraphState)

    graph.add_node("agent1", agent1_structural_profiler)
    graph.add_node("agent2", agent2_semantic_tagger)
    graph.add_node("agent3", agent3_preprocessor)
    graph.add_node("agent4", agent4_analysis)

    graph.set_entry_point("agent1")

    graph.add_conditional_edges("agent1", should_continue_after_agent1,
                                {"agent2": "agent2", "end": END})
    graph.add_conditional_edges("agent2", should_continue_after_agent2,
                                {"agent3": "agent3", "end": END})
    graph.add_conditional_edges("agent3", should_continue_after_agent3,
                                {"agent4": "agent4", "end": END})
    graph.add_conditional_edges("agent4", should_continue_after_agent4,
                                {"end": END})

    return graph.compile()


if __name__ == "__main__":
    pipeline = build_pipeline()

    initial_state: GraphState = {
        "csv_path": "sample_sales.csv",
        "raw_profile": {},
        "schema_blueprint": {},
        "preprocessing_config": {},
        "preprocessing_profile": "auto",
        "dataset_domain": "",
        "_df_cache": None,
        "cleaned_df": None,
        "cleaned_csv_path": "",
        "scaling_params": {},
        "preprocessing_log": [],
        "data_quality": {},
        "stats": {},
        "chart_paths": [],
        "validation_result": {},
        "final_report_path": "",
        "errors": [],
    }

    final_state = pipeline.invoke(initial_state)

    raw_profile = final_state.get("raw_profile", {})
    stats = final_state.get("stats", {})
    data_quality = final_state.get("data_quality", {})
    schema_blueprint = final_state.get("schema_blueprint", {})
    chart_paths = final_state.get("chart_paths", [])
    errors = final_state.get("errors", [])

    raw_rows = raw_profile.get("shape", {}).get("rows", 0)
    raw_cols = raw_profile.get("shape", {}).get("cols", 0)
    clean_df = final_state.get("cleaned_df")
    clean_rows = int(clean_df.shape[0]) if clean_df is not None else 0
    clean_cols = int(clean_df.shape[1]) if clean_df is not None else 0

    strong_pairs = stats.get("correlation", {}).get("strong_pairs", [])
    anomalies = stats.get("anomalies", {})
    regression = stats.get("regression", {})

    semantic_counts = {}
    for meta in schema_blueprint.values():
        tag = meta.get("semantic_tag", "unknown")
        semantic_counts[tag] = semantic_counts.get(tag, 0) + 1

    anomaly_total = sum(v.get("count", 0) for v in anomalies.values() if isinstance(v, dict))
    significant_regression = sum(
        1 for v in regression.values() if isinstance(v, dict) and v.get("significant")
    )

    print("\n=== Pipeline Summary ===")
    print(f"Status: {'FAILED' if errors else 'SUCCESS'}")
    print(
        "Rows/Cols: "
        f"raw={raw_rows}x{raw_cols} -> cleaned={clean_rows}x{clean_cols}"
    )
    print(
        "Quality: "
        f"score={data_quality.get('overall_quality_score', 'n/a')} "
        f"remaining_nulls={data_quality.get('remaining_null_pct', 'n/a')}% "
        f"validation_fail={data_quality.get('validation_fail_pct', 'n/a')}%"
    )
    print(
        "Preprocessing: "
        f"profile={final_state.get('preprocessing_profile', 'unknown')} "
        f"domain={final_state.get('dataset_domain', 'unknown')}"
    )
    if final_state.get("cleaned_csv_path"):
        print(f"Cleaned CSV: {final_state['cleaned_csv_path']}")

    print("\n=== Analysis Highlights ===")
    print(f"Descriptive stats columns: {len(stats.get('descriptive', {}))}")
    print(f"Strong correlations: {len(strong_pairs)}")
    for pair in strong_pairs[:5]:
        print(
            "  - "
            f"{pair.get('col1')} <-> {pair.get('col2')} "
            f"(r={pair.get('pearson_r')}, {pair.get('direction')})"
        )
    print(f"Anomalies: {len(anomalies)} columns, {anomaly_total} total points")
    print(
        "Regression: "
        f"{len(regression)} models, {significant_regression} statistically significant"
    )
    print(f"Charts generated: {len(chart_paths)}")
    for p in chart_paths[:8]:
        print(f"  - {p}")
    if len(chart_paths) > 8:
        print(f"  - ... and {len(chart_paths) - 8} more")

    if semantic_counts:
        top_semantics = sorted(semantic_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        semantic_summary = ", ".join(f"{k}:{v}" for k, v in top_semantics[:8])
        print("\nSchema semantics:", semantic_summary)

    if errors:
        print("\n=== Errors ===")
        for e in errors:
            print(f"  - {e}")