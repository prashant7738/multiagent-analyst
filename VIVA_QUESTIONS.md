# Viva / Defense Question Bank (~500 Q&A)

Organized by topic. Each answer is deliberately short (1–3 sentences) — expand verbally in the room using [`DEFENSE_README.md`](./DEFENSE_README.md) and [`MAGIC_NUMBERS.md`](./MAGIC_NUMBERS.md) for the full reasoning. Where a question asks "where did that number come from," the short answer here always points at the relevant `MAGIC_NUMBERS.md` row.

---

## A. General, Motivation, Scope, Objectives (30)

1. **What does this project do?**
   Converts a raw business CSV into a validated, plain-language analytical report automatically, using six specialized agents instead of one general-purpose LLM.
2. **Why not just use ChatGPT/an LLM directly on the CSV?**
   A single LLM mixes exact arithmetic with fluent explanation in one pass, which is exactly where hallucinated numbers come from; we measured a 10× numerical error from a general-purpose Qwen model on the same dataset (see Results).
3. **Who is the target user?**
   Small/medium businesses, NGOs, and municipal bodies (per Digital Nepal Framework context) that have data but lack in-house data-analyst expertise — non-technical stakeholders, specifically.
4. **What's the core motivation?**
   Organizations have data but not the technical skill to use it; existing tools need statistics/programming knowledge, and existing LLM tools can produce unverified/hallucinated insights.
5. **What are the three concrete problems this addresses?**
   Manual workflows taking days-to-weeks, lack of standardization across analysts, and limited accessibility for non-technical stakeholders.
6. **What are the two stated objectives?**
   (1) An autonomous multi-agent system converting raw data into professional reports without manual coding; (2) making financial analytics accessible to SMEs through a no-code web interface.
7. **What is explicitly in scope?**
   Sales records, transaction logs, expense sheets; a six-agent pipeline from CSV input to report output; a web app (FastAPI + React), no extra software needed by the end user.
8. **What is explicitly out of scope / future work?**
   Direct database connectors, real-time streaming, forecasting/ML training, multi-tenant RBAC, non-English NLU, and exposing Excel/JSON/Parquet on the web upload route.
9. **What are the primary use cases?**
   Sales performance tracking, financial reporting & budgeting, retail/e-commerce analytics, small-business operations, and translating financial data for non-finance teams.
10. **Why CSV as the primary format?**
    It's the universal lowest-common-denominator export format from spreadsheets and databases that non-technical users already have.
11. **Does the system support Excel/JSON/Parquet?**
    Yes, internally in Agent 1's loader (`_load_dataframe`), but the web upload route currently only accepts CSV — that's a documented gap, not a bug.
12. **What framework orchestrates the agents?**
    LangGraph (`langgraph.graph.StateGraph`), a state-based DAG orchestration library built on top of LangChain concepts.
13. **How many agents are there and what do they do, one line each?**
    1) Profile raw structure, 2) tag column semantics (LLM), 3) clean/transform data, 4) compute statistics & charts, 5) validate everything (trust gate), 6) write the narrative report (LLM, grounded).
14. **Which agents call an LLM?**
    Only Agent 2 (semantic tagging) and Agent 6 (narrative generation). Agents 1, 3, 4, and Agent 5's Tier-1 checks are pure deterministic Python.
15. **What's the "one sentence" differentiator from a plain LLM chatbot?**
    Deterministic computation and language generation are structurally separated, so numbers can never be "made up" by the model — only judgment tasks (naming, explaining) touch the LLM.
16. **What LLM is used and why?**
    Groq's hosted `qwen/qwen3.6-27b`, chosen for Groq's LPU hardware giving very low inference latency, which matters because Agent 2 may tag dozens of columns per run.
17. **What happens if the LLM is unavailable?**
    Automatic failover: Groq → Gemini (multi-key, multi-model) → deterministic heuristic fallback. The pipeline never hard-fails because of an LLM outage.
18. **What's the single most defensible design decision in this project?**
    Agent 5 — a hard validation gate that stops the pipeline (and never lets Agent 6 run) if deterministic contract checks fail, at zero extra LLM cost.
19. **What does "multi-agent" mean here, precisely?**
    Six independent pure functions (`state -> state`) that never call each other directly; they only communicate through one shared `GraphState` object, orchestrated by conditional edges.
20. **Is this a "true" multi-agent system in the AutoGen/CrewAI conversational-agent sense?**
    No — there's no agent-to-agent dialogue or negotiation; it's a fixed pipeline of specialized stages, closer to a DAG-orchestrated workflow than a conversational multi-agent system. That's a deliberate choice for reproducibility over flexibility.
21. **What's the report's stated research gap?**
    A gap between BI tools (need technical skill), LLM-assistant tools (accessible but not reproducible/auditable), and multi-agent frameworks (used mostly for software engineering/general reasoning, not data analytics pipelines).
22. **How does this project position itself relative to LAMBDA (Sun et al.)?**
    Similar spirit (specialized agents for data analysis) but this project adds a dedicated deterministic validation gate (Agent 5) and claim-grounding step (Agent 6) that LAMBDA-style systems don't emphasize.
23. **How does this relate to Data2Vis/VizML/Draco/DeepEye (automated visualization research)?**
    Those treat chart selection as a learned/constraint-based recommendation problem; this project's `chart_planner.py` does something similar with a hand-built effect-size scoring function (η², Pareto concentration, r², Cramér's V) rather than a trained model.
24. **Why LangGraph over CrewAI or AutoGen?**
    LangGraph gives explicit stateful, conditional-routing DAG control that maps directly onto a fixed six-stage pipeline with hard gating logic — CrewAI/AutoGen are more suited to open-ended agent conversation, which this workflow doesn't need.
25. **What does "economic feasibility" mean for this project?**
    Uses pay-per-use hosted LLM APIs (Groq/Gemini) instead of requiring GPU infrastructure for local model hosting, keeping infra cost near zero for a small deployment.
26. **What does "technical feasibility" mean here?**
    All components (Python, pandas, scikit-learn, LangGraph, FastAPI, React) are mature, well-documented, open-source technologies; no novel hardware/algorithm research risk.
27. **What is "operational feasibility"?**
    The system runs as a normal web app; the target users (SME staff) only need a browser, not new software or training in query languages/statistics.
28. **What's the elevator pitch for a non-technical panel member?**
    "Upload your sales spreadsheet, get a report back that explains what happened, why it matters, and what to do next — and every number in it is double-checked automatically before it's shown to you."
29. **What's the single most important number to remember from Results?**
    The general-purpose LLM had a 10× scaling error on total revenue ($1.33B vs actual $13.33B) while this pipeline was numerically exact — that's the strongest evidence for the architecture's value.
30. **If you had to cut one agent, which would hurt the argument most and why?**
    Agent 5 — without it there's no automated proof that the report is trustworthy; every other agent's argument ("we're not hallucinating") depends on Agent 5 actually gating the pipeline.

---

## B. Architecture & Orchestration (35)

31. **What is `GraphState`?**
    A single `TypedDict` (in `main.py`) defining every field that flows between agents — inputs, each agent's outputs, and shared fields like `errors` and `reliability`.
32. **Why a shared state object instead of agents calling each other directly?**
    Decouples every agent so each is independently testable and replaceable — an agent only needs to know the shape of the state, not the internals of any other agent.
33. **What makes each agent function "pure"?**
    `state -> state`: no agent mutates global variables or another agent's internals; new/updated state is returned and merged, and side effects are limited to logging and file writes (charts, reports).
34. **How does routing between agents work?**
    `graph.add_conditional_edges(agent_name, router_function, {...})` — after each agent runs, a small router function inspects `state["errors"]`/key outputs and returns "next_agent" or "end".
35. **What causes the pipeline to stop early?**
    Agent 1 load failure or empty `raw_profile`; Agent 2 empty `schema_blueprint`; Agent 3's `cleaned_df` being `None` (genuine failure, not just a warning); Agent 4 errors; Agent 5's `validation_report["passed"] == False`.
36. **Why does Agent 3's router check `cleaned_df is None` instead of "any 'Agent3' string in errors"?**
    Agent 3 also appends non-fatal warnings prefixed "Agent3:" (e.g. derived-metric divergence) that must NOT abort the pipeline — only an actual missing `cleaned_df` (set by `_early_exit_with_error`) is the fatal signal.
37. **What is `run_id` and why does it matter?**
    A short unique id per pipeline run; charts/reports are written to `outputs/charts/<run_id>/` and `outputs/reports/<run_id>/` so concurrent jobs from different users never overwrite each other's files.
38. **What is the reliability layer?**
    A cross-cutting mechanism (`update_reliability()` in `main.py`) where every agent reports a confidence score (0–1) plus supporting evidence strings after doing its work; these are aggregated into an overall confidence and a `decision_readiness` label.
39. **How is overall confidence computed?**
    The mean of every numeric per-stage confidence value reported so far.
40. **What are the three `decision_readiness` labels and thresholds?**
    `"ready"` at overall confidence ≥0.85, `"needs_review"` at ≥0.65, `"blocked"` below that.
41. **What confidence does Agent 1 report and how?**
    `1.0 − (missing_rate/100)×0.5 − (duplicate_rate/100)×0.3`, clamped to [0,1] — less missing/duplicate data yields higher confidence in the raw profile.
42. **Does Agent 2 report a numeric confidence into the reliability layer?**
    The per-column confidence scores exist (0–100 each), but Agent 2 itself is one of the two agents where the report notes confidence as "n/a" for the overall reliability table on the sample run — the more meaningful cross-check for Agent 2 is Agent 5's Cohen's kappa, computed after the fact.
43. **How does Agent 3 compute its confidence?**
    `0.5 × (quality_score/100) + 0.5 × (rows_after/rows_before)` — combines how clean the result is with how much data survived.
44. **How does Agent 4 compute its confidence?**
    A simple heuristic: `0.9` if `stats` is non-empty, else `0.4` — reflects "did the analysis actually produce output," not a statistical measure.
45. **How does Agent 5 compute its confidence?**
    From its own validation score (scaled 0–1), halved if `review_required` is true (from data-quality issues), and reduced further per insufficient-sample trend flagged.
46. **How does Agent 6 compute its confidence?**
    `0.95` if the narrative came from the LLM path, `0.55` if it fell back to pure-deterministic wording, then both are scaled by `(0.7 + 0.3 × grounding_confidence)`.
47. **What was the overall reliability on the sample run?**
    0.97 mean confidence, `decision_readiness = "ready"`.
48. **Why is a "trust score" a novel/valuable idea here?**
    Most LLM pipelines return an answer with no self-assessment of how much to trust that particular run; this makes trust an explicit, auditable, per-run number rather than an assumed constant.
49. **What's the difference between `errors` and `reliability` in `GraphState`?**
    `errors` is a flat list of hard/soft failure messages accumulated across agents; `reliability` is a structured confidence/evidence/readiness record, orthogonal to whether anything technically "errored."
50. **How is testability achieved?**
    Each agent is a standalone function with a documented state-in/state-out contract, so `backend/tests/test_agent*.py` (200+ tests) can call any agent directly with a synthetic state dict, with no need to run the whole pipeline.
51. **What's `_df_cache` and why is it "internal"?**
    The raw DataFrame Agent 1 loaded, cached in `state["_df_cache"]` so downstream agents (2, 5) don't have to re-read the source file from disk; the underscore prefix signals it's plumbing, not a reportable output.
52. **What's `raw_shape` and why is it separate from `raw_profile["shape"]`?**
    Captured immediately after ingestion, before any transform (encoding fixes, feature engineering) ever touches the DataFrame — the single source of truth for "raw row/column counts" that every downstream agent (especially Agent 6, when it reports "started with N columns") must use, rather than re-deriving from an already-transformed frame.
53. **What is `_write_run_diagnostics`?**
    A `pipeline.py` helper that dumps every agent's key output (profile, blueprint, preprocessing log, stats, validation report, narrative, errors, reliability) into one `outputs/agent_run_diagnostics.json` file after a CLI run — a single artifact a tester/examiner can open to see the whole run.
54. **Why is `python pipeline.py` different from the web app's flow?**
    The CLI entry point (`if __name__ == "__main__"`) is a fixed demo/dev harness using a hardcoded default CSV; the web app instead builds the same `GraphState` dynamically per uploaded file inside `job_manager.py` and streams progress over SSE.
55. **What happens to intermediate state fields not yet populated (Agent 5/6 placeholders) early in a run?**
    They're initialized to empty dicts/lists/strings in `GraphState`'s construction, so every agent can safely call `.get(field, default)` without a `KeyError`, even before that agent has run.
56. **Is the pipeline synchronous or asynchronous?**
    `pipeline.invoke(state)` runs synchronously end-to-end within `job_manager.py`'s background job execution; concurrency comes from running multiple jobs (each with its own thread and `run_id`), not from async agent execution.
57. **How are per-user API keys kept from leaking across concurrent jobs?**
    `request_context.get_api_key_override()` and the key-usage tracker (`key_indicator.py`) both use thread-local storage, so each concurrently-running job's key usage is captured independently.
58. **What does "run isolation" protect against?**
    Two users analyzing different CSVs at the same time overwriting each other's chart PNGs or report HTML files, since both would otherwise write to the same shared `outputs/charts/` directory.
59. **Why store `preprocessing_config` and `preprocessing_profile` in state rather than as constants?**
    So the same code can run with different strictness settings per job/dataset (auto-selected or user-requested), and so the exact configuration used is auditable per run (it's echoed into the diagnostics JSON).
60. **What's `dataset_domain` used for?**
    Auto-detected (`finance_sales` vs `generic`) from column names/tags in Agent 3, used to pick a sensible default preprocessing profile (`strict` for finance) when the caller hasn't explicitly chosen one.
61. **What would happen if Agent 4 crashed with an unhandled exception?**
    It isn't fully caught at the top level of `agent4_analysis` itself for every internal step (individual chart-family calls run inside `_agent4_analysis_inner`); an uncaught exception there would propagate up through `pipeline.invoke` — in practice the code guards the riskiest sub-steps (e.g. the chart planner call) in try/except so one family's failure doesn't take down the whole analysis.
62. **How does the chart planner's failure get handled gracefully?**
    Wrapped in try/except in `_agent4_analysis_inner`; on failure it logs an `Agent4:` error and falls back to the legacy per-family chart candidates only, rather than losing all charts.
63. **What is `MAX_CHARTS_PER_REPORT` and where is it enforced?**
    An Agent 4 constant (`16`, env-overridable) enforced twice: once for the legacy PNG candidate pool (ranked and pruned, with dropped PNGs deleted from disk) and once again for the unified `chart_specs` gallery (`finalize_specs(..., cap=...)`).
64. **What is a `ChartSpec`?**
    A unified, dataset-agnostic dict contract (`chart_spec.py`) carrying a chart's title, plain-language explanation, alt text, annotations, and pre-aggregated data — one shape consumed by both the interactive ECharts frontend and the static matplotlib/report path.
65. **Why maintain both "legacy" per-family charts and the new "planner" chart specs?**
    Backward compatibility during an incremental migration — `wrap_legacy_candidate()` adapts the older, hand-coded chart-family outputs (agent_4) into the same `ChartSpec` shape the newer, effect-size-scored planner (`chart_planner.py`) produces, so both can be ranked and capped together.

---

## C. Agent 1 — Structural Profiler (30)

66. **What's Agent 1's core philosophy?**
    "No fixing, no inference of meaning — just observe and record." It only describes the raw data.
67. **Does Agent 1 call any LLM?**
    No — it is 100% deterministic Python (pandas/numpy).
68. **What file formats can Agent 1 load?**
    CSV/TSV (including mixed-delimiter), Excel (.xlsx/.xlsm/.xls), JSON/JSON-Lines/NDJSON, Parquet.
69. **How does the mixed-delimiter CSV reader work?**
    Per-line delimiter detection: for each line, count `;` vs `,` and use whichever is more frequent; if the resulting field count doesn't match the header, it retries with the other delimiter before giving up.
70. **What encodings does the CSV reader try, in order?**
    `utf-8-sig`, then `cp1252`, then `latin-1` — the three most common real-world encodings for exported business CSVs.
71. **How are multi-sheet Excel files handled?**
    If a specific sheet isn't requested and there's more than one sheet, all sheets are read and concatenated (outer join on columns), each row tagged with a `_source_sheet` column; a schema mismatch across sheets is surfaced as a pipeline warning.
72. **What JSON shapes does the JSON reader support, and in what priority order?**
    JSON-Lines (one object per line) first, then a records list `[{...}, ...]`, then a columns dict `{col: {idx: val}}`, then a pandas-default fallback.
73. **What does Agent 1 compute per column?**
    dtype, missing count/%, unique count, first 3 sample values, a candidate-key hint, an IQR-based outlier analysis, datetime parseability %, and lightweight format hints (currency/date/identifier-like).
74. **What is a "candidate key hint"?**
    A boolean flag set when a column's `cardinality_ratio ≥ 0.95`, has 0 missing values, and the dataset has more than 1 row — signals "this might be a primary key."
75. **What dataset-level enrichments does Agent 1 add beyond per-column stats?**
    Distribution analysis (skew/kurtosis-based typing) for numeric columns, implicit-missingness detection (sentinel values/null-strings), and column-relationship detection (candidate keys, duplicate column pairs, strong numeric correlations).
76. **What is "implicit missingness detection"?**
    Flags numeric sentinel values (e.g. `-999`, `9999`) or textual "null-looking" strings (e.g. `"n/a"`, `"unknown"`) that encode missingness without being an actual `NaN` — informs Agent 2/3's cleaning decisions.
77. **Why is `0` treated specially in sentinel detection?**
    Zero is an extremely common legitimate value; it's only flagged as a suspicious sentinel if it makes up ≥25% of the column, avoiding false positives on normal "0 units sold" data.
78. **What does "column relationship detection" report?**
    Potential keys (fully unique, no missing), suspicious duplicate column pairs (`df[c1].equals(df[c2])`), and numeric pairs with `|Pearson r| ≥ 0.5`.
79. **How is skewness/kurtosis used to classify a distribution?**
    "Normal" if `|skew| ≤ 0.5` and `|excess kurtosis| ≤ 1.0`; "right_skewed" if `skew > 1.0`; otherwise "symmetric" (a catch-all including mild left-skew).
80. **What are "format hints" and how are they detected?**
    Cheap heuristics on the first 10 non-null sample values and the column name: presence of currency symbols → `currency_like`; "date"/"time" in the name or dash-containing 8+ char samples → `date_like`; name ending in `_id`/starting with `id_` → `identifier_like`.
81. **How does Agent 1 estimate datetime "parseability"?**
    `pd.to_datetime(..., errors="coerce", format="mixed")` on non-null string values, then the % that successfully parsed (didn't become `NaT`).
82. **Why is the parseability threshold 80% and not 100%?**
    100% would misclassify a mostly-date column with a handful of genuinely corrupt/garbled entries as "not a date column"; 80% tolerates realistic partial data quality.
83. **What outlier method does Agent 1 use, and is it acted on?**
    IQR (Q1−1.5IQR .. Q3+1.5IQR) — purely descriptive metadata here; Agent 1 itself doesn't remove or clip anything, it only records `outlier_count`/`outlier_pct`/`has_significant_outliers` for downstream agents.
84. **Does Agent 1 output anything about Excel sheet metadata?**
    Yes — `sheet_used` and `all_sheets` are surfaced in `raw_profile`, plus a warning if multi-sheet concatenation had a schema mismatch.
85. **What happens if the file can't be loaded at all?**
    The exception is caught, an `"Agent1: File load failed — ..."` error is appended, confidence is reported as 0.0 with `decision_readiness="blocked"`, and the pipeline's conditional edge routes straight to `END`.
86. **What are `raw_profile` and `_df_cache` used for downstream?**
    `raw_profile` is consumed by Agent 2's LLM prompt builder and its heuristic type sniffer; `_df_cache` is the actual DataFrame Agent 2/3/5 operate on without re-reading the file.
87. **Why cache the DataFrame in state instead of re-reading the file in every agent?**
    Performance (avoid repeated disk I/O and re-parsing) and consistency (every agent sees exactly the same in-memory frame Agent 1 produced, not a possibly-different re-parse).
88. **How many sample values does Agent 1 keep per column, and why exactly that many?**
    3 — enough to signal format/content to a human or an LLM prompt without inflating cost or exposing excessive raw data.
89. **Is Agent 1's profiling adaptive to dataset size (e.g. sampling for huge files)?**
    No — it profiles the full DataFrame as loaded; there's no chunked/sampled ingestion yet (explicitly listed as a future scalability item).
90. **What would you say if asked "why not also detect PII in Agent 1"?**
    That's a reasonable extension but out of current scope; Agent 1 focuses on structural/statistical profiling, not privacy classification — a good future-work answer.
91. **Why is `duplicate_rows` computed here and re-verified in Agent 3?**
    Agent 1's count is the ground truth for a consistency assertion in Agent 3's `dedup_exact_rows` — if the actual duplicate count found in Agent 3 disagrees with Agent 1's, the pipeline treats that mismatch as a likely bug and halts rather than silently proceeding.
92. **What if a numeric column has fewer than 4 non-null values — does outlier analysis still run?**
    No — it needs at least 4 values for a meaningful IQR; below that it reports `outlier_count=0`/`has_significant_outliers=False` rather than computing unstable quartiles on too little data.
93. **What if a text column is entirely empty (all null)?**
    `_analyze_parseability` returns `datetime_pct=0.0` immediately (empty `values` after `dropna()`), avoiding a division-by-zero.
94. **How is a "duplicate rate" computed?**
    `duplicated_rows / total_rows × 100`, using pandas' default `.duplicated()` (marks all but the first occurrence of an exact-match row).
95. **Would Agent 1 catch two columns that are duplicates of each other but with different names?**
    Yes — `_detect_column_relationships`'s `suspicious_duplicates` check compares column *values* pairwise with `.equals()`, independent of column naming.

---

## D. Agent 2 — Semantic Tagger (45)

96. **What's Agent 2's job in one sentence?**
    Decide what each column *means* semantically (currency, identifier, datetime, percentage, categorical, geographic, text, physical measurement, or unknown) and derive processing rules from that meaning.
97. **What two signal sources does Agent 2 combine?**
    A cheap, LLM-free pure-Python type sniffer (`_infer_intended_types`), and an LLM-generated semantic schema blueprint — reconciled/overridden by deterministic guardrails afterward.
98. **How does the local type sniffer decide "numeric" for a string column?**
    If ≥80% of non-null values successfully coerce to a number via `pd.to_numeric(errors="coerce")`.
99. **How does the local type sniffer decide "datetime"?**
    If ≥80% of non-null values parse as dates via `pd.to_datetime(..., format="mixed", errors="coerce")` — same threshold and function pattern as Agent 1's parseability check.
100. **What does the LLM actually receive as input?**
    Per column: name, the heuristically inferred type, missing-rate %, unique count, up to 3 sample values, distribution type/skewness/normality flag, outlier %, and top strong numeric-correlation partners — never the full dataset.
101. **Why send only metadata + 3 samples, not full rows?**
    Cost control (smaller prompts = cheaper/faster calls) and a privacy-by-design choice — the LLM never needs to see the bulk of the actual customer/business data to classify a column's *type of meaning*.
102. **What model is called, and with what generation settings?**
    Groq's `qwen/qwen3.6-27b`, `temperature=0.1`, `reasoning_effort="none"`, `max_tokens=2000`.
103. **Why `temperature=0.1` and not 0 or 1?**
    Near-zero makes the output distribution sharply peaked (near-deterministic token choice) — needed because the response must be strictly parseable JSON, but a hard `0` isn't meaningfully different and 0.1 is the conventional "almost deterministic" choice.
104. **Why `reasoning_effort="none"`?**
    Verified empirically: with reasoning enabled the model emits a `<think>...</think>` block that either breaks the strict-JSON parser or wastes tokens; disabling it returns clean JSON directly.
105. **What happens if the JSON response is malformed?**
    `_loads_lenient` first retries after stripping trailing commas (a common LLM slip); if that still fails, and there are ≥2 columns in the batch, the request is recursively halved and retried (`_call_llm_for_schema_blueprint_with_retry`) so one malformed field doesn't discard the whole batch's tagging.
106. **What's the full LLM failover chain?**
    Groq (2 retries on transient errors, 3s backoff) → Gemini (multi-key rotation, model-fallback chain `gemini-flash-latest → gemini-3.6-flash → gemini-3.5-flash`) → deterministic `_fallback_blueprint` heuristic.
107. **What counts as a "transient" Groq error worth retrying?**
    `RateLimitError`, `APIConnectionError`, `APITimeoutError`, `InternalServerError` (5xx) — a genuine bad-request/auth error is not retried, it fails straight to Gemini.
108. **How does multi-key Gemini rotation work?**
    Multiple keys can be configured (`GEMINI_API_KEYS`, or numbered `GEMINI_API_KEY_1..5`); calls rotate through them starting from a module-level rotation index, so load is spread and one exhausted key doesn't block all requests.
109. **What does `_fallback_blueprint` produce?**
    A conservative schema using only the locally-sniffed type (numeric/datetime/string/boolean), `semantic_tag="unknown"`, no scaling/imputation beyond `"none"`/`flag_only`, explicitly noting `"fallback — LLM call failed"`.
110. **Why does the fallback deliberately avoid hardcoding `encoding_strategy`?**
    So the later, cardinality-aware `_derive_encoding_strategy` step fills it in properly — a documented past bug had every fallback "string" column one-hot-encoded regardless of cardinality, exploding column counts on high-cardinality/date-like text.
111. **What is the on-disk schema cache and why does it exist?**
    Hashes the exact LLM prompt payload (dataset content + model + batch size + system prompt) with SHA-256; if an identical hash was seen before, the cached blueprint is reused and **zero** LLM calls are made — pure cost optimization for repeated runs on an unchanged file.
112. **When does Agent 2 batch its LLM calls instead of one call for everything?**
    When the schema has more than `LLM_SINGLE_CALL_THRESHOLD=15` columns, it splits into batches of `LLM_BATCH_SIZE=10` columns each.
113. **What is `financial_role` and why is it computed independently of the LLM?**
    A deterministic classification (`_derive_financial_role`) of *whose* money a currency column represents (revenue / cost / tax / discount / budget / price / spend / customer_income) purely from column-name tokens — runs for both the LLM and fallback paths so the revenue-vs-income distinction always exists even if the model is unavailable or slightly wrong in its notes.
114. **Why does this distinction (revenue vs. income) matter so much?**
    A customer/personal attribute like "Income" being silently treated as "company Revenue" would corrupt every downstream business metric (profit, margin) derived from "revenue" — this is a documented, deliberately-guarded failure mode.
115. **What is `_calculate_semantic_confidence` and what factors feed it?**
    A per-column 0–100 score (name-match, type-alignment, format-hint corroboration, cardinality signals, missingness/outlier penalties) that independently grades how well-supported the assigned semantic tag is — it is not something the LLM reports about itself.
116. **What are the confidence level bands?**
    `≥80` high, `≥60` medium, `<60` low.
117. **What is `column_assessment` / "is_suitable"?**
    A per-column verdict (`_assess_column_suitability`) on whether the column is fit for downstream analysis at all, based on missing-rate and duplicate-pressure thresholds that vary by semantic tag (identifiers strictest, since a missing key breaks row identity).
118. **What is `null_policy` and how does it differ from `imputation_strategy`?**
    `null_policy` is a structured `{action, threshold_pct, reason}` record (the "why"); `imputation_strategy` is the short string Agent 3 actually branches on (`mean`/`median`/`mode`/…) — `_imputation_strategy_from_null_policy_action` keeps the two consistent.
119. **When is the model's own `null_policy`/`imputation_strategy` overridden regardless of what it said?**
    For "guardrail tags": `identifier`, `currency`, `financial`, `datetime` — the deterministic rule always wins there, so currency/financial columns can never end up mean/median/mode-imputed even if the LLM suggested it.
120. **Why is imputation of currency/financial columns forbidden entirely?**
    Inventing a plausible-looking dollar figure for a missing transaction amount could materially mislead a financial report; the policy is to flag it for human review (`flag_only`) instead of guessing.
121. **How are percentage columns' scale (0–1 vs 0–100) determined?**
    Auto-detected: if the 95th percentile of the column's numeric values is ≤1.0, it's treated as a `ratio` [0,1]; otherwise `percent` [0,100].
122. **What's an example of a rule that depends on correlation strength, not just missingness?**
    Numeric/percentage/count columns with ≥2 correlated partners at `|r|≥0.9` and 10–35% missing get `impute_iterative` (MICE-style); at `|r|≥0.85` and 10–30% missing they get `impute_knn` instead of a simple median fill.
123. **What encoding strategies exist and when is each chosen?**
    `one_hot` for nominal categories ≤20 unique values, `ordinal` only with a genuine, explicitly supplied order list, `none` for identifiers/datetimes/free text/booleans/high-cardinality labels.
124. **Can the LLM introduce an invalid ordinal order (e.g. inferred from alphabetical order)?**
    The system prompt explicitly forbids inferring ordinal order from alphabetical order and requires "a complete explicit order list" — `_derive_encoding_strategy` also only accepts an ordinal method if a non-empty `order` list is actually present, otherwise it falls back.
125. **What is `SchemaBlueprint` (the dict subclass)?**
    A `dict` subclass whose `__len__` excludes the internal `"__metadata__"` key, so "how many columns were tagged" reporting (`len(schema_blueprint)`) doesn't accidentally count the metadata block as a column.
126. **What lives in `schema_blueprint["__metadata__"]`?**
    Dataset-level signals: the overall data-quality risk assessment, the recommended preprocessing profile, the LLM tagging source (`"llm"` vs `"fallback"`) and error (if any), plus (added later by Agent 3) derived-metric source mappings and canonical-derived-metric replacements.
127. **What does "tagging_source" tell you and why report it to the frontend?**
    Whether the schema came from a real LLM call or the heuristic fallback — surfaced so a job whose tagging silently degraded doesn't look identical to a normal AI-tagged run to the end user.
128. **How does `_assess_data_quality_signals` classify overall dataset risk?**
    A rule ladder using missing-rate %, duplicate-rate %, and count of implicit-missingness/outlier-flagged columns: `critical` (≥30% missing or ≥8% dup or ≥4 implicit-null columns) → `high` → `moderate` → `low`, each mapping to a recommended preprocessing profile.
129. **Why does column-level LLM tagging use whole-word keyword matching for name hints, not substring matching?**
    Prevents false positives like "count" matching inside "Country" — a documented lesson learned and reused pattern (`_name_tokens` splits on non-alphanumerics into whole tokens before set-intersection).
130. **What are the 12 classification rule categories in the system prompt?**
    Currency, identifier, datetime, percentage, count, low-cardinality categorical, geographic, free text, physical measurement, plus general "use samples with types," "be conservative," and unknown/ambiguous handling.
131. **What's the fallback when the model returns *valid* JSON but for the wrong columns (a batch mismatch)?**
    `_merge_schema_blueprints` merges by matching column-name keys; unmatched entries just get added, and a `.update()` on an existing entry means later batches can enrich earlier ones without full replacement.
132. **What if the LLM's response includes extra/dataset-level keys the prompt forbade?**
    The system prompt explicitly instructs "Do not add columns, dataset-level metadata, or a `__metadata__` key" — the code doesn't currently strip stray extra keys defensively beyond that instruction, so this is enforced by prompting, not a post-parse filter (a fair thing to note if pressed on robustness).
133. **Why is `_infer_semantic_tag_from_metadata` (the fallback tagger) not just a simple lookup table?**
    It layers multiple signal types (parseability, format hints, candidate-key score, cardinality ratio, name tokens, sample content) in a priority order — datetime signals checked first, then currency/percentage/count numeric signals, then identifier signals, then name-hint keywords, then cardinality-based categorical/text distinction.
134. **How does the fallback tagger distinguish "categorical_label" from "text"?**
    By cardinality: unique count < 20 or cardinality ratio ≤ 0.2 → categorical; if it's high-cardinality *and* looks near-unique (candidate-key score ≥0.9 or cardinality ratio ≥0.8) → text.
135. **What happens to a column both Agent 1 flagged as high-missingness (>20%) and Agent 2 wants to analyze?**
    `MISSINGNESS_ANALYSIS_THRESHOLD_PCT=20.0` — it gets `analysis_allowed=False`, is excluded from downstream statistics, and a note is appended to its `notes` field explaining why.
136. **Does `analysis_allowed=False` mean the column is dropped from the DataFrame?**
    Not necessarily immediately — it's excluded from *analysis* (Agent 4's numeric/categorical column selectors check this flag), though it may still physically exist in `cleaned_df` unless a separate drop rule (e.g. `drop_column` null policy) removes it.
137. **What's the role of `_column_correlation_summary`?**
    Surfaces, per column, its strongest numeric correlation partners (from Agent 1's `column_relationships`) — fed into both the LLM prompt (context for tagging) and the deterministic null-policy logic (to justify KNN/iterative imputation choices).
138. **Is Agent 2's LLM call rate-limited or cost-bounded in any other way besides batching?**
    Yes — the on-disk schema cache means an unchanged dataset triggers zero repeat calls, and the minimal-metadata prompt (not full rows) bounds prompt size regardless of dataset row count.
139. **What if two Gemini models both 404 ("model retired")?**
    `_is_model_unavailable_error` detects 404/"not_found"/"no longer available" text and moves to the *next model* in the fallback chain for the *same* set of keys, rather than giving up after the first model fails.
140. **How are API keys never leaked in logs?**
    Every logged/recorded key reference goes through `mask_key`/`_mask_gemini_key`, which stores only a 10-character SHA-256 prefix fingerprint — the actual key value is never printed or persisted anywhere in usage records.

---

## E. Agent 3 — Preprocessor (55)

141. **What's Agent 3's contract?**
    Take `_df_cache` + `schema_blueprint`, apply a deterministic ~13-step cleaning/transformation pipeline, and return `cleaned_df` plus a complete audit trail.
142. **Does Agent 3 call any LLM?**
    No — entirely deterministic pandas/numpy/scikit-learn.
143. **What's the very first step and why does it run before anything else?**
    Exact-row deduplication, with a consistency assertion against Agent 1's own duplicate count — catching a mismatch here as early as possible flags a likely upstream bug before any transformation compounds the problem.
144. **What happens if the actual duplicate count disagrees with Agent 1's expected count?**
    `dedup_exact_rows` raises a `ValueError` with both counts and sample duplicate signatures; Agent 3 halts via `_early_exit_with_error` rather than silently proceeding with an inconsistent dataset.
145. **How is currency text normalized (`_normalize_currency_text`)?**
    Strips symbols (₹ $ € £ ¥ ₩), converts `(123)` accounting-style negatives to `-123`, strips `Rs.`/currency codes (USD/EUR/INR/etc.), then disambiguates thousands vs. decimal separators by comparing the position of the last `,` vs last `.`.
146. **How does the code tell European `1.234,56` from US `1,234.56`?**
    Whichever of the last `,` or last `.` appears *later* in the string is treated as the decimal separator; the other becomes the thousands separator to be stripped.
147. **What's the "critical currency plausibility assertion"?**
    If a currency column parses to 100% null, or its max absolute value exceeds the profile's `currency_max_abs_value` cap, the pipeline halts immediately as a likely parsing bug rather than continuing silently.
148. **Why `format="mixed"` for datetime parsing specifically?**
    Without it, `pd.to_datetime` locks onto the first row's date format and converts every other differently-formatted row to `NaT`; `format="mixed"` parses each value against its own format.
149. **What's the fuzzy category-merge algorithm, step by step?**
    Case/separator-fold first (`_canonicalize_text_values`), then a from-scratch Levenshtein-distance clustering (`_build_canonical_category_map`) on the remaining distinct labels, gated by minimum length, max edit distance, matching first letter, and rarity of the merged-away value.
150. **Why implement Levenshtein distance from scratch instead of using a library?**
    Keeps the dependency footprint small for a simple, well-understood O(len(a)×len(b)) dynamic-programming algorithm the codebase already needs in exactly one place.
151. **Give a concrete example the fuzzy merge is designed to catch.**
    `"Complete"` vs `"Completed"`, `"Cancelled"` vs `"Canceled"`, `"Bank Transfer"` vs `"Banktransfer"`.
152. **Give a concrete example the fuzzy merge is designed to reject.**
    `"North"`/`"South"` (edit distance 2, but different first letters and geographically opposite meanings) and `"Houston"`/`"Boston"` (edit distance 2, both 6+ chars, but genuinely different city names — caught by the first-letter guard).
153. **Why require the labels to share a first letter?**
    Real spelling variants/typos of the same word essentially never change the leading character; this single rule eliminates a whole class of false-positive merges without excluding any of the verified legitimate ones.
154. **Why is fuzzy matching skipped for columns with ≤3 distinct values?**
    Too few categories for "near-duplicate spelling" to be a meaningful concept — they're more likely to be genuinely distinct short labels (`LOW_CARDINALITY_MAX=3`).
155. **Why is fuzzy matching skipped above 500 distinct labels?**
    Pairwise comparison is O(n²) and stops being meaningful for product-name-like high-cardinality fields — cost without benefit past `FUZZY_MAX_CATEGORY_LABELS=500`.
156. **Is fuzzy matching applied to geographic columns like Country?**
    No — explicitly disabled for columns tagged `geographic` or matching geographic name tokens (country/state/province), because that's a closed, well-defined vocabulary where a "typo" merge risk (e.g. merging two real but similar-sounding places) is higher-stakes.
157. **What happens to labels that are *almost* mergeable but fail the length gate?**
    They're left unmapped but explicitly flagged in the preprocessing log for manual review, rather than silently guessed at either way.
158. **Why re-run deduplication *after* fuzzy canonicalization?**
    Merging "Complete"/"Completed" into one label can make two previously-distinct rows become exact duplicates of each other — a second dedup pass catches those newly-created duplicates.
159. **How are business metrics like profit and margin derived?**
    Column-pair detection using Agent 2's explicit `financial_role` tags first (never name-keyword guessing alone), e.g. `derived_profit = revenue_col − cost_col`, `derived_profit_margin_pct = derived_profit / revenue_col × 100`.
160. **What if there's no true revenue column at all (e.g. a marketing dataset with per-category spend columns)?**
    A `derived_total_spend` proxy is computed as the sum of columns tagged `financial_role="spend"` (e.g. `MntWines`, `MntFruits`) — explicitly chosen over misusing a customer attribute like `Income` as a stand-in for revenue.
161. **What is "ground-truth reconciliation" for derived metrics?**
    If a derived metric's name-token concept (e.g. `{profit, margin}`) fully matches an existing raw column's tokens, the two are checked for agreement (`Pearson r ≥ 0.99`, MAPE ≤ 1%); a mismatch is flagged as a likely wrong derivation formula or wrong source-column resolution.
162. **What happens when a derived metric is redundant with an existing column (agrees closely)?**
    It's dropped from the DataFrame entirely (`_find_redundant_derived_metrics` / removal step), and the derivation map is rewritten so any metric that depended on the redundant derived column now points at the canonical raw column instead.
163. **What's `_detect_raw_formula_relationships` for?**
    Detects, among purely raw (non-derived) columns, whether an exact `profit = revenue − cost` identity already holds — recorded as metadata so Agent 4's correlation analysis can treat that pair as "formulaic" (algebra, not a discovery) rather than a business insight.
164. **What preprocessing profiles exist and how are they chosen?**
    `strict` / `balanced` / `lenient`; auto-selected via `_detect_dataset_domain` (finance-keyword/tag heuristic → `strict` for `finance_sales`, else `balanced`), or explicitly overridden by the caller.
165. **What differs across the three profiles?**
    Currency plausibility ceiling, max reasonable tax rate, reconciliation tolerance (relative & absolute), and the quality-score component weights.
166. **How is a dataset classified as "finance_sales"?**
    ≥3 column names containing finance keywords (amount/revenue/cost/tax/price/discount/sales/profit/margin/invoice) OR ≥2 columns tagged `currency`/`percentage` by Agent 2.
167. **How does imputation choose between mean, median, mode, KNN, and iterative?**
    Driven by `null_policy.action` set in Agent 2 (semantic tag × missingness % × distribution shape × correlation strength), with currency/financial columns hard-blocked from any fill regardless of what the policy says (defence-in-depth).
168. **What is KNN imputation here and what's `k`?**
    `sklearn.impute.KNNImputer` over the eligible numeric columns (excluding identifier/datetime/currency/financial), with `n_neighbors` defaulting to 5, clamped to at most `n_rows − 1`.
169. **What is "iterative" imputation here?**
    `sklearn.impute.IterativeImputer` (a MICE-style multivariate imputer), `random_state=0`, `max_iter=10`, `initial_strategy="median"`.
170. **Why exclude identifier/datetime/currency/financial columns from the multivariate imputation frame?**
    Those columns either shouldn't be imputed at all (identifiers, currency) or aren't meaningful numeric predictors for KNN/iterative distance calculations (datetime).
171. **What does the "column ledger" track?**
    Per-column: the action taken (currency_clean/coerce/text_standardize/outlier_clip/scale/date_parse), before/after null %, parse-failure %, range-failure %, plus clip bounds and post-clip actual min/max — a full per-column audit trail.
172. **What is `row_accounting` and why is it a separate structure?**
    Tracks input rows, exact duplicates removed, rows after canonical dedup, and rows dropped by imputation — gives Agent 5 an independent ground truth to reconcile against the final `cleaned_df` row count.
173. **How does one-hot encoding scale with cardinality?**
    ≤10 unique values → full one-hot; >10 → top-8 most frequent categories + a single "Other" bucket, so column count doesn't explode on high-cardinality fields.
174. **What's the "near-unique" safety net in encoding?**
    If a column's cardinality is >50% of row count *and* above the low-cardinality threshold, one-hot/top-N encoding is skipped entirely — it's very likely a mistagged identifier/date, and the "Other" bucket would be meaningless.
175. **How is adaptive outlier clipping "adaptive"?**
    Defaults to the standard IQR ×1.5 fence, but switches to percentile clipping (1–99% / 5–95% / 2.5–97.5%, based on assessed risk tier) *only when Agent 1's own distribution analysis shows real skew/outliers* — never triggered by semantic tag alone.
176. **What bug did the "evidence-gated" percentile clipping fix?**
    Previously, percentage/count columns were *always* percentile-clipped regardless of whether they had real outliers, manufacturing a fake ~5% "outlier rate" purely by construction on perfectly clean data.
177. **Why are currency/financial/datetime/identifier columns hard-excluded from clipping?**
    A legitimate large transaction shouldn't be artificially capped (that would distort real business figures), and datetime/identifier values aren't meaningfully "outliers" in the statistical sense being targeted.
178. **What is preserved when a column is clipped?**
    A `<col>_raw` backup column (uncapped original values) and a boolean `<col>_was_clipped` flag — nothing is destroyed, and the clip is fully reversible/auditable.
179. **What scaling method is used and why?**
    Min-Max normalization to [0,1], because the report needs real-unit numbers later and min-max is trivially invertible with the saved `{min, max}` — unlike z-score standardization, which would need the same reconstruction machinery for no added benefit here.
180. **What is `scaling_params` used for downstream?**
    Agent 4's `_restore_scaled_columns` inverse-transforms every scaled column back to real units (`value × (max−min) + min`) before computing any statistic or chart.
181. **What date features are extracted?**
    year, month, quarter, day, day_of_week, is_weekend, week_of_year — from every column tagged `datetime`.
182. **What is the "row survival floor" and when does it trigger?**
    `_assert_row_survival_or_abort` — if fewer than 50% of input rows survive any single step (dedup, canonical dedup, or imputation-driven row drops), the pipeline halts with an explicit error, treating a >50% loss as almost certainly a bug rather than legitimate cleaning.
183. **How is the overall data-quality score computed?**
    A weighted combination of completeness (1 − missing%), consistency (1 − validation-failure%), and deduplication (1 − duplicate-rate%) — weights vary per preprocessing profile, plus a small penalty if the dataset's risk tier is `high`/`critical`.
184. **Is the Agent-3 quality score final?**
    No — Agent 4 applies a further adjustment (`_apply_anomaly_quality_penalty`) after anomaly/structural-issue detection, so the *final* score reflects both cleaning quality and analysis-time findings.
185. **What business-rule validations does Agent 3 run?**
    Count-range checks (no negative/non-integer counts) and financial-constraint checks (tax-rate sanity vs. amount, `total ≈ amount+tax−discount` reconciliation, profit-margin bounds) — each producing a per-row boolean flag column.
186. **Why produce a boolean flag column instead of just dropping bad rows?**
    Preserves every row for full auditability and lets the end user/report decide what to do with flagged rows, rather than silently discarding potentially-important data.
187. **What's `_resolve_business_keys` used for?**
    Determines which column(s) define row identity for deduplication — prefers columns Agent 2 tagged `is_identifier=True`, falling back to a priority list of common key-name patterns (`transaction_id`, `order_id`, etc.) if none were tagged.
188. **Why is the sample dataset's cleaned shape 58 columns from an original 14?**
    One-hot encoding of Region/Item Type/Sales Channel, ordinal encoding of Order Priority, date-feature extraction on two date columns, plus derived business metrics and audit columns (`_raw`, `_scaled`, `_was_clipped`, parse/range-failure flags) all add columns.
189. **What happens if a schema-blueprint column no longer exists in the DataFrame (e.g. it was dropped earlier)?**
    Every transformation step checks `if col not in df.columns: continue` — steps are individually skip-safe rather than assuming every blueprint column is still present.
190. **How does verbose logging work, and is it on by default?**
    Controlled by the `PIPELINE_VERBOSE` environment variable (`1/true/yes/on`); off by default, so normal runs only print milestone summaries, not every intermediate step.
191. **What gets exported to disk at the end of Agent 3?**
    The cleaned DataFrame to `outputs/cleaned_data.csv` (or a run-scoped path), independent of what the API layer separately does with `cleaned_df` in memory.
192. **Does Agent 3 ever silently swallow an exception?**
    Individual steps wrap risky operations in try/except and record a note (e.g. "coercion failed - {e}") rather than crashing the whole pipeline on one column's failure — but the three "critical assertion" checks (currency parse, currency plausibility, clip-bounds violation) are intentionally *not* swallowed, they halt the pipeline.
193. **What is `_log_null_diff` for?**
    A debugging/regression-detection helper that reports per-column null-count deltas after each step, so an unexpected increase in nulls (a red flag for a bug) is visible in the preprocessing log immediately.
194. **How would you explain "why 58 columns isn't a red flag" to an examiner who thinks the dataset ballooned unnecessarily?**
    Every added column is either (a) a standard encoding artifact needed for any downstream numeric ML/statistics use, (b) an audit/reversibility column (`_raw`, `_was_clipped`), or (c) a genuinely new business metric — none of it is noise, and the report itself narrates from a curated subset, not all 58 raw columns.
195. **What's the difference between `dropped_by_imputation` and simply excluding a column from analysis?**
    `dropped_by_imputation=True` (set by `_mark_column_dropped`) means the column was physically removed from `cleaned_df` because its missingness exceeded the drop threshold; `analysis_allowed=False` alone means the column still exists but is skipped by Agent 4's selectors.

---

## F. Agent 4 — Statistical Analysis & Charts (55)

196. **What's Agent 4's contract?**
    Take `cleaned_df` + `schema_blueprint`, compute a large `stats` dict and generate/select chart images, with zero LLM calls.
197. **What's the very first thing Agent 4 does to the data and why?**
    `_restore_scaled_columns` inverse-transforms every min-max-scaled column back to real units — every statistic and chart must show human-readable numbers, not squashed 0..1 values.
198. **What is `_build_chart_plan` and why does it exist?**
    Classifies the dataset's shape (sales_timeseries / sales_categorical / time_series / mixed_analytics / numeric_table / categorical_table / general_table) from what columns actually exist, then only enables chart "families" that are structurally possible — this is what makes the report dataset-specific rather than templated.
199. **What descriptive statistics are computed?**
    count, mean, median, std, variance, min, max, Q1, Q3, skewness, excess kurtosis — per eligible numeric column.
200. **What two correlation methods are computed and why both?**
    Pearson (linear relationships) and Spearman (monotonic, rank-based relationships) — Spearman catches non-linear-but-monotonic relationships Pearson would understate.
201. **What counts as a "strong" vs. "moderate" correlation here?**
    `|r| ≥ 0.7` strong, `|r| ≥ 0.5` moderate (below 0.5 isn't reported as a "strong pair" at all).
202. **What is "leakage detection" in the correlation step?**
    `flag_leakage_columns` flags likely ID/model-output/leakage columns via name patterns (classifier/_score/_proba/predicted_/id/index), near-perfect correlation with exactly one other column and near-zero with everything else, or pure-identifier cardinality — these are excluded from headline "Top Correlations."
203. **Why exclude "formulaic pairs" from correlation findings?**
    A derived metric correlating ~1.0 with its own source column (e.g. `derived_profit` vs. `Revenue`) isn't a discovery, it's algebra — tracked via Agent 3's explicit derivation map, not a correlation-value cutoff, so it also catches *indirect* identities (e.g. `revenue_per_unit` being exactly `unit_price` through an intermediate formula).
204. **What's a "near-perfect correlation" and why is it flagged separately?**
    `|r| > 0.98` — flagged as a possible data-quality artifact (duplicated/derived columns) rather than presented as a genuine, interesting business relationship.
205. **When is the correlation heatmap actually drawn?**
    Only if the strongest pair reaches `CORRELATION_HEATMAP_MIN_R = 0.3` — a wall of near-zero correlation cells is noise, not insight, so it's skipped entirely below that bar.
206. **How are Month-over-Month / Quarter-over-Quarter growth rates computed?**
    Group the primary revenue metric by year+month (or year+quarter), sum, then `.pct_change() × 100` on the resulting series.
207. **What happens once there are more than 40 time periods to chart?**
    The **chart** (not the underlying stats, which stay full-fidelity) rolls up to a coarser grain (e.g. monthly → yearly) so a multi-decade dataset doesn't produce an illegible hundred-bar chart.
208. **What's `_has_meaningful_variation` and why does it exist?**
    A coefficient-of-variation check (std/mean ≥ 0.03) that guards against drawing a time-series/trend chart for data that's essentially flat — a flat line chart isn't a meaningful insight, it's noise.
209. **How are top/bottom-N rankings selected across categorical dimensions?**
    `_select_ranking_dimensions` always gives business-priority dimensions (region/category/segment/representative, matched by keyword) a ranking slot if they pass a basic cardinality sanity check (2–20 unique values), then fills remaining slots (up to `MAX_RANKING_DIMENSIONS=6`) with whichever other columns show the most metric-differentiated spread.
210. **Why was the priority-dimension logic added (what bug did it fix)?**
    Previously, Region/Category/Segment-style columns could lose the "most differentiated" ranking race against noisier columns like Customer_City or Product_Name and never get a ranking slot at all, even though they're the business-priority dimensions a reader actually cares about.
211. **How does seasonality detection work?**
    Groups the revenue metric by month (or quarter) and averages, then identifies the best/worst period by that average — charted as a line (monthly) or bar (quarterly) if there's meaningful variation.
212. **What's the anomaly detection method and why "skew-aware"?**
    Plain z-score (|z| > 3.5) for roughly-symmetric numeric columns; a log-transformed z-score for positive right-skewed columns; a wide IQR ×3.0 "far-out" fence for anything skewed and not strictly positive — because a flat z-rule either misses anomalies or badly over-flags a legitimate long tail on skewed data.
213. **Why z=3.5 instead of the "textbook" z=3?**
    A slightly wider, still-conventional threshold chosen to reduce false positives on business data where merely-large-but-legitimate transactions would otherwise be flagged too often at z=3.
214. **Why IQR ×3.0 for anomaly *flagging* but ×1.5 for outlier *clipping* in Agent 3?**
    An audit found the 1.5× rule flags ~24% of rows on a real right-skewed column — too noisy to *report as anomalies* to a user, even though 1.5× is fine for silently *clipping* extreme values during cleaning. 3.0 is Tukey's "far-out" fence, reserved for genuinely rare, worth-surfacing extremes.
215. **What's the difference between a "statistical anomaly" and a "structural data-quality issue"?**
    A statistical outlier (e.g. one very large but legitimate transaction) isn't a defect; a structural violation (negative quantity, discount >100%, a broken total reconciliation) is a genuine data-quality problem — they're detected and penalized separately so legitimate long-tail values aren't punished like real defects.
216. **How much does each type penalize the final quality score?**
    Statistical outliers: scale 0.1, cap 5.0, with a 3% tolerance band that costs nothing. Structural issues: scale 1.5, cap 40.0 — structural defects dominate the penalty by design.
217. **What structural rules does Agent 4 check beyond Agent 3's own flags?**
    Negative-count fields not already flagged by Agent 3, percentage/discount fields out of auto-detected bounds, and returns exceeding order quantity or negative returns.
218. **How are numeric-column bounds (0–1 vs 0–100) auto-detected for validation, separately from Agent 2's `unit_scale`?**
    `_auto_detect_bounds`: if >95% of values fall in [0,1] → ratio bounds; if >95% fall in [0,100] → percent bounds; otherwise no bounds check applies (arbitrary-range columns like revenue aren't bounds-checked at all).
219. **What is `BROKEN_RULE_FIRE_RATE_PCT = 95.0` for?**
    If a structural rule fires on more than 95% of rows, that's stronger evidence the *rule itself* is misconfigured for this particular dataset than that 95% of the data is genuinely broken — such rules are filtered out rather than shown as an alarming but probably-wrong finding.
220. **What is `STRUCTURAL_RULE_REVIEW_PCT = 90.0` for?**
    A rule firing on >90% (but ≤95%) of rows is flagged as needing human review, distinct from being outright filtered as broken.
221. **How is regression/trend analysis done?**
    OLS linear regression (`scipy.stats.linregress`) of each eligible numeric column against a monotonic time index (built from year×12+month when available, else row order).
222. **Why exclude date-derived columns (`_year`, `_month`, etc.) from regression?**
    They're trivially/mechanically correlated with the time axis itself — regressing them would just recover the time index, not a real trend, and would self-regress to r²=1.0 if not excluded.
223. **When is a trend actually charted?**
    Only when `p_value < 0.05` (statistically significant) — a regression line fit to noise (p≥0.05) would mislead readers into seeing a trend that isn't real.
224. **Why did the sample run report zero significant trends out of 8 candidates?**
    None of the 8 candidate trends met both the p<0.05 significance bar and (independently, via Agent 5) the minimum sample-size bar on that particular dataset/time window — a correctly conservative "no trend to report" outcome, not a failure.
225. **What's the "distribution charts" family?**
    Box plots and histograms for up to 6 key numeric columns, showing spread and shape.
226. **What are the cross-dimensional analysis families and what gates each one?**
    Discount-vs-return-rate (needs a discount + a returned/boolean column), category-margin-over-time (margin + category + month columns), rep-discount-margin (rep + discount + margin columns), segment-order-value (segment + revenue), region-shipping-cost (shipping + region), shipping-lead-time (a derived days-to-ship metric) — each only runs if its required columns actually exist.
227. **What is `chart_planner.py`'s scoring approach and why is it "dataset-agnostic"?**
    Scores every candidate chart by a statistical effect-size metric appropriate to its type — ANOVA η² for category-vs-metric ranking charts, Pareto concentration (0.6×top1 + 0.4×top3 share) for concentration charts, r² for trend charts, Cramér's V for categorical-categorical crosstabs — so the *same code* surfaces different, relevant charts on a sales dataset vs. an HR dataset vs. a support-ticket dataset, without keyword-matching a specific domain.
228. **How is the final chart list capped, and is anything actually deleted?**
    All candidates across every family are pooled, ranked by their informativeness score, and only the top `MAX_CHARTS_PER_REPORT=16` are kept — dropped PNG files are genuinely deleted from disk (`os.remove`), not just hidden from the report.
229. **Why cap total charts at all — isn't more information always better?**
    A wide dataset can produce dozens of charts of wildly uneven value; without a cap, a near-uniform, uninteresting bar chart would sit next to a genuinely strong correlation heatmap and bury it — capping by score keeps the report focused.
230. **What guarantees are enforced on every saved chart PNG regardless of content?**
    Hard dimension cap (1600px per side at up to 150 DPI), axis-tick-label thinning beyond 18 labels (rotated beyond 8), so a chart with hundreds of categories/periods never renders as illegible overlapping text.
231. **What is a `ChartSpec` and why unify legacy and planner charts into one shape?**
    A dict contract (title, plain-language explanation, alt text, annotations, pre-aggregated data) consumed identically by the interactive ECharts frontend and the static matplotlib/report renderer — unifying lets both older, hand-coded chart families and the newer scored planner compete fairly in one ranked, capped gallery.
232. **What does `_find_revenue_col` actually search for, in priority order?**
    (1) A column Agent 2 explicitly tagged `financial_role="revenue"` with real variation; (2) a `derived_total_spend` proxy; (3) whole-word keyword match on common revenue/sales names — deliberately never matching "income" as a revenue synonym.
233. **Why does `_find_revenue_col` require "meaningful variation," not just a name/tag match?**
    A flat/constant "revenue" column (a known quirk in some public datasets — a placeholder field) isn't a usable business metric even if its name or tag matches; skipping it in favor of the next candidate tier avoids building an entire chart section around a column that's secretly all zeros or a single value.
234. **How does the code decide a chart title should say "Total Spend" instead of always "Revenue"?**
    `_revenue_label` derives the human label from whatever column `_find_revenue_col` actually resolved to, so a chart is never captioned "Revenue" when the underlying column is actually "Income" or a spend proxy — this was a documented fix for a mismatch between honest column titles and dishonest captions.
235. **What is `_impact_columns` used for in anomaly detection?**
    Identifies "impact" columns (name tokens like revenue/sales/amount/total/value/price) so each flagged anomalous row's *business impact* (a dollar-figure estimate) can be reported, not just a raw count of outliers.
236. **How is a column's identifier/leakage flag from Agent 4 different from Agent 2's `is_identifier`?**
    It's an independent, code-level safety net (`flag_leakage_columns`) that runs specifically on the correlation matrix and catches columns the schema blueprint mistagged or never saw (e.g. an external model's score/probability column baked into the raw file) — belt-and-suspenders against upstream tagging misses.
237. **Why does Agent 4 use its own `_numeric_cols`/`_categorical_cols` selectors instead of just checking pandas dtypes?**
    They additionally exclude validation-suffix columns (`_parse_failed`, `_range_failed`), backup columns (`_raw`, `_scaled`, `_was_clipped`), identifiers, datetimes, and analysis-disallowed columns — a plain dtype check would pull in audit/plumbing columns that were never meant to be "real" analysis variables.
238. **What pandas-version-specific bug does the categorical-column selector guard against?**
    In pandas 3.x, text columns can report dtype literally as `"str"` (not `"object"`/`"string"`); without checking for that string, every geographic-tagged column (e.g. Region) would silently fall out of both the dtype check and the semantic-tag check, excluding it from every downstream ranking function.
239. **Why does chart generation happen on `df` (a fresh, restored-to-real-units copy) rather than the `cleaned_df` returned to state?**
    So the scaled representation stays intact and available to any modelling code via `state['scaling_params']` and the untouched `<col>_scaled` column, while every chart/statistic Agent 4 itself produces reads real-world units.
240. **What would you say if asked "why not use Plotly/D3 directly instead of matplotlib PNGs"?**
    Both exist in this system — matplotlib PNGs are the deterministic, universally-renderable "twin" for print/PDF/`<noscript>` fallback, while `echarts_options.py` builds the interactive on-screen chart from the exact same `ChartSpec` data, so the two never disagree.

---

## G. Agent 5 — Output Validation & Trust Gate (35)

241. **What is Agent 5's core job in one sentence?**
    Independently verify that everything Agents 1–4 produced is internally consistent and trustworthy *before* any LLM is allowed to write prose about it.
242. **Does Agent 5 use any LLM?**
    No — its Tier-1 checks and Tier-2 Cohen's kappa computation are all pure Python; it's the "zero LLM cost" trust gate.
243. **What are the two tiers of checks?**
    Tier 1: deterministic contract/statistical checks (always run). Tier 2: Cohen's kappa agreement between the LLM's semantic type judgment and the independent heuristic sniffer.
244. **List all Tier-1 checks.**
    Row/column reconciliation, schema-dataframe consistency, quality-score bounds, stats numeric sanity, chart artifact integrity, business-rule validation, category-normalization safety, trend sample sufficiency.
245. **What does "row/column reconciliation" verify?**
    Cross-checks Agent 3's own `row_accounting.final_rows` ledger entry against the *actual* `len(cleaned_df)` — catches any silent mismatch between what Agent 3 claims happened and what actually happened.
246. **What does "schema-dataframe consistency" verify?**
    Every schema column not dropped by imputation must actually exist in `cleaned_df` (accounting for known canonical replacements, e.g. a redundant derived column that was intentionally removed and replaced).
247. **What does "stats numeric sanity" verify?**
    Every descriptive statistic must be finite (no NaN/Inf), and every Pearson correlation coefficient must fall within [-1, 1] (with a tiny floating-point tolerance).
248. **What does "chart artifact integrity" verify?**
    Every path listed in `chart_paths` must actually exist on disk and be non-empty (size > 0 bytes) — catches a chart-generation bug that silently produced a broken/missing file.
249. **What does "business-rule validation" verify?**
    Rolls up Agent 3's count-range/financial-constraint validation failures; the *worst* single rule's failure percentage must be ≤ `MAX_VALIDATION_FAIL_PCT = 15%`.
250. **What does "category-normalization safety" verify?**
    Rejects any fuzzy category merge from Agent 3 that either changed more than 5% of rows at once, or merged two values that were each independently common (>1% of rows) — a safeguard against an overly-aggressive merge slipping through.
251. **What does "trend sample sufficiency" verify?**
    Re-checks every regression trend Agent 4 marked "significant" (p<0.05) against a minimum sample size of 10 — a significant fit on 4-5 points is statistical noise, not a trustworthy trend, even though Agent 4 doesn't itself enforce a sample-size floor.
252. **Why does Agent 5 re-check something (trend sample size) that Agent 4 could have checked itself?**
    Separation of concerns — Agent 4 doesn't know Agent 5's reliability bar; keeping the "is this trustworthy enough to report" judgment in the dedicated validation agent means the threshold is defined and changed in exactly one place.
253. **What is Cohen's kappa measuring here, precisely?**
    Agreement between two independent "raters" of column type: Agent 2's LLM-assigned `intended_type` (coarsened to numeric/datetime/boolean/string/unknown) and the pure-Python heuristic type sniffer re-run fresh in Agent 5.
254. **Why is Cohen's kappa implemented from scratch instead of using scikit-learn?**
    So the validator doesn't need an extra dependency for one formula; the observed-agreement-minus-expected-agreement-by-chance calculation is simple enough to implement directly and test.
255. **Give the Cohen's kappa formula used.**
    κ = (observed_agreement − expected_agreement) / (1 − expected_agreement), where expected_agreement is computed from each rater's marginal label frequencies assuming independence.
256. **What edge case does the kappa implementation explicitly handle?**
    If `expected_agreement ≥ 1.0` (both raters used exactly one class throughout, a degenerate case), it returns `1.0` (trivial perfect agreement) rather than dividing by zero.
257. **Why is Cohen's kappa valuable *without* ground-truth human labels?**
    It measures whether the LLM's judgment mechanically agrees with an independent, non-LLM baseline — a proxy trust signal for "is the LLM behaving sanely on this dataset" that doesn't require anyone to have hand-labeled the correct semantic tags.
258. **What's the acceptance threshold and what does it mean qualitatively?**
    `MIN_ACCEPTABLE_KAPPA = 0.4` — the Landis & Koch (1977) boundary for "fair" agreement or better; below this, low agreement is a warning that the schema should be reviewed, not just accepted blindly.
259. **What was the sample run's kappa, and what does that number mean in context?**
    1.0 (perfect agreement across all 14 columns) — meaning the LLM's type judgments never contradicted the local mechanical sniffer on that dataset; it's an internal-consistency measure, not an external accuracy score against a labeled gold standard.
260. **Why must you be careful how you phrase "our kappa is 1.0" to an examiner?**
    Because it's agreement between the LLM and a heuristic, not agreement with human-verified ground truth — overstating it as "human-validated accuracy" would be an easy, avoidable mistake to be caught on.
261. **How is `overall_validation_score` computed?**
    `100 × (passed_checks + 0.5 × warned_checks) / total_checks` — warnings count as half credit rather than a full pass or fail.
262. **What determines `passed` (the hard gate)?**
    `passed = (failed_checks == 0)` — any warning-level issue doesn't block the gate, but any check at `fail` severity does.
263. **What happens to the pipeline if `passed` is False?**
    `should_continue_after_agent5` in `pipeline.py` routes to `END` — Agent 6 never runs, so no narrative report is ever generated over data the pipeline itself doesn't trust.
264. **What's the difference between a "warn" and a "fail" severity check?**
    Set per-check when it's recorded (e.g. business-rule validation and category-normalization safety are recorded at `severity="warning"`) — a design choice that some imperfections (like a moderately-high validation failure rate) are worth surfacing but not worth halting the entire pipeline over.
265. **How is Agent 5's own confidence in its *validation score* computed (a confidence about a confidence)?**
    `_validation_confidence`: starts from the validation score itself (0–1 scaled), halved if a data-quality "review_required" flag was set, then reduced further per insufficient-sample trend found.
266. **What does `review_required` (from Agent 4's data-quality-issues summary) mean here?**
    A signal that a structural rule fired on enough rows to need human review — factored into how much Agent 5 trusts its own overall assessment, not just into whether individual checks pass.
267. **Is Agent 5 itself capable of "hallucinating" anything?**
    No — every check is a direct, deterministic computation over state that already exists; there's no generative step in Agent 5 to hallucinate with.
268. **Why does Agent 5 look at `state["_df_cache"]` (the *raw* dataframe) for category-normalization safety, not `cleaned_df`?**
    It needs the raw, pre-merge value counts to compute what percentage of rows a fuzzy merge actually changed and how common the merged-away value originally was — that comparison requires the "before" state, not the "after."
269. **What's a concrete example of a fuzzy merge Agent 5 would reject?**
    A hypothetical merge that changed 8% of rows (over the 5% threshold), or one that merged two labels each independently representing >1% of rows (both "common enough to plausibly be real, distinct categories").
270. **What's the single most quotable line about Agent 5 for the defense?**
    "It's the only agent whose entire job is to say 'no' — and it can, at zero extra API cost, which is why it's the strongest evidence this system isn't just trusting the LLM."
271. **Could Agent 5 give a false sense of security (pass things it shouldn't)?**
    It's limited to what it's told to check — a genuinely wrong-but-internally-consistent number (e.g. a correct-looking but semantically nonsensical business metric) wouldn't necessarily be caught by contract checks alone; that's an honest limitation worth naming if pushed.
272. **How would you extend Agent 5 if asked "what would you add next"?**
    A SelfCheckGPT-style resampling/consistency check on the LLM narrative itself is explicitly noted in the code's own docstring as reserved for future work, once there's actual free-form prose (post-Agent 6) to validate against multiple samples.
273. **Does Agent 5 verify anything about the frontend/report rendering itself?**
    No — its checks are entirely about the pipeline's computed state (stats, charts-as-files, schema); it runs and gates *before* Agent 6 renders anything, so report-rendering bugs are out of its scope by design.
274. **What data structure does Agent 5 use to accumulate its findings?**
    A small `ValidationLedger` class holding `checks` (name → status/detail) and `issues` (only the failed/warned ones, each with a severity) — a lightweight, purpose-built accumulator rather than reusing Agent 3's `ColumnLedger`.
275. **Why does the pipeline print a warning even for checks that only produced a "warn," not a "fail"?**
    Warnings are still surfaced in the console log and in `flagged_issues` for visibility/audit purposes — they just don't block the gate the way a "fail" does.

---

## H. Agent 6 — Insight Report Generator (40)

276. **What's Agent 6's contract?**
    Take everything computed by Agents 1–5, extract deterministic facts, generate a grounded plain-language narrative, and render a self-contained HTML (or PDF) report.
277. **Does Agent 6 always call an LLM?**
    It attempts to (Groq → Gemini fallback), but always computes a fully deterministic fallback narrative in parallel/afterward as the guaranteed floor — the report never depends solely on the LLM succeeding.
278. **What is `insight_facts` and why is it described as "the only source of truth"?**
    A large, purely-deterministic dictionary extracted straight from pipeline state (shape, quality, correlations, growth, rankings, anomalies, regression, validation, reliability, chart summaries) — the LLM is instructed to write about *only* these facts, and grounding checks later verify it actually did.
279. **What is "hybrid narrative composition"?**
    `_compose_hybrid_narrative`: the deterministic, fact-derived narrative is always computed first as a guaranteed floor; the LLM's version is layered on top of it only where it passes hygiene checks (no unknown chart IDs, no jargon, a validly-shaped 3-part story).
280. **Why "deterministic-first," not "LLM-first with a deterministic fallback only on total failure"?**
    Because an LLM can partially succeed — return grammatically fine prose that's subtly ungrounded or jargon-heavy in just one section — hybrid composition catches and replaces *that specific section*, not just an all-or-nothing failure.
281. **What are the three parts of the "story" section?**
    What happened / Why it matters / What to do next.
282. **What is "claim grounding" and how is it implemented?**
    Every numeric-looking token in the LLM's prose is regex-extracted (`_CLAIM_PATTERN`) and checked against every number that appears anywhere in `insight_facts` (flattened into a set), within an absolute+relative tolerance — ungrounded claims are flagged and logged.
283. **What's the grounding tolerance and why both absolute and relative?**
    `CLAIM_GROUNDING_TOLERANCE = 1.0` absolute, also scaled by 5% of the known value — a flat ±1.0 alone would be too strict for large numbers (a $10,000 rounding is trivial) and too loose for small ones (a ±1.0 error on a count of 3 is huge), so the check uses whichever tolerance is more generous.
284. **What was the sample run's grounding result?**
    21 of 21 checked numeric claims matched computed facts (confidence 1.0).
285. **What is "contradiction detection"?**
    A separate pass (`_check_narrative_contradictions`) that scans the composed narrative for internally inconsistent statements — e.g. describing the data as both "complete" and "has significant gaps" in different sections.
286. **What is "recommendation grounding"?**
    `_ground_recommendations` requires every recommendation to tie back to at least one actual reported finding rather than being generic, data-independent boilerplate advice.
287. **What is the "dynamic glossary" and how does it differ from a fixed glossary?**
    Jargon terms that actually appear in the *final rendered text* get a plain-language definition inline, built from a base glossary plus any additional terms the LLM itself introduced — it doesn't define terms the report never actually uses.
288. **What is the "jargon linter" (`_lint_plain_language`) and when does it run?**
    A final safety net after hybrid composition: any remaining jargon-laden bullet or the `bottom_line` is swapped back to the deterministic wording — the very last line of defense before rendering.
289. **What's the difference between the jargon check inside `_compose_hybrid_narrative` and the separate `_lint_plain_language` pass?**
    The first filters candidate LLM content *before* merging it in; the second is a final sweep over the *already-merged* result in case something jargon-laden slipped through (e.g. from a bullet source not explicitly checked earlier) — belt-and-suspenders.
290. **What determines Agent 6's own confidence score?**
    0.95 if the narrative source is the LLM (post-hygiene-checks), 0.55 if it's the deterministic fallback — then both are scaled by `(0.7 + 0.3 × grounding_confidence)`, so even an LLM-sourced narrative with ungrounded claims scores lower.
291. **Why is the deterministic fallback's confidence 0.55, not near-zero?**
    It's still 100% fact-accurate (it's built directly from `insight_facts`) — it's just less polished/nuanced in wording than a good LLM pass, so it deserves meaningfully more trust than "essentially untrustworthy," just less than a validated LLM narrative.
292. **What decides `decision_readiness` for Agent 6 specifically?**
    `"ready"` only if the narrative source wasn't the fallback AND no claims were flagged as ungrounded — both conditions must hold.
293. **What happens if PDF generation fails (e.g. missing WeasyPrint native libraries)?**
    The report is written as a self-contained HTML file instead (`insight_report.html`) — this is explicitly *not* treated as a data-quality or confidence problem, since it's an environmental/deployment issue, not a signal about report accuracy.
294. **Why does the code explicitly say PDF availability "no longer docks points" in the confidence score?**
    A past version conflated environmental factors (a missing native library on the demo machine) with narrative trustworthiness — that's now corrected so confidence reflects only what the report *says*, not what file format it was saved as.
295. **What are the sections of the rendered report, top to bottom?**
    KPI hero cards → "In Plain English" box → 3-part story → narratively-grouped chart sections → technical appendix in collapsible `<details>` → inline glossary.
296. **What does "narratively grouped chart sections" mean, as opposed to a flat chart dump?**
    Charts are grouped by theme/topic in the rendered output rather than listed in raw generation order — `_group_by_section` organizes the final chart view-models into coherent report sections.
297. **How are charts embedded in the HTML report?**
    As base64-encoded PNGs inline in the HTML (`_embed_png`), so the report is a single self-contained file with no external image dependencies — it opens and displays correctly even emailed as one attachment.
298. **What validation does Agent 6 run on its own extracted facts before even calling the LLM?**
    `_validate_raw_column_count` (facts must reflect the true raw column count from `raw_shape`, not a later transformed count) and `_validate_no_empty_required_cells` (certain required table fields can't silently be blank) — both raise assertions caught and logged as `Agent6:` errors if violated.
299. **Why does Agent 6 specifically re-validate the raw column count against `raw_shape` rather than trusting `insight_facts`?**
    To guard against a documented failure mode where a downstream, already-transformed frame's column count could get reported as "the original dataset had N columns," misleading the reader about what was actually uploaded.
300. **What LLM prompt-size guard exists for the narrative call?**
    `MAX_NARRATIVE_PROMPT_CHARS = 7000` — large fact dictionaries are truncated/compacted (`_truncate_lists_for_prompt`, `_compact_dimension_sections`) before being sent, keeping cost/latency predictable regardless of dataset size.
301. **How are chart captions from the LLM validated before use?**
    Only accepted if the chart ID actually exists in the known chart set, the caption text is non-empty, and it passes the jargon check — capped at `MAX_CHART_CAPTIONS_FROM_LLM = 12` regardless.
302. **What happens if the LLM's `story` field is malformed or missing a required part?**
    `_valid_story` validates its shape; if invalid (or any part contains jargon), the entire story section falls back to `_fallback_story` built from facts, rather than rendering a partial/broken story.
303. **What's `_narrative_provenance` for?**
    Records where the final narrative actually came from (LLM vs. fallback, and why, if it fell back) — surfaced in the report/diagnostics for transparency about how much of the wording is model-generated vs. deterministic.
304. **How does the report format currency/large numbers consistently?**
    Via shared `report_style.py` helpers (`humanize_number`, `humanize_currency`, `humanize_pct`) used by matplotlib chart labels, the interactive chart JS, and the narrative prose alike — one source of truth so a number never displays differently in different parts of the same report.
305. **What does `_quality_verdict` do?**
    Converts the numeric 0–100 quality score into a qualitative label for the report's KPI cards (e.g. an "excellent/good/needs attention"-style verdict), so a non-technical reader doesn't have to interpret a raw number.
306. **How is the "In Plain English" box different from the executive summary?**
    It's a compact, deterministic-first bullet list (`plain_language_insights`) specifically designed to survive even if the LLM path fails entirely, distinct from the more free-form LLM-authored executive summary text.
307. **Why is claim grounding described as "the direct implementation of RAG-style grounding," even though this isn't a retrieval system?**
    The same core idea — constrain generation to verifiable facts and check the output against them afterward — is applied here without needing a vector database, because the "knowledge base" is simply the deterministic `insight_facts` dict already in memory.
308. **What happens to a narrative claim that's flagged as ungrounded — is it removed from the report?**
    No — it's flagged in `claims_grounding` (logged and factored into confidence), but the current implementation doesn't automatically strip individual ungrounded sentences from the rendered prose; that's a reasonable "what would you improve" answer if asked.
309. **Why compute `deterministic = _fallback_narrative(insight_facts)` even when the LLM call succeeded?**
    It's needed as the comparison baseline for hygiene checks and as the literal floor to merge onto — you can't safely "fall back to the deterministic version for just the story section" without having already computed it.
310. **What's the practical difference between "the LLM failed" and "the LLM succeeded but hybrid composition rejected parts of it"?**
    The first sets `narrative_source="fallback"` outright (confidence 0.55 ceiling); the second keeps `narrative_source="llm"` but the final text is a genuine blend — Agent 6 can produce an LLM-sourced report where, say, the bottom line is deterministic wording because the LLM's version used jargon.
311. **What is `_narrative_text_blob` used for?**
    Concatenates all narrative text fields into one string so the jargon-pattern scan and dynamic-glossary term detection only need to run once over the whole rendered content, not field-by-field.
312. **How many "risks" or caveats does the report typically surface, and where do they come from?**
    They're generated as part of the narrative (LLM or fallback) grounded in `insight_facts`' quality/validation signals — e.g. a lower validation score or flagged anomalies would surface as a risk note, not invented independently of the computed facts.
313. **Why does Agent 6 require `validation_report` to be non-empty before running at all?**
    If `cleaned_df`, `stats`, or `validation_report` is missing, it immediately errors out — Agent 6 structurally cannot run without Agent 5 having actually executed and produced a verdict, reinforcing the hard-gate design.
314. **What would happen if you tried to call `agent6_insight_report_generator` directly with a hand-built state that skipped Agent 5?**
    It would fail its own precondition check (`not validation_report`) and append an `"Agent6: Missing cleaned_df, stats, or validation_report"` error rather than attempting to generate a report — by design, it can't be tricked into writing over unvalidated data even if called out of order.
315. **What template engine renders the final HTML?**
    Jinja2 (`templates/insight_report.html.jinja`), with `report_style.py`'s humanize/label helpers registered as custom Jinja filters.

---

## I. Magic Numbers & "Where did this come from?" (35)

*(Full detail in [MAGIC_NUMBERS.md](./MAGIC_NUMBERS.md) — short answers here.)*

316. **Where does the IQR ×1.5 outlier fence come from?**
    Tukey's classical (1977) "mild outlier" convention — the textbook-standard IQR multiplier, used for descriptive flagging (Agent 1) and default clipping (Agent 3).
317. **Where does the IQR ×3.0 anomaly threshold come from?**
    Tukey's "far-out" fence (the wider, second convention from the same tradition) — chosen specifically because 1.5× was measured to over-flag ~24% of rows on a real skewed column when used for *reporting* anomalies.
318. **Where does the 0.4 Cohen's kappa threshold come from?**
    The Landis & Koch (1977) interpretive scale for kappa, where 0.4 is the boundary into "fair" agreement.
319. **Where does the p<0.05 significance threshold come from?**
    Standard statistical convention (5% significance level) — used consistently for regression trend "significance" in both Agent 4 and Agent 5.
320. **Where does z=3.5 (not the textbook z=3) come from?**
    An engineering judgment call, slightly more conservative than the common z=3 convention, to reduce false-positive anomaly flags on real business data.
321. **Where does the 80% type-parseability threshold come from?**
    An engineering choice, not a formal statistical test — high enough to require strong evidence, low enough to tolerate some genuinely corrupt entries in an otherwise consistent column.
322. **Where does the 20% "exclude from analysis" missingness threshold come from?**
    `MISSINGNESS_ANALYSIS_THRESHOLD_PCT=20.0` in Agent 2 — an engineering judgment that beyond ~1/5 missing, per-column statistics are unreliable enough to flag rather than silently compute.
323. **Where does the Levenshtein-distance-2 / min-length-6 fuzzy match rule come from?**
    Empirically verified against real observed dataset category values — the code comment explicitly documents the legitimate merges it was checked to preserve and the false-positive risks (short antonyms/codes) it was checked to exclude.
324. **Where does the one-hot cutoff of 10 categories (with top-8+Other above that) come from?**
    A common, practical machine-learning engineering convention to bound one-hot column-count explosion — not derived from this dataset specifically, a general-purpose default.
325. **Where does the 16-chart cap per report come from?**
    An editorial/UX judgment call (readability of the final report) balanced against dataset richness — explicitly made environment-configurable (`MAX_CHARTS_PER_REPORT` env var) because the "right" number is genuinely use-case-dependent.
326. **Where does the currency plausibility ceiling (1.1B/1B/10B by profile) come from?**
    An engineering safety-net choice per preprocessing profile — high enough not to reject genuinely large legitimate business figures, low enough to catch a decimal-parsing bug that inflates a value by orders of magnitude.
327. **Where does the 90%/95% "broken rule" thresholds come from?**
    Engineering judgment: if a rule fires on almost every row, the far more likely explanation is a misconfigured rule (wrong column matched, wrong bounds) than a near-universally broken dataset.
328. **Where does the 5-neighbor KNN default come from?**
    scikit-learn's own conventional default for `KNNImputer` — not tuned specially for this project, a standard, unremarkable starting point.
329. **Where does the max_iter=10 for iterative imputation come from?**
    A practical convergence budget for MICE-style iterative imputation on typical business-dataset sizes — enough rounds to stabilize without excessive runtime, not derived from a formal convergence proof for this specific data.
330. **Where does the 3% "material difference" threshold for rankings come from?**
    `_is_material_difference`'s absolute_threshold_pct=5, multiplier=1.5 — an engineering choice about what counts as a "real" gap worth calling out in the narrative versus noise-level variation.
331. **Are any of these thresholds learned/tuned via machine learning?**
    No — none of them are ML-fitted; they're either well-known statistical conventions or documented, code-commented engineering judgment calls (some empirically checked against real sample data behavior).
332. **If an examiner says "these numbers seem arbitrary," what's the strongest honest response?**
    "Several are textbook statistical conventions (Tukey fences, Cohen's kappa bands, p<0.05); the rest are documented engineering judgment calls, many with an explicit rationale and a specific observed failure case in the code comments — and the profile system means the most business-sensitive ones (currency ceiling, tax rate, reconciliation tolerance) are deliberately *not* fixed constants, they're configurable per dataset domain."
333. **Which constants are environment-overridable, and why does that matter?**
    `ANOMALY_IQR_MULTIPLIER` and `MAX_CHARTS_PER_REPORT` — shows the team anticipated needing to tune behavior per-deployment without a code change, a maintainability/production-readiness signal.
334. **Which numbers differ across the three preprocessing profiles, and why is that a better answer than "one fixed threshold"?**
    Currency ceiling, tax rate ceiling, reconciliation tolerance, and quality-score weights — a single fixed threshold can't be simultaneously right for strict financial auditing and lenient generic exploration, so the profile system encodes that trade-off explicitly instead of picking one number and hoping it fits everything.
335. **What's the rule-manifest hash/version for, and is it a "magic number"?**
    Not a threshold — `RULE_DEFINITION_VERSION="2026.08.1"` plus a content hash of the rule definitions, stamped onto every run's output, so any specific report can be traced back to exactly which version of the business rules produced it (reproducibility/auditability, not statistics).
336. **Why 3 sample values sent to the LLM, not 5 or 10?**
    A cost/signal trade-off — enough to communicate format and rough content, small enough to keep every prompt bounded regardless of dataset size (a fixed, not row-count-scaling, prompt cost).
337. **Why does `humanize_number` switch at exactly 1,000 / 1,000,000 / 1,000,000,000?**
    Standard K/M/B abbreviation boundaries used in everyday business reporting — not a statistical choice, a readability convention.
338. **Why is the safe-filename max length exactly 120 characters?**
    A conservative, well-under-typical-OS-path-limit cap for a generated chart filename component, leaving headroom for the directory path and a hash suffix.
339. **Why 400 as the max scatter-plot sample size in the chart planner?**
    A rendering-legibility/performance trade-off — enough points to preserve the visual shape of a relationship, far fewer than what would render as an unreadable smear or slow the chart-generation step down on a huge dataset.
340. **Why is the row-survival floor exactly 50%, not e.g. 90%?**
    Deliberately generous — legitimate cleaning (heavy deduplication, aggressive but correct filtering) could reasonably remove a large minority of rows; the 50% floor is meant to catch a catastrophic bug (a bad join/merge key), not to second-guess normal cleaning outcomes.

---

## J. LLM / Transformer Theory (30)

341. **What is a Large Language Model, formally?**
    A neural network trained to model the probability distribution of natural language — given prior tokens, it estimates the probability of the next token.
342. **Why decoder-only, not encoder-decoder, for this use case?**
    Text-generation models like Qwen use a decoder-only stack with causal masking, making them autoregressive — appropriate here since the task is "generate a JSON/prose response," not sequence-to-sequence translation between two distinct sequences.
343. **What replaced recurrence in the Transformer, and why does that matter for training speed?**
    Self-attention — it relates every token to every other token in parallel, instead of RNN/LSTM's step-by-step sequential processing, making training far more parallelizable.
344. **What is a "causal mask" and what does it enforce?**
    A mask ensuring the prediction at position t can only attend to positions 1..t — enforces the left-to-right, autoregressive generation property.
345. **What is tokenization, and why subword tokens specifically?**
    Splitting raw text into subword units from a fixed vocabulary — balances vocabulary size against the ability to represent rare/unseen words as combinations of known subword pieces.
346. **What is the embedding step, formally?**
    Each token index is mapped through a learned embedding matrix E ∈ ℝ^(V×d) into a dense d-dimensional vector.
347. **Why is positional encoding needed at all?**
    Self-attention is inherently order-agnostic (it's a set operation over tokens) — positional information must be injected explicitly so the model can distinguish token order, not just identity.
348. **Write the scaled dot-product attention formula.**
    Attention(Q,K,V) = softmax(QKᵀ / √d_k) · V.
349. **Why divide by √d_k in attention?**
    To keep the softmax's input scale stable — without scaling, large dot products (from higher-dimensional keys) push softmax into extremely peaked/saturated regions, destabilizing gradients.
350. **What is multi-head attention and why use several heads?**
    Running several attention computations in parallel, each with its own learned projections, so the model can capture different types of relationships between tokens simultaneously.
351. **What does the feed-forward sub-layer + residual connections + layer norm accomplish?**
    Adds representational capacity per block (the FFN) while residual connections and normalization keep gradients well-behaved through many stacked layers.
352. **What is the final next-token prediction step?**
    The last token's representation is projected to logits over the vocabulary, and softmax converts logits to a probability distribution the model samples/argmaxes from.
353. **Why does this project use a low temperature specifically?**
    A low temperature sharpens the softmax distribution toward the highest-probability token, producing near-deterministic output — essential because the response must be strictly valid, parseable JSON, not creative variation.
354. **Why is Groq specifically used instead of a locally-hosted model?**
    Three stated reasons: inference speed (LPU hardware for autoregressive decoding), no local GPU/VRAM requirement, and simplicity/cost control via an OpenAI-compatible chat-completion API.
355. **What is an LPU and how does it differ from a GPU for this workload?**
    A Language Processing Unit — custom silicon designed around the sequential, memory-bound nature of autoregressive decoding, using on-chip SRAM rather than off-chip DRAM to reduce the memory-bandwidth bottleneck of reading weights every token step.
356. **Why is memory bandwidth the bottleneck for autoregressive decoding specifically?**
    Each forward pass generates exactly one token, and the dominant cost per step is reading the full model's weights from memory — compute is comparatively cheap; LPUs target this specific bottleneck.
357. **What is Grouped-Query Attention (GQA) and what problem does it solve?**
    Partitions query heads into groups that share a single key-value head (G groups < H heads); reduces KV-cache size proportionally to H/G, lowering memory-bandwidth pressure during decoding.
358. **Write the GQA formula for one query head.**
    GQA_h(Q_h, K_g, V_g) = softmax(Q_h K_gᵀ / √d_k) · V_g, where K_g/V_g are the shared key/value matrices for that head's group g.
359. **What is RoPE (Rotary Position Embedding) and how does it differ from adding a positional vector?**
    Instead of adding a fixed positional vector to embeddings, RoPE encodes position by rotating the query/key vectors by an angle proportional to position before the dot product, so the resulting attention score depends only on the *relative* position (m−n).
360. **Why does RoPE generalize better to unseen prompt lengths than learned absolute positional embeddings?**
    Because it encodes relative, not absolute, position mathematically through rotation — it doesn't need to have "seen" a specific absolute position index during training to handle it correctly.
361. **What is SwiGLU and what does it replace?**
    A gated feed-forward activation replacing plain ReLU: FFN(x) = (Swish(xW₁) ⊙ xW₂)·W₃, where Swish(x)=x·σ(x) — the gating lets the network adaptively suppress irrelevant dimensions, improving quality at the same parameter count.
362. **What is RMSNorm and why does Qwen use it over LayerNorm?**
    Root Mean Square Layer Normalization — normalizes by RMS(x) without LayerNorm's mean-centering step; achieves similar training stability at lower computational cost since re-centering is often redundant given downstream weight matrices.
363. **What is a KV cache and why does it matter for latency?**
    After the prompt is processed once, the key/value tensors for every prompt token are cached; each new output token only needs to run through the network once (attending to the cache) rather than re-processing the whole sequence — makes generation fast even for long prompts.
364. **Walk through Agent 2's exact call flow to the LLM.**
    Prompt construction (system + user message) → API request (`chat.completions.create`, temperature=0.1, reasoning_effort="none") → tokenization/embedding on Groq's LPU cluster → decoder blocks (GQA+RoPE, SwiGLU, RMSNorm) → logits → softmax → autoregressive generation via KV cache → Gemini failover if needed → response parsing.
365. **Why is Agent 2 described as "loosely coupled to the model provider"?**
    All LLM interaction is isolated inside a handful of functions (prompt building, the Groq/Gemini client calls, response parsing) — swapping in another OpenAI-compatible endpoint wouldn't require touching the rest of the pipeline.
366. **What's the difference between "reasoning_effort" and "temperature" as generation controls?**
    Reasoning effort controls whether/how much the model spends tokens on an internal chain-of-thought-style reasoning block before answering; temperature controls how peaked/random the final token-selection distribution is — they're independent knobs.
367. **Why does the report emphasize the model is "used as a structured reasoning component, not an unrestricted prose generator" in Agent 2?**
    To make clear the LLM's role there is constrained to producing a specific, schema-validated JSON object under a strict system prompt — not open-ended free text generation.
368. **If asked "could you swap in GPT-4 or Claude instead of Qwen," what's the honest answer?**
    Architecturally straightforward for Agent 2/6's OpenAI-compatible-style call sites (loosely coupled, as noted above); it's explicitly listed as future work ("model-agnostic provider configuration") rather than already implemented.
369. **Why does temperature near-zero matter *more* for Agent 2 than for Agent 6?**
    Agent 2's output must be machine-parseable JSON (any deviation breaks the pipeline); Agent 6's output is human-readable prose, where minor stylistic variation is harmless — though Agent 6 also uses controlled generation for consistency.
370. **What's the practical tokenization detail specific to this system's prompts?**
    The prompt containing column names, inferred types, and sample values is tokenized/embedded exactly per the standard pipeline described above — nothing custom to the tokenizer, the customization is entirely in *what content* is put into the prompt (minimal metadata, not full rows).

---

## K. Statistics & Data Science Theory (30)

371. **What's the difference between Pearson and Spearman correlation?**
    Pearson measures linear relationship strength on raw values; Spearman measures monotonic relationship strength on ranks — Spearman is robust to non-linear-but-monotonic relationships and less sensitive to outliers.
372. **What does skewness measure, and what does a positive value mean?**
    Asymmetry of a distribution; positive (right) skew means a long tail toward high values (a few very large values pulling the mean above the median).
373. **What does (excess) kurtosis measure?**
    "Tailedness"/peakedness relative to a normal distribution; Fisher's definition centers a normal distribution at 0 excess kurtosis.
374. **Why use both skewness and kurtosis together to call a distribution "normal" here, rather than a formal test?**
    A cheap, per-column screening heuristic (|skew|≤0.5 and |kurtosis|≤1.0) suitable for scanning many columns quickly; a formal Shapiro-Wilk/Anderson-Darling test would be more rigorous but more expensive and arguably overkill for a screening pass that only informs which imputation/clipping branch to take.
375. **What is the IQR and why is it a robust measure of spread?**
    Interquartile range = Q3 − Q1; robust because it isn't influenced by extreme tail values the way variance/std is.
376. **What is a z-score and what does |z|>3.5 mean statistically?**
    Standardized distance from the mean in units of standard deviation; |z|>3.5 means a value more than 3.5 standard deviations from the mean — under a normal distribution, an extremely rare event.
377. **Why does skew break the assumption behind a plain z-score anomaly test?**
    Z-scores implicitly assume roughly symmetric, near-normal data; skew inflates the standard deviation in a way that either masks true anomalies (in the direction of the tail) or falsely flags legitimate tail values as anomalous.
378. **What is a log-transform z-score and when is it used here?**
    Applying `log1p` before computing mean/std/z-score — used for positive, right-skewed columns, because the log transform compresses the long tail toward symmetry, making a z-score meaningful again.
379. **What is Cohen's kappa measuring, in general (outside this project)?**
    Inter-rater agreement corrected for the agreement expected by chance alone — more informative than raw percent agreement, especially with imbalanced label distributions.
380. **What are the Landis & Koch interpretation bands for kappa?**
    Roughly: <0 poor, 0–0.20 slight, 0.21–0.40 fair, 0.41–0.60 moderate, 0.61–0.80 substantial, 0.81–1.00 almost perfect (this project's 0.4 threshold sits at the fair/moderate boundary).
381. **What is OLS linear regression computing here?**
    Fits `y = slope·x + intercept` minimizing squared residuals between the primary metric and a monotonic time index, via `scipy.stats.linregress`.
382. **What does r² mean in this context?**
    The proportion of variance in the metric explained by the linear time trend — squared Pearson correlation coefficient between fitted and actual/time values.
383. **What does a p-value of 0.05 mean here, precisely?**
    Under the null hypothesis of no real linear trend, there's only a 5% chance of observing a slope this extreme (or more extreme) by random chance alone — the conventional cutoff for calling a result "statistically significant."
384. **Why is a minimum sample size still needed even with a significant p-value?**
    P-values from very small samples are unstable and easily produced by noise fitting a nearly-arbitrary line; a sample-size floor (10) protects against over-interpreting a spuriously "significant" fit on too few points.
385. **What is ANOVA η² (eta-squared) and why use it for chart ranking?**
    The proportion of a metric's total variance explained by group membership (a categorical variable) — used by the chart planner to rank which categorical dimension most meaningfully differentiates a numeric outcome, a principled alternative to just eyeballing bar-chart spread.
386. **What is Cramér's V?**
    A measure of association strength between two categorical variables (derived from the chi-squared statistic, normalized to [0,1]) — used by the chart planner to decide whether a categorical-categorical crosstab/heatmap is worth drawing.
387. **What is Pareto concentration and why 0.6×top1 + 0.4×top3?**
    A weighted measure of how concentrated a metric is in its top categories — weighting the single top category more heavily (0.6) than the cumulative top-3 (0.4) rewards genuinely extreme concentration (a "one category dominates" story) over more evenly-spread top performers.
388. **What is MAPE and why use it for reconciliation checks?**
    Mean Absolute Percentage Error — a scale-independent measure of how far a derived value diverges from its expected/matched value on average; well-suited to comparing business metrics that can span very different magnitudes across datasets.
389. **Why require both correlation AND MAPE for the reconciliation check, not just one?**
    High correlation alone could hide a consistent scaling/offset error (correlated but not actually equal); MAPE alone could be thrown off by a few extreme relative errors on small values — requiring both gives a more robust "these are really the same number" check.
390. **What's the statistical justification for Min-Max scaling vs. z-score standardization?**
    Min-Max bounds values to a known, interpretable [0,1] range and is trivially invertible with just the stored min/max; z-score standardization centers/scales by mean/std, useful for many ML algorithms but not needed here since nothing downstream trains a model on the scaled values directly.
391. **What is coefficient of variation (CV) and why use it for "meaningful variation"?**
    std/mean — a scale-free measure of relative variability, letting the same 0.03 threshold apply sensibly whether the metric is in the tens or the millions.
392. **Why exclude columns that are "formulaic pairs" from correlation reporting, statistically speaking?**
    A correlation between two variables related by an exact algebraic identity (e.g. profit = revenue − cost) reflects the definition, not an empirical discovery about the world — reporting it as "insight" would be statistically vacuous even though the r-value is real.
393. **What does it mean that near-perfect correlations (r>0.98) are flagged as a "possible data quality issue" rather than a finding?**
    In real business data, two genuinely independent variables correlating almost perfectly is far more often a sign of duplicated/derived columns or missing intermediate data than a remarkable true relationship — a domain-informed statistical heuristic, not a hard rule.
394. **What is the difference between a "statistical outlier" and a "leverage point" in regression, and does this project distinguish them?**
    A statistical outlier is unusual in its own distribution; a leverage point specifically has unusual influence on a regression fit. This project's anomaly detection targets univariate outliers (z-score/IQR per column), not regression-specific leverage/influence diagnostics — a fair "what's not covered" answer if pressed.
395. **How would you defend using a fixed set of statistical methods rather than an AutoML-style search?**
    The methods chosen (descriptive stats, Pearson/Spearman, OLS regression, z/IQR anomaly detection, ANOVA-style effect sizes) are standard, interpretable, and directly explainable in the generated narrative — an AutoML/black-box approach would undermine the project's core goal of producing a *trustworthy, auditable* report a non-technical user can act on.
396. **What is the "materiality" concept borrowed from finance/accounting that shows up in the design?**
    Multiple thresholds (currency plausibility, tax rate, reconciliation tolerance, "material difference" in rankings) implement the accounting idea that small discrepancies within a reasonable tolerance shouldn't be flagged as errors, while genuinely large deviations should be — the preprocessing-profile system tunes exactly where that line sits.
397. **What would change statistically if the dataset had far fewer rows (e.g. 50 instead of 10,000)?**
    Several minimum-sample gates (trend n≥10, reconciliation min-pairs=5, IQR needing ≥4 values) would suppress more findings as "insufficient evidence" rather than force a conclusion from too little data — a deliberate conservatism built into the thresholds.
398. **Why does the system avoid presenting confidence intervals or p-values directly to non-technical end users in the plain-language sections?**
    The "In Plain English" design goal is accessibility for non-technical stakeholders — statistical jargon (including raw p-values) is confined to the technical appendix and glossary rather than the main narrative.
399. **What statistical assumption does OLS regression rely on that this project doesn't explicitly test (e.g. homoscedasticity, residual normality)?**
    Correct — the implementation reports slope/intercept/r²/p-value from `linregress` but does not run residual diagnostics (homoscedasticity, normality of residuals, autocorrelation); this is a reasonable "known limitation" to name if an examiner probes regression rigor.
400. **Why is a simple linear regression chosen over more flexible time-series models (ARIMA, exponential smoothing)?**
    Simplicity, interpretability, and speed for a general-purpose "is there a trend" screening tool across arbitrary datasets — proper time-series forecasting is explicitly listed as future work, not a claimed capability here.

---

## L. Backend, API, Infrastructure, Security (30)

401. **What web framework is the backend built on?**
    FastAPI (Python), chosen for its async support, automatic OpenAPI docs, and Pydantic-based request/response validation.
402. **How does the frontend get live progress updates during a long-running analysis?**
    Server-Sent Events (SSE) — a one-way streaming HTTP connection (`GET /{job_id}/stream`) that pushes per-agent progress events as the pipeline runs.
403. **Why SSE instead of WebSockets?**
    SSE is simpler for one-directional server-to-client progress streaming (no need for bidirectional messaging), works over plain HTTP, and is natively supported by browsers via `EventSource`.
404. **What does the job manager do?**
    Runs the LangGraph pipeline for an uploaded file in the background (per job), tracks job status, and emits SSE progress events per agent.
405. **How are jobs isolated from each other?**
    Each job gets a unique `run_id`; charts/reports write to `run_id`-scoped subdirectories, and API-key usage/overrides are captured via thread-local storage scoped per job's execution thread.
406. **What API routes exist and what does each do?**
    `analysis` (submit/stream/cancel/result), `jobs` (list/get/delete), `reports` (serve HTML/PDF + chart images), `chat` (RAG Q&A), `auth` (signup/login/logout), `settings` (per-user API keys), `health` (incl. LLM connectivity test).
407. **How are user-supplied API keys protected at rest?**
    Encrypted using a local encryption key (`.encryption_key`) via `api/services/crypto.py` — never stored or logged in plaintext.
408. **How does a per-user API key take priority over the shared server key?**
    `request_context.get_api_key_override(provider)` checks a thread-local override first; Agent 2/6's client-getter functions check this before falling back to the shared environment-configured client.
409. **How is API key usage made visible to the end user without exposing the key?**
    `agents/key_indicator.py` records provider/model/purpose plus a SHA-256 10-character fingerprint of the key (never the key itself) for every LLM call, surfaced through the job result payload.
410. **What is the RAG dataset chat, and what does it need to function?**
    An optional retrieval-augmented Q&A feature over the uploaded dataset and its analysis results; requires PostgreSQL with the `pgvector` extension and a Hugging Face token for embeddings.
411. **What embedding model does the RAG chat use?**
    `BAAI/bge-base-en-v1.5`.
412. **What two kinds of documents go into the RAG retrieval corpus?**
    Row-level documents from the original uploaded CSV, and "fact documents" derived from the deterministic analysis result (summaries, correlations, rankings, anomalies, chart references).
413. **Why always include "fact documents" regardless of vector-similarity rank?**
    So broad analytical questions ("what's the overall trend?") stay grounded in the computed results even when no single CSV row is semantically closest to the question — pure nearest-row retrieval alone would miss these.
414. **What LLM chain does RAG chat answer generation use?**
    Groq → Gemini fallback → deterministic fallback — the same failover pattern used elsewhere in the pipeline, for consistency and resilience.
415. **What retrieval metrics were reported for the RAG chat, at K=8?**
    Precision@8 = 0.5938, Recall@8 = 0.0049, nDCG@8 = 0.6227, MRR@8 = 0.7500.
416. **Why is Recall@8 so low (0.0049) — is that a bug?**
    No — the corpus contains thousands of row-documents and typically only a handful are truly relevant to any one query, so recall (relevant-retrieved / total-relevant) is mechanically tiny at K=8 regardless of retrieval quality; precision/nDCG/MRR are the meaningful metrics at this corpus scale, not recall.
417. **What does MRR@8 = 0.75 mean in plain terms?**
    On average, the first genuinely relevant result appeared very close to the top of the ranked list (a reciprocal rank of 0.75 corresponds to averaging roughly rank 1–2 across queries).
418. **What auth mechanism is currently implemented?**
    Basic signup/login/logout (`auth.py`, `auth_store.py`) — explicitly not OAuth2/OIDC with refresh tokens or RBAC, which is listed as future work.
419. **What database is used, and is it required?**
    PostgreSQL (with `pgvector` for embeddings) is optional persistence — the core pipeline itself runs without a database; Postgres is only needed for the RAG chat feature and persistent job storage.
420. **How does the on-demand chart / result-builder service work?**
    `result_builder.py` assembles the final API response payload (stats, chart URLs, narrative, validation) from pipeline state for the frontend to consume via `GET /result`.
421. **What does the `health` route's "test LLM" endpoint do?**
    Lets a user verify their configured API key(s) actually work by making a lightweight test call, before running a full (potentially costly) analysis job.
422. **What's cached to avoid repeat LLM cost, at the API layer vs. the agent layer?**
    At the agent layer (Agent 2's on-disk schema cache, keyed by an exact prompt-payload hash) — there isn't a separate API-layer LLM response cache described beyond that.
423. **How would you explain the "encryption key" file's purpose to a security-minded examiner?**
    It's the symmetric key used to encrypt/decrypt per-user API keys at rest in whatever store holds them, so plaintext API keys are never persisted to disk or database directly.
424. **What happens if two users upload files with the same filename at the same time?**
    Server-side storage uses a `<job_id>.csv` naming scheme (per `main.py`'s comment on `csv_path` vs `original_filename`) — the job id, not the user's filename, determines the actual storage path, avoiding collisions.
425. **Why keep `original_filename` separate from `csv_path` in `GraphState`?**
    `csv_path` is the server-side, job-id-based storage path; `original_filename` is what the user actually uploaded and is what Agent 6 should display in the report — conflating them would either leak internal storage naming to the user or show a confusing job-id "filename" in the report.
426. **What deployment target does `render.yaml` suggest?**
    Render.com-style PaaS deployment — a backend web service (and optionally a managed Postgres instance for RAG) defined declaratively.
427. **Is there rate limiting/throttling on the API?**
    Not described as a distinct middleware layer in what's covered here beyond Groq/Gemini's own upstream rate limits and the retry/backoff/failover logic inside the agents — a fair "not yet implemented at the API gateway level" answer if asked.
428. **How would you explain CORS handling if asked?**
    `api/middleware/cors.py` configures Cross-Origin Resource Sharing so the separately-hosted React frontend can call the FastAPI backend across origins during development/deployment.
429. **What's the purpose of `api/utils/serialization.py`?**
    Handles converting pandas/numpy types (Timestamps, NaN, numpy scalars) into JSON-serializable Python primitives for API responses — the same category of problem Agent 2's `_json_safe_value` solves internally for LLM prompts.
430. **If asked "how do you know the backend won't crash on a malformed upload," what's the honest answer?**
    Agent 1's multi-format loaders and multi-encoding fallback catch and convert most load failures into a controlled `Agent1: File load failed` error rather than an unhandled crash, and the API layer wraps job execution in its own error handling — but this hasn't been exhaustively fuzz-tested against arbitrary malformed input, which would be a reasonable robustness improvement to name.

---

## M. Frontend (15)

431. **What frontend stack is used?**
    React 19 with Vite 8 as the build tool, Tailwind CSS v4 for styling, Framer Motion for animation, React Router v7 for routing.
432. **What is the frontend app called?**
    AnalyzeAI (`frontend/AnalyzeAI/`).
433. **Why React 19 specifically — anything used from the newer version?**
    The project simply targets the current React release; nothing in the described architecture depends on a React-19-exclusive feature beyond using the current stable toolchain.
434. **Why Vite over Create React App / webpack?**
    Vite offers much faster dev-server startup and hot-module-replacement via native ES modules and esbuild/rolldown-based bundling — a modern, fast default for new React projects.
435. **What is Tailwind CSS's role here?**
    Utility-first CSS framework for styling components without writing separate CSS files per component — configured via `tailwind.config.ts` and a Vite plugin.
436. **Why Framer Motion?**
    Declarative animation library for React — used for UI transitions/micro-interactions (e.g. progress indicators, page transitions) to make the live-analysis experience feel responsive.
437. **How does the frontend consume the backend's live progress?**
    Opens an `EventSource` connection to the SSE stream endpoint and updates UI state per received event as each agent starts/completes.
438. **How does the frontend render the final report?**
    Displays the interactive HTML/chart content served by the `reports` API route, with charts rendered via interactive ECharts options built from the same `ChartSpec` data structure Agent 4 produces.
439. **What's `oxlint` used for in this frontend?**
    A fast Rust-based linter (used instead of/alongside ESLint) for code-quality checks in the frontend build pipeline.
440. **How does the frontend handle authentication state?**
    Via `src/contexts` (React context) backed by the backend's basic auth endpoints (`/signup`, `/login`, `/logout`).
441. **What is `src/lib` vs `src/utils` likely used for (structurally)?**
    `lib` typically holds the API client/SSE wiring and shared integration code; `utils` holds small pure helper functions — a conventional separation in React project structure.
442. **How does the frontend show per-agent progress specifically (not just a spinner)?**
    Each SSE event names which agent is running/completed, letting the UI render a step-by-step progress indicator (e.g. "Agent 3: Preprocessing…") rather than a generic loading state.
443. **How would a user download the final report?**
    Via the `reports` route (`GET /api/report/{job_id}`), which serves the HTML (or PDF, if WeasyPrint succeeded) for that job.
444. **Does the frontend let a user configure their own API keys?**
    Yes — via the `settings` route/UI for managing per-user Groq/Gemini API keys, encrypted server-side.
445. **What animations live in `src/animations`?**
    Reusable Framer Motion animation definitions/variants shared across components, rather than each component defining its own inline animation config.

---

## N. Results, Evaluation, Comparison (25)

446. **What dataset was used for the reported results?**
    `10000 Sales Records.csv` — 10,000 rows × 14 columns of simulated global sales transactions.
447. **What was Agent 1's finding on this dataset?**
    0.0% missing values, 0 duplicate rows out of 10,000×14.
448. **What preprocessing profile/domain was auto-selected, and why?**
    `strict` profile, `finance_sales` domain — because the dataset's column names/tags matched the finance-keyword/currency-tag detection rule.
449. **What was the final cleaned shape and quality score?**
    10,000 rows × 58 columns, quality score 100.0/100.
450. **What was the strongest correlation found, and was it flagged as formulaic?**
    Unit Price vs. Unit Cost, r=0.99 — reported as a genuine (non-formulaic) strong correlation, not excluded, since it isn't a derived/algebraic identity.
451. **How many anomalous rows were flagged, and what was their estimated business impact?**
    52 rows (0.52%), estimated business impact ≈ $412K.
452. **How many regression trends were tested, and how many were reported significant?**
    8 candidates tested, 0 met both the significance and minimum-sample-size bar on this dataset.
453. **How many charts were generated, and what's a representative sample?**
    16 charts, including a correlation heatmap, boxplots, a revenue histogram, a unit-price-vs-cost scatter, monthly revenue growth/seasonality lines, and top-5 region/item-type bar charts.
454. **What was the Tier-1 validation outcome?**
    All 9 checks passed; overall validation score 100/100.
455. **What was the Cohen's kappa result and what does it mean here?**
    1.0 — perfect agreement between the LLM's assigned types and the heuristic sniffer across all 14 columns on this run.
456. **What was the narrative grounding result?**
    21 of 21 checked numeric claims in the LLM-composed narrative matched computed facts (grounding confidence 1.0).
457. **What was the overall pipeline reliability score, and what does the label mean?**
    0.97 mean confidence, `decision_readiness = "ready"` — meaning the system itself assessed this particular run as trustworthy enough to act on.
458. **How was the comparison against a general-purpose Qwen model set up?**
    Same dataset (`10000_Sales_Records.csv`), same underlying LLM family, asked directly to "analyze this" in a single pass with no pipeline/validation around it.
459. **What was the runtime difference?**
    This pipeline ≈52 seconds vs. the plain Qwen chat ≈4 minutes 12 seconds — about 4.8× slower for the single-LLM approach.
460. **What was the numerical accuracy difference, specifically?**
    This pipeline's totals/breakdowns/rankings matched the source data exactly; the plain LLM reported total revenue as $1.33B instead of the actual $13.33B — a consistent 10× scaling error.
461. **Was the plain LLM's ranking of top categories/regions wrong too?**
    No — rankings and percentages were directionally correct; the error was specifically in absolute dollar figures (a scale error), which is arguably worse because it's easy to miss when the relative story still looks plausible.
462. **What validation did the plain-LLM baseline have?**
    None — no validation layer, so a numerical error like the 10× scaling issue could reach the final output completely undetected.
463. **What statistical depth did the plain LLM provide vs. this pipeline?**
    High-level totals/top-N/recommendations only, no outlier detection or correlation analysis — vs. this pipeline's Pearson/Spearman with tautology filtering, skew-aware anomaly detection, YoY/QoQ trends, and cross-dimensional breakdowns.
464. **How did output length/structure compare?**
    This pipeline: a 27-page structured report with overview, findings, correlations, distributions, anomalies, recommendations, appendix, and glossary. Plain LLM: roughly a 5-section Markdown summary with no appendix or methodology trail.
465. **What's the "actionability" comparison example given in the report?**
    This pipeline tied a finding to specific evidence (Snacks averaging 26.1 shipping days vs. 24.7 for Fruits); the plain LLM's recommendations were broader and less evidence-tied.
466. **What's the single strongest sentence to summarize this comparison?**
    "The pipeline was about five times faster and was the only system in the comparison whose output was independently verifiable against the source data."
467. **Why is the 10× scaling error described as "especially instructive," not just "an error"?**
    Because the directionally-correct rankings could make the report look trustworthy at a glance, while the absolute dollar figures were catastrophically wrong — exactly the class of silent, high-consequence error a validation layer is designed to catch before it reaches a decision-maker.
468. **What runtime numbers are reported per-agent, and what's their source?**
    Agent 1: 0.38s, Agent 2: 4.66s, Agent 3: 1.22s, Agent 4: 6.72s, Agent 5: 0.01s, Agent 6: 2.48s, total pipeline: 24.07s — derived from persisted SSE `running`/`completed` event timestamps in `outputs/analysis_jobs.json`, i.e. pipeline-stage wall-clock durations, not raw provider API latency.
469. **Why are token counts and API latency explicitly NOT reported as numerical results?**
    The current implementation doesn't persist prompt/completion/total token counts or per-call API latency — the report is explicit that it won't claim numbers the system doesn't actually measure yet; that instrumentation is named as future work.
470. **Why is Agent 4 the slowest stage (6.72s) and Agent 5 the fastest (0.01s)?**
    Agent 4 does the heaviest actual computation (many statistical passes plus matplotlib chart rendering to disk); Agent 5's checks are lightweight, purely-in-memory boolean/arithmetic comparisons over already-computed state, with no rendering or heavy computation.

---

## O. Limitations, Risks, Future Work, Ethics (25)

471. **What's the biggest honest limitation to lead with if asked "what doesn't work yet"?**
    Multi-format ingestion (Excel/JSON/Parquet) is only available internally in Agent 1, not exposed on the web upload route yet.
472. **What's missing from the API observability story?**
    Prompt/completion/total token counts and per-call API latency aren't persisted anywhere yet — only provider/model/purpose usage and coarse per-agent wall-clock durations are currently tracked.
473. **What's the auth/security gap?**
    No OAuth2/OIDC, no refresh tokens, no role-based access control, no multi-tenancy — basic signup/login only.
474. **What's the evaluation-scale gap?**
    Results are from one representative sales dataset; systematic benchmarking across 100+ diverse datasets/domains is named future work, not yet performed.
475. **Does the system do any forecasting?**
    No — regression here is retrospective trend detection (was there a linear trend in the observed period), not predictive forecasting of future values.
476. **Can a user customize which charts appear or the narrative's tone?**
    Not yet — an "interactive report customization" visual editor is listed as future work; today the chart selection/narrative are fully automatic.
477. **Does the system learn from user corrections (e.g. fixing a mistagged column)?**
    Not yet — a continuous-learning feedback loop (storing corrections to improve future tagging/preprocessing rules) is named future work, not implemented.
478. **Is the LLM provider swappable by the end user today?**
    Only between the two built-in providers (Groq/Gemini) and their failover chain — full model-agnostic provider configuration (OpenAI, Anthropic, local Ollama models via a settings panel) is future work.
479. **What ethical consideration applies to Agent 2 sending sample data to a third-party LLM API?**
    Only 3 sample values per column (not full rows) are sent, limiting exposure of potentially sensitive raw business data to the external LLM provider — a deliberate privacy-by-minimization design choice, though not a full anonymization/PII-redaction guarantee.
480. **Is there any PII detection/redaction before data reaches the LLM?**
    Not implemented — the mitigation is prompt minimization (metadata + 3 samples only), not explicit PII scrubbing; a fair improvement to name if pushed on privacy.
481. **What happens to uploaded user data after a job completes — is it deleted?**
    The system persists uploaded files/outputs under job-scoped paths (`uploads/`, `outputs/charts/<run_id>/`, `outputs/reports/<run_id>/`); explicit data-retention/deletion policy details aren't a focus of the reviewed code — worth flagging as an operational/compliance question for a production deployment, not something claimed to be solved.
482. **Could this system be used to generate a misleading report if fed adversarially crafted data?**
    Agent 5's checks are about internal consistency of what the pipeline itself computed, not about detecting that the *source data itself* was fabricated/adversarial — that's outside the current threat model, a fair limitation to acknowledge.
483. **What happens if the same dataset is analyzed twice — is the result identical?**
    Largely yes for the deterministic agents (1, 3, 4, 5); Agent 2/6's LLM calls use low temperature for near-determinism but aren't guaranteed bit-identical across calls unless the schema cache (Agent 2) or a cached narrative avoids a repeat call.
484. **Does the system handle extremely large files (multi-GB CSVs) well today?**
    Not optimized for that yet — "performance optimization for datasets >1GB" / chunked ingestion is named as a future enhancement; current ingestion loads the full file into memory.
485. **What would you say if asked "is 6 agents the right number, could it be 4 or 10"?**
    6 maps cleanly onto distinct responsibilities (profile / tag / clean / analyze / validate / report) with clear input-output boundaries between each; fewer would blur genuinely separate concerns (e.g. merging validation into analysis would weaken the "independent trust gate" argument), more would add coordination overhead without a clearly separable new responsibility.
486. **What's a good answer to "what would you change if you rebuilt this from scratch"?**
    Add the API-call metrics wrapper (token counts, latency) from day one, since retrofitting observability after the fact is exactly the friction the current report acknowledges.
487. **Is the system accessible to users with no English proficiency?**
    Not currently — the interface, prompts, and generated narrative are English-only; localization is not an implemented feature.
488. **What happens if the uploaded CSV has a completely different structure than anything the "dataset domain"/chart-planner logic anticipates?**
    The chart-planner's dataset-type classification and preprocessing-domain detection degrade gracefully to generic categories (`generic` domain, `general_table`/`categorical_table` dataset type) rather than crashing — fewer specialized chart families fire, but the pipeline still completes.
489. **How would you respond to "this seems like a lot of hardcoded business logic for 'AI'"?**
    That's intentional, not a weakness — the deterministic logic is what makes the numbers trustworthy; the LLM is deliberately confined to the two places (semantic judgment, prose generation) where a rules engine genuinely can't do the job as well, and even there its output is independently checked.
490. **What's the honest answer to "how do you know Agent 6's grounding check itself is bug-free"?**
    It's covered by dedicated unit tests (`test_agent6_claim_grounding.py`) exercising specific grounded/ungrounded scenarios — like any code, its correctness rests on test coverage and code review, not a formal proof; that's a fair, honest limitation of any software validation layer.
491. **If the panel asks "what was the hardest part of this project," what's a defensible answer grounded in the code?**
    Getting the preprocessing and analysis to be genuinely dataset-agnostic (not hardcoded to one sales-CSV shape) while still producing specific, non-generic insights — visible in how much of Agent 2–4's logic is keyword/token/tag-driven rather than hardcoded column names, plus the documented bugs (docs/known_issues.md references in the code comments) that had to be found and fixed to get there.
492. **What does the presence of `docs/known_issues.md` references in code comments tell you about the development process?**
    Issues were tracked, root-caused, and the fixes documented directly at the point in the code where the fix lives — evidence of an iterative, bug-driven refinement process rather than a one-shot implementation.
493. **What testing exists, and is it enough to claim "production-ready"?**
    200+ unit tests across all 6 agents (`backend/tests/test_agent*.py`) covering specific behaviors (chunking, JSON recovery, currency parsing, fuzzy normalization, anomaly calibration, claim grounding, etc.) — strong for a prototype/thesis project, but the report itself frames this as "a working prototype with clear areas for future extension," not a claim of production hardening.
494. **What's the risk if Groq AND Gemini are both down simultaneously?**
    Agent 2 falls back to deterministic heuristics (schema still produced, just less semantically rich); Agent 6 falls back to the deterministic narrative floor (report still produced, just less polished prose) — the pipeline degrades gracefully rather than failing outright in either case.
495. **What's the risk if a user's API key is invalid/expired?**
    The `health`/`test-llm` endpoint lets a user proactively verify their key before submitting a job; if a job proceeds anyway and the key fails, the same Groq→Gemini→fallback chain applies as any other LLM failure.

---

## P. Closing / Synthesis (5)

496. **In one sentence, why does the validation-gate design matter more than any individual statistical method used?**
    Because a wrong number nobody catches is worse than a missing feature — the architecture prioritizes *catching* errors before they reach a user over maximizing statistical sophistication.
497. **What single artifact would you show first if given 60 seconds to prove this system works?**
    The comparison table: same dataset, same LLM family, this pipeline exact and 4.8× faster, the plain-LLM baseline off by 10× with no way to have caught it.
498. **What's the project's main contribution, in the report's own words?**
    "A practical framework for agentic data analysis that combines deterministic algorithms with controlled LLM reasoning," aimed at settings (education, non-profits, small businesses) where data exists but analytics expertise doesn't.
499. **How would you answer "is this just a wrapper around an LLM"?**
    No — four of six agents (1, 3, 4, and Agent 5's Tier-1 checks) never call an LLM at all; the LLM is a component inside a larger deterministic system, not the system itself, which is precisely the architectural point being defended.
500. **If you only had one minute left in the viva, what would you say?**
    "This project's core claim is narrow and measurable: separating deterministic computation from LLM-generated language, with an explicit validation gate and claim-grounding step in between, produces a report that is faster and numerically exact compared to asking an LLM to do the whole job in one pass — and we quantified that gap (4.8× faster, 10× more accurate) on the same real dataset, not just as a theoretical claim."

---

*That's 500. If you get a question not covered here, the honest fallback is always: "let me trace that through the actual pipeline stage that would produce/check that number" — pointing at the specific agent and, if relevant, the exact constant in [MAGIC_NUMBERS.md](./MAGIC_NUMBERS.md) is a stronger answer than a general one. Good luck tomorrow.*
