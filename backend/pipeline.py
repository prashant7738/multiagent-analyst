from dotenv import load_dotenv
load_dotenv()

import json
from datetime import datetime, timezone
from pathlib import Path

from langgraph.graph import StateGraph, END
from agents.agent_1 import GraphState, agent1_structural_profiler
from agents.agent_2 import agent2_semantic_tagger
from agents.agent_3 import agent3_preprocessor
from agents.agent_4 import agent4_analysis
from agents.agent_5 import agent5_output_validator
from agents.agent_6 import agent6_insight_report_generator


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
    # Agent 3 also appends non-fatal "Agent3: ..." warnings (e.g. derived-metric
    # divergence) that must NOT abort the pipeline - cleaned_df is None only on
    # genuine failure (see agent_3._early_exit_with_error), so that's the sole
    # fatal signal here; don't blanket-match "Agent3" in errors.
    if state.get("cleaned_df") is None:
        return "end"
    return "agent4"


def should_continue_after_agent4(state: GraphState) -> str:
    if state.get("errors") and any("Agent4" in e for e in state["errors"]):
        return "end"
    return "agent5"


def should_continue_after_agent5(state: GraphState) -> str:
    if state.get("errors") and any("Agent5" in e for e in state["errors"]):
        return "end"
    if not state.get("validation_report", {}).get("passed"):
        return "end"
    return "agent6"



def _write_run_diagnostics(state: GraphState, output_path: str | Path | None = None) -> str:
    """Write the tester-facing metadata from the latest pipeline run."""
    if output_path is None:
        output_path = Path(__file__).resolve().parent / "outputs" / "agent_run_diagnostics.json"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    diagnostics = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input": {
            "csv_path": state.get("csv_path"),
            "sheet_name": state.get("sheet_name"),
        },
        "agent_1": {
            "raw_profile": state.get("raw_profile", {}),
            "columns": state.get("raw_profile", {}).get("columns", {}),
        },
        "agent_2": {
            "columns": state.get("schema_blueprint", {}),
        },
        "agent_3": {
            "preprocessing_profile": state.get("preprocessing_profile", ""),
            "dataset_domain": state.get("dataset_domain", ""),
            "preprocessing_config": state.get("preprocessing_config", {}),
            "scaling_params": state.get("scaling_params", {}),
            "preprocessing_log": state.get("preprocessing_log", []),
            "data_quality": state.get("data_quality", {}),
            "column_ledger": state.get("column_ledger", {}),
            "cleaned_csv_path": state.get("cleaned_csv_path", ""),
        },
        "agent_4": {
            "stats": state.get("stats", {}),
            "chart_paths": state.get("chart_paths", []),
        },
        "agent_5": {
            "validation_report": state.get("validation_report", {}),
        },
        "agent_6": {
            "insight_facts": state.get("insight_facts", {}),
            "insight_narrative": state.get("insight_narrative", {}),
            "report_path": state.get("report_path", ""),
        },
        "pipeline": {
            "errors": state.get("errors", []),
            "reliability": state.get("reliability", {}),
        },
    }

    if output_path.exists():
        output_path.unlink()
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(diagnostics, handle, indent=2, ensure_ascii=False, default=str)
        handle.write("\n")

    return str(output_path)


def build_pipeline() -> StateGraph:
    graph = StateGraph(GraphState)

    graph.add_node("agent1", agent1_structural_profiler)
    graph.add_node("agent2", agent2_semantic_tagger)
    graph.add_node("agent3", agent3_preprocessor)
    graph.add_node("agent4", agent4_analysis)
    graph.add_node("agent5", agent5_output_validator)
    graph.add_node("agent6", agent6_insight_report_generator)

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
    import os
    import uuid

    pipeline = build_pipeline()

    # Use absolute path relative to this script's location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, "claude_data1.csv")

    initial_state: GraphState = {
        "csv_path": csv_path,
        "raw_profile":           {},
        "schema_blueprint":      {},
        "_df_cache":             None,
        "cleaned_df":            None,
        "cleaned_csv_path":      "",
        "scaling_params":        {},
        "preprocessing_log":     [],
        "analysis_config":       {},
        "preprocessing_config":  {},
        "preprocessing_profile": "",
        "dataset_domain":        "",
        "data_quality":          {},
        "column_ledger":         {},
        "run_id":                os.getenv("PIPELINE_RUN_ID", uuid.uuid4().hex[:12]),
        "chart_specs":           [],
        "stats":                 {},
        "chart_paths":           [],
        "validation_report":     {},
        "insight_facts":         {},
        "insight_narrative":     {},
        "report_path":           "",
        "errors":                [],
        "reliability":           {},
    }

    final_state = pipeline.invoke(initial_state)
    diagnostics_path = _write_run_diagnostics(final_state)
    print(f"\n  Run diagnostics: {diagnostics_path}")

    # ── Agent 1 output ──────────────────────────────────────────────────────
    print("\n══════════════════════════════════════════")
    print("  AGENT 1 — Structural Profile")
    print("══════════════════════════════════════════")
    raw_profile = final_state.get("raw_profile", {})
    shape = raw_profile.get("shape", {})
    print(f"  Rows:            {shape.get('rows')}")
    print(f"  Columns:         {shape.get('cols')}")
    print(f"  Total cells:     {raw_profile.get('total_cells')}")
    print(f"  Missing rate:    {raw_profile.get('overall_missing_rate_pct')}%")
    print(f"  Duplicate rows:  {raw_profile.get('duplicate_rows')} ({raw_profile.get('duplicate_rate_pct')}%)")
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

    # ── Agent 5 output ──────────────────────────────────────────────────────
    print("\n══════════════════════════════════════════")
    print("  AGENT 5 — Output Validation")
    print("══════════════════════════════════════════")
    validation_report = final_state.get("validation_report", {})
    print(f"  Validation score:  {validation_report.get('overall_validation_score')}/100")
    print(f"  Passed:            {validation_report.get('passed')}")
    tier1_checks = validation_report.get("tier1_checks", {})
    for name, result in tier1_checks.items():
        print(f"    [{result.get('status')}] {name}")
    kappa_info = validation_report.get("semantic_tagging_agreement", {})
    print(f"  Semantic tagging agreement (Cohen's kappa): {kappa_info.get('cohen_kappa')} "
          f"({kappa_info.get('n_columns')} columns)")
    flagged_issues = validation_report.get("flagged_issues", [])
    if flagged_issues:
        print(f"  Flagged issues:  {len(flagged_issues)}")
        for issue in flagged_issues[:5]:
            print(f"    [{issue['severity']}] {issue['check']}: {issue['detail']}")

    # ── Agent 6 output ──────────────────────────────────────────────────────
    print("\n══════════════════════════════════════════")
    print("  AGENT 6 — Insight Report")
    print("══════════════════════════════════════════")
    report_path = final_state.get("report_path", "")
    if report_path:
        narrative = final_state.get("insight_narrative", {})
        print(f"  Report:          {report_path}")
        print(f"  Narrative source: {narrative.get('source')}")
        print(f"  Executive summary: {narrative.get('executive_summary', '')[:160]}")
        print(f"  Key findings:    {len(narrative.get('key_findings', []))}")
    else:
        print("  Skipped (Agent 5 validation failed or upstream data missing)")

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


