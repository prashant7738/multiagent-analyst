"""
pipeline.py — LangGraph pipeline wiring Agents 1, 2, and 3.
"""
from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph, END
from agents.agent_1 import GraphState, agent1_structural_profiler
from agents.agent_2 import agent2_semantic_tagger
from agents.agent_3 import agent3_preprocessor


# ── routing functions ─────────────────────────────────────────────────────────

def should_continue_after_agent1(state: GraphState) -> str:
    """Halt if CSV failed to load."""
    if state.get("errors") and any("Agent1" in e for e in state["errors"]):
        return "end"
    if not state.get("raw_profile"):
        return "end"
    return "agent2"


def should_continue_after_agent2(state: GraphState) -> str:
    """Halt if semantic tagging produced no blueprint."""
    if state.get("errors") and any("Agent2" in e for e in state["errors"]):
        return "end"
    if not state.get("schema_blueprint"):
        return "end"
    return "agent3"


def should_continue_after_agent3(state: GraphState) -> str:
    """Halt if preprocessing failed to produce a cleaned DataFrame."""
    if state.get("errors") and any("Agent3" in e for e in state["errors"]):
        return "end"
    if state.get("cleaned_df") is None:
        return "end"
    return "end"   # Agent 4 will be wired here once built


# ── graph builder ─────────────────────────────────────────────────────────────

def build_pipeline() -> StateGraph:
    graph = StateGraph(GraphState)

    graph.add_node("agent1", agent1_structural_profiler)
    graph.add_node("agent2", agent2_semantic_tagger)
    graph.add_node("agent3", agent3_preprocessor)

    graph.set_entry_point("agent1")

    graph.add_conditional_edges(
        "agent1",
        should_continue_after_agent1,
        {"agent2": "agent2", "end": END}
    )
    graph.add_conditional_edges(
        "agent2",
        should_continue_after_agent2,
        {"agent3": "agent3", "end": END}
    )
    graph.add_conditional_edges(
        "agent3",
        should_continue_after_agent3,
        {"end": END}
    )

    return graph.compile()


# ── quick test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    pipeline = build_pipeline()

    initial_state: GraphState = {
        "csv_path": "sample_sales.csv",
        "raw_profile": {},
        "schema_blueprint": {},
        "_df_cache": None,
        "cleaned_df": None,
        "scaling_params": {},
        "preprocessing_log": [],
        "stats": {},
        "chart_paths": [],
        "validation_result": {},
        "final_report_path": "",
        "errors": [],
    }

    final_state = pipeline.invoke(initial_state)

    print("\n── Raw Profile (shape) ──")
    print(json.dumps(final_state["raw_profile"].get("shape"), indent=2))

    print("\n── Schema Blueprint ──")
    print(json.dumps(final_state["schema_blueprint"], indent=2))

    print("\n── Preprocessing Log ──")
    for entry in final_state.get("preprocessing_log", []):
        print(" •", entry)

    print("\n── Scaling Params ──")
    print(json.dumps(final_state.get("scaling_params", {}), indent=2))

    print("\n── Cleaned DataFrame (first 3 rows) ──")
    df = final_state.get("cleaned_df")
    if df is not None:
        print(df.head(3).to_string())

    if final_state["errors"]:
        print("\n── Errors ──")
        for e in final_state["errors"]:
            print(" •", e)