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
    graph.add_edge("agent4", END)

    return graph.compile()


if __name__ == "__main__":
    import json
    import os

    pipeline = build_pipeline()

    # Use absolute path relative to this script's location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, "olist_products_dataset.csv")

    initial_state: GraphState = {
        "csv_path": csv_path,
        "raw_profile":           {},
        "schema_blueprint":      {},
        "_df_cache":             None,
        "cleaned_df":            None,
        "cleaned_csv_path":      "",
        "scaling_params":        {},
        "preprocessing_log":     [],
        "preprocessing_config":  {},
        "preprocessing_profile": "",
        "dataset_domain":        "",
        "data_quality":          {},
        "column_ledger":         {},
        "stats":                 {},
        "chart_paths":           [],
        "errors":                [],
        "reliability":           {},
    }

    final_state = pipeline.invoke(initial_state)

    # ── Agent 1 output ──────────────────────────────────────────────────────
    print("\n══════════════════════════════════════════")
    print("  AGENT 1 — Structural Profile")
    print("══════════════════════════════════════════")
    raw_profile = final_state.get("raw_profile", {})
    dataset = raw_profile.get("dataset", {})
    print(f"  Rows:            {dataset.get('rows')}")
    print(f"  Columns:         {dataset.get('columns')}")
    print(f"  Total cells:     {dataset.get('total_cells')}")
    print(f"  Missing rate:    {dataset.get('missing_rate_pct')}%")
    print(f"  Duplicate rows:  {dataset.get('duplicate_rows')} ({dataset.get('duplicate_rate_pct')}%)")
    col_profiles = raw_profile.get("columns", {})
    print(f"  Column profiles: {len(col_profiles)} columns profiled")

    # ── Agent 2 output ──────────────────────────────────────────────────────
    print("\n══════════════════════════════════════════")
    print("  AGENT 2 — Schema Blueprint")
    print("══════════════════════════════════════════")
    schema_blueprint = final_state.get("schema_blueprint", {})
    tag_counts = {}
    for meta in schema_blueprint.values():
        tag = meta.get("semantic_tag", "unknown")
        tag_counts[tag] = tag_counts.get(tag, 0) + 1
    for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1]):
        print(f"  {tag:<25} {count} columns")
    print(f"  Total tagged:    {len(schema_blueprint)} columns")

    # ── Agent 3 output ──────────────────────────────────────────────────────
    print("\n══════════════════════════════════════════")
    print("  AGENT 3 — Preprocessing")
    print("══════════════════════════════════════════")
    dq = final_state.get("data_quality", {})
    print(f"  Quality score:   {dq.get('overall_quality_score')}")
    print(f"  Completeness:    {dq.get('completeness_pct')}%")
    print(f"  Duplicates removed: {dq.get('duplicates_removed')}")
    cleaned_df = final_state.get("cleaned_df")
    if cleaned_df is not None:
        print(f"  Cleaned shape:   {cleaned_df.shape[0]} rows × {cleaned_df.shape[1]} cols")
    log = final_state.get("preprocessing_log", [])
    print(f"  Preprocessing steps logged: {len(log)}")
    cleaned_path = final_state.get("cleaned_csv_path", "")
    if cleaned_path:
        print(f"  Cleaned CSV:     {cleaned_path}")

    # ── Agent 4 output ──────────────────────────────────────────────────────
    print("\n══════════════════════════════════════════")
    print("  AGENT 4 — Statistical Analysis")
    print("══════════════════════════════════════════")
    stats = final_state.get("stats", {})
    descriptive = stats.get("descriptive", {})
    print(f"  Descriptive stats columns: {len(descriptive)}")
    strong_pairs = stats.get("correlation", {}).get("strong_pairs", [])
    print(f"  Strong correlation pairs:  {len(strong_pairs)}")
    if strong_pairs:
        for pair in strong_pairs[:5]:
            print(f"    {pair['col1']} ↔ {pair['col2']}  r={pair['pearson_r']} ({pair['strength']}, {pair['direction']})")
    anomaly_summary = stats.get("anomaly_summary", {})
    print(f"  Anomalous rows:  {anomaly_summary.get('unique_flagged_rows')} ({anomaly_summary.get('unique_flagged_row_pct')}%)")
    chart_paths = final_state.get("chart_paths", [])
    print(f"  Charts saved:    {len(chart_paths)}")
    for p in chart_paths:
        print(f"    {p}")

    # ── Reliability ─────────────────────────────────────────────────────────
    print("\n══════════════════════════════════════════")
    print("  PIPELINE RELIABILITY")
    print("══════════════════════════════════════════")
    reliability = final_state.get("reliability", {})
    print(f"  Overall confidence:  {reliability.get('overall_confidence')}")
    print(f"  Decision readiness:  {reliability.get('decision_readiness')}")
    stage_conf = reliability.get("stage_confidence", {})
    for stage, conf in stage_conf.items():
        print(f"    {stage}: {conf}")

    if final_state.get("errors"):
        print("\n── Pipeline Errors ──")
        for e in final_state["errors"]:
            print(f"  • {e}")


