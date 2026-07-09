from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph, END
from agents.agent_1 import GraphState, agent1_structural_profiler
from agents.agent_2 import agent2_semantic_tagger
from agents.agent_3 import agent3_preprocessor
from agents.agent_4 import agent4_analysis
from agents.agent_5 import agent5_validator
from agents.agent_6 import agent6_report_generator


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
    return "agent5"


def should_continue_after_agent5(state: GraphState) -> str:
    validation = state.get("validation_result", {})
    if not validation.get("passed", False):
        return "end"   # halt — bad report won't be generated
    return "agent6"       # proceed to Agent 6


def build_pipeline() -> StateGraph:
    graph = StateGraph(GraphState)

    graph.add_node("agent1", agent1_structural_profiler)
    graph.add_node("agent2", agent2_semantic_tagger)
    graph.add_node("agent3", agent3_preprocessor)
    graph.add_node("agent4", agent4_analysis)
    graph.add_node("agent5", agent5_validator)
    graph.add_node("agent6", agent6_report_generator)

    graph.set_entry_point("agent1")

    graph.add_conditional_edges("agent1", should_continue_after_agent1,
                                {"agent2": "agent2", "end": END})
    graph.add_conditional_edges("agent2", should_continue_after_agent2,
                                {"agent3": "agent3", "end": END})
    graph.add_conditional_edges("agent3", should_continue_after_agent3,
                                {"agent4": "agent4", "end": END})
    graph.add_conditional_edges("agent4", should_continue_after_agent4,
                                {"agent5": "agent5", "end": END})
    graph.add_conditional_edges("agent5", should_continue_after_agent5,
                                {"agent6": "agent6", "end": END})
    graph.add_edge("agent6", END)

    return graph.compile()


if __name__ == "__main__":
    import json

    pipeline = build_pipeline()

    initial_state: GraphState = {
        "csv_path": "DataCoSupplyChainDataset.csv",
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
        "validation_result":     {},
        "final_report_path":     "",
        "errors":                [],
    }

    final_state = pipeline.invoke(initial_state)

    print("\n── Validation Result ──")
    vr = final_state.get("validation_result", {})
    print(f"  Passed:           {vr.get('passed')}")
    print(f"  Confidence score: {vr.get('confidence_score')} (τ={vr.get('threshold')})")
    print(f"  Checks run:       {vr.get('checks_run')}")
    print(f"  Checks passed:    {vr.get('checks_passed')}")
    print(f"  Failures:         {vr.get('failure_count')}")
    print(f"  Warnings:         {vr.get('warning_count')}")

    if vr.get("failures"):
        print("\n── Critical Failures ──")
        for f in vr["failures"]:
            print(f"  ✗ {f}")

    if vr.get("warnings"):
        print("\n── Warnings ──")
        for w in vr["warnings"]:
            print(f"  ⚠ {w}")

    print("\n── Evidence Log ──")
    evidence_log = vr.get("evidence_log", [])
    print(f"  Total entries: {len(evidence_log)}")
    preview_count = 20
    for entry in evidence_log[:preview_count]:
        print(f"  {entry}")
    remaining = len(evidence_log) - preview_count
    if remaining > 0:
        print(f"  ... (remaining {remaining} evidence entries omitted)")

    if final_state["errors"]:
        print("\n── Pipeline Errors ──")
        for e in final_state["errors"]:
            print(f"  • {e}")