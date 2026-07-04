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
    import json

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

    print("\n── Descriptive Stats ──")
    print(json.dumps(final_state["stats"].get("descriptive", {}), indent=2))

    print("\n── Strong Correlations ──")
    print(json.dumps(final_state["stats"].get("correlation", {}).get("strong_pairs", []), indent=2))

    print("\n── Anomalies ──")
    print(json.dumps(final_state["stats"].get("anomalies", {}), indent=2))

    print("\n── Regression ──")
    print(json.dumps(final_state["stats"].get("regression", {}), indent=2))

    print("\n── Charts Generated ──")
    for p in final_state["chart_paths"]:
        print(" •", p)

    if final_state["errors"]:
        print("\n── Errors ──")
        for e in final_state["errors"]:
            print(" •", e)