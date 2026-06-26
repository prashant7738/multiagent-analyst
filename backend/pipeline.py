# pipeline.py — wire Agent 1 + 2 together with LangGraph

from langgraph.graph import StateGraph, END
from agents.agent_1 import GraphState, agent1_structural_profiler
from agents.agent_2 import agent2_semantic_tagger


def should_continue_after_agent1(state: GraphState) -> str:
    """Halt if CSV load failed."""
    if state.get("errors") and any("Agent1" in e for e in state["errors"]):
        return "end"
    if not state.get("raw_profile"):
        return "end"
    return "agent2"


def build_pipeline() -> StateGraph:
    graph = StateGraph(GraphState)

    graph.add_node("agent1", agent1_structural_profiler)
    graph.add_node("agent2", agent2_semantic_tagger)

    graph.set_entry_point("agent1")

    graph.add_conditional_edges(
        "agent1",
        should_continue_after_agent1,
        {"agent2": "agent2", "end": END}
    )
    graph.add_edge("agent2", END)

    return graph.compile()


# ── Quick test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    pipeline = build_pipeline()

    initial_state = {
        "csv_path": "sample_sales.csv",  # swap your CSV path
        "raw_profile": {},
        "schema_blueprint": {},
        "cleaned_df": None,
        "stats": {},
        "chart_paths": [],
        "validation_result": {},
        "final_report_path": "",
        "errors": [],
    }

    final_state = pipeline.invoke(initial_state)

    print("\n── Raw Profile ──")
    print(json.dumps(final_state["raw_profile"], indent=2))

    print("\n── Schema Blueprint ──")
    print(json.dumps(final_state["schema_blueprint"], indent=2))

    if final_state["errors"]:
        print("\n── Errors ──")
        for e in final_state["errors"]:
            print(" •", e)