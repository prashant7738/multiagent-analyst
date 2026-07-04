from dotenv import load_dotenv
load_dotenv()

import numpy as np
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


def format_comprehensive_output(final_state):
    """Format 8-section comprehensive pipeline output for developers."""
    from datetime import datetime
    import os
    import pandas as pd
    
    # Extract data
    raw_profile = final_state.get("raw_profile", {})
    stats = final_state.get("stats", {})
    data_quality = final_state.get("data_quality", {})
    schema_blueprint = final_state.get("schema_blueprint", {})
    chart_paths = final_state.get("chart_paths", [])
    errors = final_state.get("errors", [])
    column_ledger = final_state.get("column_ledger", {})
    scaling_params = final_state.get("scaling_params", {})
    row_accounting = column_ledger.get("row_accounting", {})
    
    raw_rows = raw_profile.get("shape", {}).get("rows", 0)
    raw_cols = raw_profile.get("shape", {}).get("cols", 0)
    clean_df = final_state.get("cleaned_df")
    clean_rows = int(clean_df.shape[0]) if clean_df is not None else 0
    clean_cols = int(clean_df.shape[1]) if clean_df is not None else 0
    
    # ──────────────────────────────────────────────────────────────────────
    # 1. HEADER
    # ──────────────────────────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    dataset = os.path.basename(final_state.get("csv_path", "unknown"))
    profile = final_state.get("preprocessing_profile", "unknown")
    domain = final_state.get("dataset_domain", "unknown")
    
    print(f"\n=== Pipeline Run: {timestamp} | dataset={dataset} | profile={profile}/{domain} ===")
    print(f"Status: {'FAILED' if errors else 'SUCCESS'}")
    missing_pct = raw_profile.get("overall_missing_rate_pct", 0)
    dup_count = raw_profile.get("duplicate_rows", 0)
    print(f"Input:  {raw_rows} rows × {raw_cols} cols | {missing_pct}% missing | {dup_count} exact duplicates detected")
    
    # ──────────────────────────────────────────────────────────────────────
    # 2. PER-COLUMN LEDGER (if ledger data exists)
    # ──────────────────────────────────────────────────────────────────────
    ledger_cols = column_ledger.get("columns", {})
    if ledger_cols:
        print("\n=== Per-Column Transformation Ledger ===")
        print(f"{'COLUMN':<25} {'ACTION':<20} {'BEFORE→AFTER NULLS':<20} {'PARSE%':<8} {'RANGE%':<8} {'NOTES':<30}")
        print("─" * 110)
        for col, info in sorted(ledger_cols.items()):
            action = info.get("action", "—")[:18]
            before_nulls = info.get("before_nulls_pct", 0)
            after_nulls = info.get("after_nulls_pct", 0)
            parse_pct = info.get("parse_fail_pct", 0)
            range_pct = info.get("range_fail_pct", 0)
            notes = info.get("notes", "")[:28]
            print(
                f"{col:<25} {action:<20} {before_nulls:>5.1f}%→{after_nulls:<5.1f}% "
                f"{parse_pct:>6.1f}%  {range_pct:>6.1f}%  {notes:<30}"
            )
    
    # ──────────────────────────────────────────────────────────────────────
    # 3. EXPLICIT BOUNDS CHECK FOR CLIPPED COLUMNS
    # ──────────────────────────────────────────────────────────────────────
    clip_bounds = column_ledger.get("clip_bounds", {})
    clip_post_bounds = column_ledger.get("clip_post_bounds", {})
    clip_verified_from_csv = {}
    cleaned_csv_path = final_state.get("cleaned_csv_path", "")

    if cleaned_csv_path and os.path.exists(cleaned_csv_path):
        try:
            csv_df = pd.read_csv(cleaned_csv_path, low_memory=False)
            for col, bounds in clip_bounds.items():
                source_col = scaling_params.get(col, {}).get("raw_col", col)
                if source_col not in csv_df.columns:
                    continue
                numeric = pd.to_numeric(csv_df[source_col], errors="coerce").dropna()
                if numeric.empty:
                    continue
                clip_verified_from_csv[col] = {
                    "min": float(numeric.min()),
                    "max": float(numeric.max()),
                    "lower": float(bounds["lower"]),
                    "upper": float(bounds["upper"]),
                    "source_col": source_col,
                }
        except Exception as e:
            errors.append(f"Report: unable to re-read cleaned CSV for bounds check - {e}")

    if clip_bounds:
        print("\n=== Validation: Post-Clip Bounds ===")
        print(f"{'COLUMN':<25} {'MIN':<15} {'MAX':<15} {'STATUS':<8} {'BOUNDS':<30}")
        print("─" * 95)
        all_pass = True
        for col in sorted(clip_bounds.keys()):
            bounds = clip_bounds[col]
            verified = clip_verified_from_csv.get(col)
            post_bounds = clip_post_bounds.get(col, {})
            min_val = verified["min"] if verified else post_bounds.get("min", float("inf"))
            max_val = verified["max"] if verified else post_bounds.get("max", float("-inf"))
            lower = bounds["lower"]
            upper = bounds["upper"]
            
            within_bounds = (min_val >= lower - 1e-6 and max_val <= upper + 1e-6)
            status = "✓" if within_bounds else "✗ FAIL"
            if not within_bounds:
                all_pass = False
            source_col = verified.get("source_col", col) if verified else col
            bounds_str = f"[{lower:.1f}, {upper:.1f}] via {source_col}"
            print(
                f"{col:<25} {min_val:>14.2f} {max_val:>14.2f} {status:<8} {bounds_str:<30}"
            )
    
    # ──────────────────────────────────────────────────────────────────────
    # 4. VALIDATION FAILURE BREAKDOWN
    # ──────────────────────────────────────────────────────────────────────
    val_failures = column_ledger.get("validation_failures", {})
    if val_failures:
        print("\n=== Validation Failures Breakdown ===")
        total_rows_affected_checks = set()
        for check_name in sorted(val_failures.keys()):
            info = val_failures[check_name]
            count = info.get("count", 0)
            pct = info.get("pct", 0)
            print(f"  {check_name:<35} {pct:>6.1f}%  ({count:>4} rows)")
        
        print(f"\n  Total checks performed: {data_quality.get('validation_fail_pct', 'n/a')}% of rows affected")
    
    # ──────────────────────────────────────────────────────────────────────
    # 5. DEDUPLICATED CORRELATIONS
    # ──────────────────────────────────────────────────────────────────────
    strong_pairs = stats.get("correlation", {}).get("strong_pairs", [])
    if strong_pairs:
        # Filter out _raw/_scaled duplicates
        seen_base_pairs = set()
        filtered_pairs = []
        for pair in strong_pairs:
            col1 = pair.get("col1", "")
            col2 = pair.get("col2", "")
            # Remove _raw, _scaled, _parse_failed suffixes to find base name
            base1 = col1.replace("_raw", "").replace("_scaled", "").replace("_parse_failed", "")
            base2 = col2.replace("_raw", "").replace("_scaled", "").replace("_parse_failed", "")
            # Skip flag columns
            if "_failed" in col1 or "_failed" in col2:
                continue
            if base1 == base2:
                continue
            pair_key = tuple(sorted([base1, base2]))
            if pair_key not in seen_base_pairs:
                seen_base_pairs.add(pair_key)
                filtered_pairs.append({
                    **pair,
                    "col1": base1,
                    "col2": base2,
                })
        
        if filtered_pairs:
            print(f"\n=== Strong Correlations (deduplicated, |r| > 0.5): {len(filtered_pairs)} unique relationships ===")
            for pair in filtered_pairs[:10]:
                col1 = pair.get("col1")
                col2 = pair.get("col2")
                r = pair.get("pearson_r")
                direction = pair.get("direction")
                strength = pair.get("strength")
                print(f"  {col1:<25} <-> {col2:<25} r={r:>6.3f}  ({strength}, {direction})")
            if len(filtered_pairs) > 10:
                print(f"  ... and {len(filtered_pairs) - 10} more")
        
        # Report flag columns separately
        flag_pairs = [p for p in strong_pairs if "_failed" in p.get("col1", "") or "_failed" in p.get("col2", "")]
        if flag_pairs:
            print(f"\n=== Flag-Column Failure Rates ===")
            for pair in flag_pairs[:5]:
                col1 = pair.get("col1")
                col2 = pair.get("col2")
                print(f"  {col1:<35} {pair.get('pearson_r'):>6.3f}")
    
    # ──────────────────────────────────────────────────────────────────────
    # 6. ANOMALIES (raw values only)
    # ──────────────────────────────────────────────────────────────────────
    regression = stats.get("regression", {})
    if regression:
        reg_seen = set()
        reg_rows = []
        for col, info in regression.items():
            base_col = col.replace("_raw", "").replace("_scaled", "")
            if base_col.endswith("_failed"):
                continue
            if base_col in reg_seen:
                continue
            reg_seen.add(base_col)
            reg_rows.append((base_col, info))

        if reg_rows:
            significant = sum(1 for _, info in reg_rows if info.get("significant"))
            print(
                f"\n=== Regression (deduplicated): {len(reg_rows)} models, "
                f"{significant} significant ==="
            )
            for col, info in reg_rows[:10]:
                print(
                    f"  {col:<30} r2={info.get('r_squared', 0):.3f} "
                    f"p={info.get('p_value', 1):.4f} trend={info.get('trend', 'n/a')}"
                )
            if len(reg_rows) > 10:
                print(f"  ... and {len(reg_rows) - 10} more")

    # ──────────────────────────────────────────────────────────────────────
    # 7. ANOMALIES (raw values only)
    # ──────────────────────────────────────────────────────────────────────
    anomalies = stats.get("anomalies", {})
    if anomalies:
        anomaly_total = sum(v.get("count", 0) for v in anomalies.values() if isinstance(v, dict))
        anom_cols = [k for k, v in anomalies.items() if isinstance(v, dict) and v.get("count", 0) > 0]
        print(f"\n=== Anomalies (raw values only, z>2.5): {len(anom_cols)} columns, {anomaly_total} points ===")
        for col in sorted(anom_cols)[:8]:
            anom_info = anomalies[col]
            count = anom_info.get("count", 0)
            values = anom_info.get("anomaly_values", [])
            if values:
                min_val = min(values)
                max_val = max(values)
                print(f"  {col:<30} {count:>3} points  range: [{min_val:>8.1f}, {max_val:>8.1f}]")
        if len(anom_cols) > 8:
            print(f"  ... and {len(anom_cols) - 8} more")
    
    # ──────────────────────────────────────────────────────────────────────
    # 8. ROW ACCOUNTING
    # ──────────────────────────────────────────────────────────────────────
    print("\n=== Row Accounting ===")
    input_rows = int(row_accounting.get("input_rows", raw_rows))
    dedup_removed = int(row_accounting.get("exact_duplicates_removed", 0))
    dropped_impute = int(row_accounting.get("rows_dropped_by_imputation", 0))
    final_rows = int(row_accounting.get("final_rows", clean_rows))
    expected_final = input_rows - dedup_removed - dropped_impute
    rows_match = expected_final == final_rows

    print(f"  input                {input_rows:>6}")
    print(f"  - exact duplicates   {dedup_removed:>6}")
    if dropped_impute:
        print(f"  - imputation drop    {dropped_impute:>6}")
    print(f"  = cleaned            {final_rows:>6}  {'✓ matches' if rows_match else '✗ MISMATCH'}")
    
    # ──────────────────────────────────────────────────────────────────────
    # 9. TRUST CHECK
    # ──────────────────────────────────────────────────────────────────────
    print("\n=== Trust Check ===")

    # Check 1: row math + non-degenerate dataset sanity.
    survived_floor = final_rows >= int(np.ceil(0.5 * max(input_rows, 1)))
    non_empty = final_rows > 0
    row_check_ok = rows_match and non_empty and survived_floor
    if row_check_ok:
        print(f"✓ Row math reconciles ({final_rows}/{input_rows} rows retained)")
    else:
        print(
            "✗ Row sanity failed "
            f"(expected_final={expected_final}, actual={final_rows}, min_allowed={int(np.ceil(0.5 * max(input_rows, 1)))})"
        )
    
    # Check 2: post-clip bounds
    bounds_ok = True
    if not clip_bounds:
        bounds_ok = False
        print("✗ Post-clip bounds check skipped (no clipped columns recorded)")
    elif not clip_verified_from_csv:
        bounds_ok = False
        print("✗ Post-clip bounds check failed (cleaned CSV values unavailable)")
    else:
        bad_cols = []
        for col in clip_bounds.keys():
            bounds = clip_bounds[col]
            verified = clip_verified_from_csv.get(col)
            if not verified:
                bad_cols.append(f"{col}: missing in cleaned CSV")
                continue
            min_val = verified["min"]
            max_val = verified["max"]
            if not (min_val >= bounds["lower"] - 1e-6 and max_val <= bounds["upper"] + 1e-6):
                bad_cols.append(
                    f"{col}: min={min_val:.2f} max={max_val:.2f} expected=[{bounds['lower']:.2f}, {bounds['upper']:.2f}]"
                )
        bounds_ok = len(bad_cols) == 0
        if bounds_ok:
            print(f"✓ Post-clip bounds verified for all {len(clip_bounds)} clipped columns")
        else:
            print(f"✗ Post-clip bounds verification failed for {len(bad_cols)} columns")
            for msg in bad_cols[:5]:
                print(f"  - {msg}")
    
    # Check 3: no duplicate correlation pairs
    dedup_ok = (len(seen_base_pairs) if 'seen_base_pairs' in locals() else 0) == len(filtered_pairs) if 'filtered_pairs' in locals() else True
    print(f"{'✓' if dedup_ok else '✗'} No duplicate correlation pairs in report")
    
    # Check 4: quality score
    quality = data_quality.get("overall_quality_score", "unknown")
    print(f"✓ Quality score: {quality}/100")
    
    if errors:
        print(f"\n{'✗'} {len(errors)} errors detected")
        for err in errors:
            print(f"  - {err}")
    else:
        print(f"{'✓'} No errors")


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
        "column_ledger": {},
        "stats": {},
        "chart_paths": [],
        "validation_result": {},
        "final_report_path": "",
        "errors": [],
    }

    final_state = pipeline.invoke(initial_state)
    format_comprehensive_output(final_state)