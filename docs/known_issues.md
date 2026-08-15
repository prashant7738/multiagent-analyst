# Known Issues (Audit Findings)

- [x] **1. MoM/QoQ growth figures contradict a direct recomputation from the source CSV**
  (e.g. reported December revenue -21% vs. actual +36% from raw `Gross_Sales`).
  Responsible: `_growth_rates()` in [agent_4.py](../backend/agents/agent_4.py#L464), which
  groups `cleaned_df` (post Agent 3 dedup/imputation, not the raw file) by whichever
  column happens to match `*_month`/`*_year` via `next(c for c in df.columns if
  c.endswith(...))` — an arbitrary pick when more than one date column exists. Feeds
  `_extract_growth_facts()` in [agent_6.py](../backend/agents/agent_6.py#L108).
  Fixed = growth % recomputed against the same source rows/column Agent 3 actually
  used is traceable and reproducible from the raw CSV, with the date column used for
  grouping made explicit (not an arbitrary first match), and dedup/imputation's effect
  on the revenue sum documented or excluded from the growth calc.
  **Fixed (2026-08-15)**: two independent bugs found via
  [test_ground_truth_reconciliation.py](../backend/tests/test_ground_truth_reconciliation.py):
  (1) `_clip_outliers()` in [agent_3.py](../backend/agents/agent_3.py) had no `semantic_tag`
  override (unlike `_scale_columns()`, which already skipped currency/datetime/identifier),
  so a currency column mistagged `scaling_allowed: True` by the LLM got IQR-clipped,
  understating total revenue by 18.6%. Fixed by adding the same
  `semantic_tag in ("currency","financial","datetime","identifier")` guard to
  `_clip_outliers()`. (2) `_coerce_types()`/`_extract_date_features()` in
  [agent_3.py](../backend/agents/agent_3.py) called `pd.to_datetime(df[col],
  errors="coerce")` with no `format` argument on `Order_Date`, a column with genuinely
  mixed date formats (ISO, `DD/MM/YYYY`, `MM-DD-YYYY`, `"Mon DD, YYYY"`). Without an
  explicit `format`, pandas infers ONE format from the first value and silently NaTs
  every row that doesn't match it - confirmed 1313/2537 (51.7%) of `Order_Date` values
  became NaT this way, vs only 15/2537 with `format="mixed"`. This is why nearly every
  month/quarter (not just December/Q4) showed a growth mismatch: most transactions for
  most periods were silently falling out of the date-based groupby. Fixed by adding
  `format="mixed"` to both `pd.to_datetime` calls in agent_3.py (matching what
  `agent_1.py`'s type-sniffer and the reconciliation test's ground-truth loader already
  used). Verified: `test_ground_truth_reconciliation.py` is now 5/5 passing (was 56
  failed/2 passed), including all MoM/QoQ sign-match and magnitude asserts. Full suite:
  3 failed/93 passed/5 skipped - same 3 pre-existing baseline failures documented in
  repo memory, no regressions.

- [ ] **2. Category normalization only folds case; typos/near-duplicates stay separate**
  ("COMPLETE"/"Complete" merge, "Completed" doesn't).
  Responsible: `_normalize_category_label()` and `_canonicalize_text_values()` in
  [agent_3.py](../backend/agents/agent_3.py#L228-L235), used by `_standardize_text_columns()`
  — logic is separator cleanup + `casefold()` + `title()` only, no fuzzy/typo matching.
  Fixed = near-duplicate spellings within a configurable edit-distance/similarity
  threshold are merged (or at minimum flagged for review) in addition to exact
  case/separator folding, with the merge decisions logged in `preprocessing_log`.

- [ ] **3. `Region`, `Product_Category`, `Customer_Segment`, `Sales_Representative` are
  never used as groupby dimensions anywhere in insight/ranking/chart generation.**
  Responsible: `_top_bottom_rankings()` in [agent_4.py](../backend/agents/agent_4.py#L561-L594)
  only considers columns returned by `_categorical_cols()` and picks the top-3 most
  "differentiated" by revenue-share spread (`candidates.sort(...)[:3]`) — legitimate
  dimensions can simply lose that selection race and never appear anywhere else in the
  pipeline (no other function groups by categorical columns).
  Fixed = either all four named dimensions are guaranteed at least one ranking/chart
  slot regardless of the top-3 cap, or the selection logic/limit is made configurable
  and its exclusions are explicitly surfaced in the report instead of silently dropped.

- [ ] **4. A ranking table header says "(4 categories)" but only 3 rows render.**
  Responsible: `_extract_ranking_facts()` in [agent_6.py](../backend/agents/agent_6.py#L138-L148):
  `"total_categories": data.get("total_categories")` passes through Agent 4's
  untruncated count, while `"top"`/`"bottom"` are sliced with
  `[:TOP_RANKING_LIMIT]` where `TOP_RANKING_LIMIT = 3` ([agent_6.py](../backend/agents/agent_6.py#L43)).
  The template ([insight_report.html.jinja](../backend/templates/insight_report.html.jinja#L156))
  renders `data.total_categories` in the header and `data.top`/`data.bottom` in the body —
  the two numbers are guaranteed to diverge whenever a category has more than 3 groups.
  Fixed = header count and rendered row count always agree — either show
  `min(total_categories, TOP_RANKING_LIMIT)` in the header, or state explicitly
  "showing top {{ TOP_RANKING_LIMIT }} of {{ total_categories }}".

- [ ] **5. "Top Correlations" includes tautological pairs (one column is a direct linear
  transform of the other, e.g. `Net_Sales` vs. a column derived from it).**
  Responsible: `_numeric_cols()` in [agent_4.py](../backend/agents/agent_4.py#L60-L78) excludes
  Agent 3's audit-trail suffix columns (`_raw`/`_scaled`/`_was_clipped`,
  `_VALIDATION_SUFFIXES`) but does **not** exclude Agent 3's derived business-metric
  columns from `_derive_business_metrics()` ([agent_3.py](../backend/agents/agent_3.py)) —
  e.g. `Profit = Revenue - Cost`, `Total Revenue = Price * Units` — which are
  algebraic functions of other columns already in the same correlation matrix.
  `flag_leakage_columns()` ([agent_4.py](../backend/agents/agent_4.py#L299-L347))'s
  "near-perfect r with exactly one other column, near-zero with the rest" heuristic
  doesn't catch these because a derived metric is usually also correlated with its
  other input columns, so the "near-zero with everything else" condition fails.
  Fixed = derived/composite columns are either excluded from the correlation input
  set, or `flag_leakage_columns` gains an explicit check for known
  derivation relationships (e.g. tracking which columns Agent 3 derived from which),
  so a metric is never shown correlated with its own source column(s).

- [ ] **6. Anomaly detection flags ~24% of rows vs. ~4% for a plain \|z\|>3.5 check on the
  same columns — IQR fallback over-flags legitimate long-tail values.**
  Responsible: `_detect_anomalies()` in [agent_4.py](../backend/agents/agent_4.py#L749),
  specifically the skew-aware branch that falls back to IQR with
  `ANOMALY_IQR_MULTIPLIER` for skewed columns containing non-positive values (per
  existing repo notes, this was already partially addressed but is still the most
  permissive/aggressive of the three methods — plain zscore, log_zscore, iqr — and
  the audit's ~24% figure suggests it's still the dominant contributor on the
  dataset in question).
  Fixed = the IQR-fallback flag rate on skewed non-positive columns is brought in
  line with (or explicitly justified against) a plain z-score sanity check on the
  same columns — e.g. via a wider/tuned multiplier, or documenting per-method flag
  rates in `anomaly_summary` so the discrepancy is visible rather than hidden behind
  one aggregate percentage.

- [ ] **7. Duplicate row detection results are never surfaced in the output report.**
  Responsible: `_extract_quality_facts()` in [agent_6.py](../backend/agents/agent_6.py#L77-L86)
  reads `data_quality.get("duplicates_removed")` — a key that **does not exist** in
  the dict actually produced by `_compute_enhanced_quality_score()` in
  [agent_3.py](../backend/agents/agent_3.py#L1289-L1340) (real keys are
  `duplicate_rate_pct` and `rows_removed`), so this fact is always `None`. Even if the
  key were correct, [insight_report.html.jinja](../backend/templates/insight_report.html.jinja)
  never references any duplicate-related field.
  Fixed = `_extract_quality_facts` reads the real key (`duplicate_rate_pct` /
  `rows_removed`), and the template renders a "Duplicate Rows" line (count + %)
  wherever the quality section is shown.

- [ ] **8. Missing-value statistics are never surfaced in the output report.**
  Responsible: same root cause as #7 — `_extract_quality_facts()` in
  [agent_6.py](../backend/agents/agent_6.py#L77-L86) reads `data_quality.get("completeness_pct")`,
  a key that doesn't exist (actual keys from
  [agent_3.py](../backend/agents/agent_3.py#L1332-L1338) are `raw_missing_pct`,
  `remaining_null_pct`, `raw_completeness_pct`), so it's always `None`; and
  [insight_report.html.jinja](../backend/templates/insight_report.html.jinja) has no
  section rendering missingness at all (confirmed only `overall_quality_score` and
  `anomaly_quality_penalty` are referenced from `facts.data_quality`).
  Fixed = `_extract_quality_facts` reads the real keys, and the report includes a
  missingness summary (overall % + notable per-column gaps from
  `null_pct_by_column`).

- [ ] **9. Chart images are referenced via absolute local filesystem paths, breaking the
  report on other machines.**
  Responsible: `_render_html()` in [agent_6.py](../backend/agents/agent_6.py#L546-L559):
  `resolved_chart_paths = [str(Path(p).resolve()) for p in chart_paths ...]`, embedded
  by [insight_report.html.jinja](../backend/templates/insight_report.html.jinja#L200)
  as `<img src="file://{{ path }}">`. This was originally done to fix broken images
  within WeasyPrint's `base_url` resolution, but the resulting HTML file is not
  portable — every `<img>` src is this machine's absolute path.
  Fixed = images are embedded in a way that survives being opened elsewhere (e.g.
  base64-inline `<img>` data URIs, or copying charts next to the report and using
  relative paths + a WeasyPrint `base_url` set to the report's own directory) instead
  of hardcoded local absolute paths.

- [ ] **10. The "narrative self-check" reports numbers as validated when it only checks
  consistency against the pipeline's own intermediate values, not the raw source file —
  giving false confidence on finding #1.**
  Responsible: `_check_narrative_grounding()` in
  [agent_6.py](../backend/agents/agent_6.py#L257-L292): `known_values =
  _flatten_numeric_facts(insight_facts)` where `insight_facts` is built entirely from
  `state["stats"]`/`state["data_quality"]` (Agent 3/4's own computed output). It never
  reads or recomputes anything from `state["csv_path"]`, so an internally-consistent
  but substantively wrong number (e.g. the MoM growth bug in #1) is reported as
  "grounded" and passes with high `confidence`.
  Fixed = the self-check (or a separate step) re-derives at least one or two headline
  numbers directly from the raw source CSV and compares against the reported figures,
  and the report/`claims_grounding` output is labeled to make clear whether grounding
  was checked against raw source data or only against the pipeline's own intermediate
  facts.

## Notes on scope

- **#3 and #6** are behavioral/threshold issues rather than a single obvious bug line
  — the exact responsible functions are pointed to (`_top_bottom_rankings`'s top-3
  selection cap, and `_detect_anomalies`'s IQR-fallback branch), but the fix will
  require a design decision (how many dimensions to guarantee, what
  multiplier/method to use) rather than a pure logic correction.
- No code changes have been made in this pass — this file is a tracking checklist only.
