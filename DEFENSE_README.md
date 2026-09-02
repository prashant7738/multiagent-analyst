# MultiAgent DataAnalyst — Defense README

Everything you need to explain, defend, and answer questions about this project tomorrow.
Companion files:
- [`MAGIC_NUMBERS.md`](./MAGIC_NUMBERS.md) — every hardcoded constant/threshold in the codebase, where it lives, and why it has that value.
- [`VIVA_QUESTIONS.md`](./VIVA_QUESTIONS.md) — ~500 likely viva questions with short answers.

---

## 0. Cheat sheet (memorize these numbers)

| Fact | Value |
|---|---|
| Number of agents | **6**, orchestrated by **LangGraph** (`StateGraph`) |
| LLM (primary) | Groq API, model `qwen/qwen3.6-27b` |
| LLM (fallback) | Google Gemini (`gemini-flash-latest` → `gemini-3.6-flash` → `gemini-3.5-flash`) |
| LLM (last resort) | Deterministic Python heuristics — pipeline never hard-fails on LLM outage |
| Backend | FastAPI (Python), Server-Sent Events for live progress |
| Frontend | React 19 + Vite + Tailwind CSS v4 + Framer Motion (app name: **AnalyzeAI**) |
| Orchestration state | A single `GraphState` TypedDict threaded through all 6 agents |
| Trust gate | Agent 5 — pipeline **stops** and Agent 6 never runs if validation fails |
| Semantic-tagging trust metric | **Cohen's kappa** (LLM tag vs. local heuristic type sniffer) |
| Kappa acceptance threshold | `MIN_ACCEPTABLE_KAPPA = 0.4` ("fair" agreement, Landis & Koch scale) |
| Sample-run kappa | **1.0** (perfect agreement, 14/14 columns) |
| Sample-run data-quality score | **100.0 / 100** |
| Sample-run validation score | **100/100**, 9/9 Tier-1 checks passed |
| Sample-run claim grounding | **21 / 21** narrative claims matched computed facts |
| Sample dataset | `10000 Sales Records.csv` — 10,000 rows × 14 columns |
| Cleaned dataset shape | 10,000 rows × **58 columns** (one-hot + derived + audit columns) |
| Charts generated (sample run) | 16 (capped from a larger candidate pool by an informativeness score) |
| Pipeline runtime (sample) | ~24–52 s end-to-end (varies by run/config) |
| vs. plain Qwen chat (same dataset) | Pipeline ≈ **4.8× faster** and numerically exact; plain LLM had a **10× scaling error** (reported $1.33B instead of $13.33B) |
| Anomaly z-threshold | `3.5` (skew-aware: falls back to log-z or IQR-3.0 for skewed columns) |
| Outlier clip rule (preprocessing) | IQR ×1.5 (or adaptive percentile 1–99/5–95/2.5–97.5 under risk) |
| Max charts per report | `MAX_CHARTS_PER_REPORT = 16` (env-overridable) |
| Report formats | Self-contained HTML always; PDF via WeasyPrint when native libs are present |

---

## 1. One-paragraph pitch (say this first)

> "This is a multi-agent AI system that turns a raw, messy business CSV into a validated, plain-language analytical report — automatically. Instead of one LLM doing everything (which is where hallucinated numbers come from), the work is split across **six specialized agents** orchestrated by **LangGraph**: one profiles the raw data, one uses an LLM to figure out what each column *means*, one cleans and transforms the data deterministically, one runs the actual statistics and builds charts, one is a hard validation gate that cross-checks everything with zero LLM cost, and the last one writes the human-readable report — and grounds every number the LLM writes back against the numbers the pipeline actually computed. The LLM is used only where judgment is genuinely needed (naming things, explaining things); every number in the final report comes from deterministic Python, not from the model's imagination."

---

## 2. Background, Motivation, Problem, Objectives, Scope

*(This section is taken near-verbatim from the project report so your wording matches what's on paper.)*

### 2.1 Background
Data-driven decision making now matters across health, agriculture, education, and commerce — Nepal's Digital Nepal Framework explicitly prioritizes this. In practice, most organizations outside the Kathmandu Valley still manage data manually in spreadsheets. Modern analytics tools (Power BI, Tableau) need query languages, schema design, or statistics knowledge; enterprise platforms are too expensive for donor-funded NGOs and municipal bodies. LLMs + agent orchestration frameworks (LangGraph) now make an automated alternative feasible.

### 2.2 Motivation
- Organizations have data but lack the technical expertise to analyze it.
- Traditional tools need statistics/programming knowledge or manual report writing.
- Existing LLM-based systems can hallucinate unverified insights.
- Multi-agent systems are now mature enough to automate this whole workflow reliably.

### 2.3 Problem definition
Three concrete failures of the status quo:
1. **Manual workflows** — cleaning, metric calculation, charting, and report compilation takes days to weeks of skilled staff time.
2. **Lack of standardization** — different analysts produce inconsistent results; periods/results aren't comparable.
3. **Limited accessibility** — non-technical stakeholders can't ask ad-hoc questions without an analyst in the loop.

### 2.4 Objectives
1. Build an autonomous multi-agent system that converts raw sales/financial data into professional reports, trend summaries, and recommendations — no manual coding.
2. Make basic financial analytics and sales optimization accessible to small/medium businesses through a no-code web interface.

### 2.5 Scope
**Technical scope**
- Handles sales records, transaction logs, expense sheets.
- Web upload accepts **CSV**; the internal Agent 1 loader also reads **Excel (.xlsx/.xlsm/.xls), JSON/JSONL, and Parquet** when invoked directly (not yet exposed on the upload route — a named future-work item, don't claim it's on the web UI).
- Six-agent pipeline, input CSV → output report, no extra software needed by the end user (it's a web app).

**Primary use cases**
1. Sales performance tracking (trends, top products, seasonality, revenue drivers).
2. Financial reporting & budgeting (expense summaries, income vs. expenditure, budget tracking).
3. Retail/e-commerce analytics (purchase behavior, inventory turnover, channel comparison).
4. Small-business operations (cash flow, margins, supplier tracking) without accounting software.
5. Turning raw financial/sales data into plain-language insight for non-finance managers.

**Out of scope (be upfront about this if asked)**: direct database connectors, real-time streaming data, forecasting/ML model training, multi-tenant RBAC, and non-English natural-language interaction are not implemented — they're future work (Section 8).

---

## 3. System architecture

```
                 ┌───────────────────────────────────────────────────────────────┐
                 │                     FastAPI backend (job manager)             │
User ── CSV ───▶ │  Upload → Job Manager → LangGraph pipeline.invoke(state) → SSE │ ──▶ React 19 SPA
                 └───────────────────────────────────────────────────────────────┘
                                          │
                        (state: a single GraphState TypedDict)
                                          ▼
   Agent 1 ──▶ Agent 2 ──▶ Agent 3 ──▶ Agent 4 ──▶ Agent 5 ──▶ Agent 6
 Structural   Semantic    Preprocessor Statistical  Output    Insight Report
  Profiler    Tagger(LLM)              Analysis     Validator  Generator (LLM)
     │             │            │           │           │            │
 raw_profile  schema_       cleaned_df,  stats,     validation_  insight_facts,
 _df_cache    blueprint     data_quality chart_specs report      report_path
                                                       │
                                          if FAILED → pipeline stops here,
                                          Agent 6 never runs (hard trust gate)
```

- **Orchestration**: `langgraph.StateGraph` ([pipeline.py](backend/pipeline.py)). Each agent is a **pure function**: `state -> state`. Edges are **conditional** (`add_conditional_edges`) — after every agent, a router function checks `state["errors"]` (and, after Agent 3, whether `cleaned_df` exists; after Agent 5, whether `validation_report["passed"]` is true) and decides whether to continue or route straight to `END`.
- **Shared state**: `GraphState` ([main.py](backend/main.py)) — a single `TypedDict` that every agent reads from and writes back into. No agent calls another agent directly; they only communicate through this state object. This is what makes each agent independently testable (`backend/tests/test_agent*.py`, 205+ tests).
- **Reliability layer**: `update_reliability()` in `main.py` — every agent, after doing its work, reports a `confidence` score (0–1) plus supporting `evidence` strings. These are merged into `state["reliability"]`. The **overall confidence** is the mean of all reported per-stage confidences, and `decision_readiness` is derived from it: `≥0.85 → "ready"`, `≥0.65 → "needs_review"`, else `"blocked"`. This is a genuinely novel piece of the design — most LLM pipelines give you an answer with no notion of "how much should I trust this run."
- **Run isolation**: every job gets a `run_id`; charts land in `outputs/charts/<run_id>/` and reports in `outputs/reports/<run_id>/`, so concurrent users' jobs never clobber each other's files.

---

## 4. The six agents, in defendable detail

For each agent: **purpose → inputs/outputs → how it works → what makes it defensible → likely "why" question**.

### Agent 1 — Structural Profiler ([agent_1.py](backend/agents/agent_1.py))
**Purpose**: Read the raw file and *observe* its structure. No fixing, no inference of meaning — purely descriptive.

**Inputs**: `csv_path` (or Excel/JSON/Parquet path). **Outputs**: `raw_profile`, `raw_shape`, `_df_cache` (the loaded DataFrame, cached so nobody re-reads the file).

**What it does**:
- Multi-format ingestion: CSV (including **mixed comma/semicolon delimiter detection per line**), Excel (single or all sheets, concatenated with a `_source_sheet` tag if multi-sheet), JSON (JSON-Lines, records-list, or columns-dict — tried in that order), Parquet.
- Multi-encoding fallback: tries `utf-8-sig` → `cp1252` → `latin-1` in order, so a Windows-exported Excel-CSV with curly quotes doesn't crash ingestion.
- Per-column profile: dtype, missing count/%, unique count, first 3 sample values, an **IQR-based outlier flag** (`Q1-1.5×IQR` .. `Q3+1.5×IQR`), a **datetime-parseability %**, and lightweight **format hints** (currency-like, date-like, identifier-like from the column name).
- Dataset-level enrichments: **skewness/kurtosis-based distribution typing** (normal / right_skewed / symmetric), **implicit missingness detection** (numeric sentinels like `-999`, `9999`; text nulls like `"n/a"`, `"unknown"`), and **column relationship detection** (candidate keys = 100% unique + 0% missing; duplicate-column pairs; |Pearson r| ≥ 0.5 numeric pairs).
- Reports a **confidence score** for its own output based on missing-rate and duplicate-rate (less missing/duplicate data ⇒ higher confidence).

**Why defensible**: This agent never guesses — every field it outputs is directly computable from the raw data, so there's nothing here for the LLM (there is no LLM call in this agent) to hallucinate.

**Likely "why" Q**: *Why IQR ×1.5 for outlier detection here but ×3.0 in Agent 4's anomaly detector?* → Agent 1's flag is just descriptive metadata for later agents (informational, low stakes). Agent 4's anomaly detector actually surfaces "anomalies" to the end user, and the audit found 1.5× over-flags ~24% of rows on skewed real data — too noisy to report as anomalies, so it uses the wider Tukey "far-out" fence (3.0) there. See [MAGIC_NUMBERS.md](./MAGIC_NUMBERS.md).

### Agent 2 — Semantic Tagger ([agent_2.py](backend/agents/agent_2.py))
**Purpose**: Decide what each column *means* (currency? identifier? percentage? categorical label?) — the only agent whose primary job needs judgment, hence the only place an LLM's opinion is structurally load-bearing.

**Inputs**: `raw_profile`, `_df_cache`. **Outputs**: `schema_blueprint` — one metadata dict per column: `intended_type`, `semantic_tag`, `is_identifier`, `scaling_allowed`, `imputation_strategy`, `null_policy` (action + threshold + reason), `encoding_strategy`, `financial_role`, a per-column **confidence score**, and a `column_assessment` (is this column even fit for analysis?).

**How it works, in order**:
1. **Pure-Python type sniffing** (`_infer_intended_types`, zero LLM cost): numeric if dtype numeric or ≥80% of string values coerce to numbers; datetime similarly by ≥80% parseability; else string.
2. **On-disk schema cache**: hashes the exact LLM input payload (dataset + model + prompt version) — an unchanged CSV re-run skips the LLM call entirely.
3. **LLM call** (Groq, `qwen/qwen3.6-27b`, `temperature=0.1`, `reasoning_effort="none"`): sends **only column metadata + 3 sample values per column**, never full rows — this is deliberate for both cost and privacy. Batches columns (10 per call) once the schema is wide (>15 columns) so one call's response never gets truncated by the token budget.
4. **Automatic failover chain**: Groq transient errors (rate limit/timeout/connection/5xx) retry twice with a 3 s backoff → then fail over to **Gemini** (with multi-key rotation and a model-fallback chain) → then a **deterministic heuristic fallback** (`_fallback_blueprint`) if every LLM path fails. The pipeline **never hard-fails** because the LLM is down.
5. **Deterministic guardrails layered on top of the LLM's answer, always, regardless of source** — this is the key design decision to defend: the LLM's opinion is *advisory*, not final. Examples:
   - `_derive_financial_role()` independently classifies *whose* money a currency column represents (company revenue vs. customer income vs. cost vs. tax…) purely from column-name tokens — this exists specifically so a column like `Income` (a customer attribute) is never silently treated as company revenue downstream, even if the LLM's `notes` field got that distinction slightly wrong.
   - `_resolve_null_policy()` / `_derive_null_policy()`: a rich rule table (semantic tag × missingness % × distribution shape × correlation strength) picks the actual imputation action; the model's suggestion is honored only when it isn't one of the "guardrail tags" (identifier/currency/financial/datetime), where the deterministic rule always wins — **currency and financial columns are never mean/median/mode-imputed, period.**
   - `_calculate_semantic_confidence()`: builds a 0–100 confidence score per column from independent evidence signals (name match, type alignment, format hints, cardinality, missingness/outlier penalties) — this is *not* something the LLM reports about itself; it's Agent 2 grading the LLM's answer.
5. Every response is JSON-schema constrained via a long, explicit **system prompt** with per-semantic-tag rules (currency, identifier, datetime, percentage, count, categorical, geographic, free text, physical measurement, unknown) — see the prompt text inline in the file if asked to quote it.

**Why defensible**: the LLM never sees raw data values beyond 3 samples/column (privacy + cost), its output is graded by an independent confidence score, its high-risk decisions (imputation of money, identifier handling) are overridden by deterministic rules regardless of what it said, and it degrades gracefully to pure heuristics if unavailable — Agent 5 later measures, with **Cohen's kappa**, whether the LLM's type judgment agreed with the independent heuristic sniffer, giving an objective trust signal **without needing ground-truth labels**.

### Agent 3 — Preprocessor ([agent_3.py](backend/agents/agent_3.py))
**Purpose**: Turn the schema blueprint into an actually clean, analysis-ready DataFrame. Fully deterministic — **no LLM calls in this agent at all.**

**Inputs**: `_df_cache`, `schema_blueprint`. **Outputs**: `cleaned_df`, `cleaned_csv_path`, `scaling_params`, `preprocessing_log` (a full audit trail), `data_quality` (0–100 score + breakdown), `column_ledger` (per-column before/after tracking), `category_normalization`, `preprocessing_profile`/`dataset_domain`.

**The pipeline (order matters — it's a real ~13-step sequence, not the old README's "10 steps")**:
0. **Exact-row dedup**, with a consistency assertion against Agent 1's own duplicate count (`dedup_exact_rows`, aborts if the numbers disagree — a canary for upstream bugs, not "trust and proceed").
1. **Currency cleaning** — strips ₹ $ € £ ¥ ₩, handles `(123)` → `-123` accounting negatives, disambiguates `1.234,56` (European) vs `1,234.56` (US) by comparing the position of the last `,` vs last `.`. Has a **critical plausibility assertion**: if a currency column parses to 100% null, or its max absolute value exceeds a configured cap, the whole pipeline halts right there rather than silently continuing with garbage.
2. **Type coercion** (float/int/datetime/boolean) using `pd.to_datetime(..., format="mixed")` — parses each value against *its own* format instead of locking onto the first row's format and NaT-ing every other format in a mixed-format column.
3. **Text standardization** — canonicalizes categorical/geographic columns (case + separator folding); leaves free text alone.
3a. **Fuzzy category-spelling merge** — a from-scratch **Levenshtein-distance** clustering (`_build_canonical_category_map`) that merges near-duplicate labels the exact fold above missed (e.g. `"Complete"` vs `"Completed"`, `"Cancelled"` vs `"Canceled"`). Deliberately guarded (min length 6, edit distance ≤2, same first letter, rare-value-only) so it never merges genuinely different short/antonym labels like `"North"`/`"South"` — see [MAGIC_NUMBERS.md](./MAGIC_NUMBERS.md) for the exact reasoning, this is a great "why this number" question.
3b. **Post-canonicalization dedup** (rows that only became duplicates after label merging).
3c. **Business-metric derivation** — profit, margin %, revenue per unit, revenue after discount, discount %, budget variance %, total cost — but only from columns Agent 2 explicitly tagged with the right `financial_role` (never guesses "Income" is "Revenue").
3d. **Ground-truth reconciliation** — if a derived metric (e.g. `derived_profit`) and an *existing raw column* both represent the same concept (matched by name-token overlap, not a hardcoded pair), they must agree (`r ≥ 0.99`, MAPE ≤ 1%). A divergence is surfaced as a pipeline warning — this catches "my formula picked the wrong column" bugs automatically, on any dataset.
4. **Business-rule validation** — count-range checks (no negative/non-integer counts) and financial-constraint checks (tax-rate sanity, total = amount+tax−discount reconciliation, profit-margin bounds), each flag becoming its own boolean column for full auditability.
5. **Imputation** — a rich decision table per semantic tag and missingness level: mean/median/mode/`"Unknown"`/forward-fill/**KNN**/**iterative (MICE-style)**/drop-rows/drop-column/flag-only. Currency/financial columns are hard-blocked from any fill (defence-in-depth, independent of what Agent 2 said).
6. **Categorical encoding** — one-hot for ≤10 categories; **top-8 + "Other" bucket** for higher cardinality; ordinal only with an explicit order list; a safety net skips encoding entirely if a column is >50% unique (looks like a mistagged ID/date, not a real category).
7. **Adaptive outlier clipping** — IQR ×1.5 by default, but switches to **percentile clipping** (1–99 / 5–95 / 2.5–97.5, depending on the dataset's assessed data-quality risk tier) *only* when Agent 1's own distribution analysis actually shows skew/outliers — never a blanket rule based on semantic tag alone (a documented past bug: percentage/count columns were always percentile-clipped even when clean, manufacturing a fake ~5% "outlier rate" out of nothing).
8. **Min-Max scaling** (0–1) for eligible numeric columns, preserving `<col>_raw` and `<col>_scaled` so nothing is destroyed — Agent 4 later inverse-transforms these back to real units before computing any statistics.
9. **Date feature extraction** — year/month/quarter/day/day_of_week/is_weekend/week_of_year.
10. **Quality scoring** — a weighted formula (completeness / consistency / deduplication / structure) whose weights are themselves configurable per **preprocessing profile**.

**Preprocessing profiles** (`strict` / `balanced` / `lenient`): auto-selected from a **dataset-domain detector** (`finance_sales` if ≥3 finance-keyword column names or ≥2 currency/percentage tags → `strict`; else `balanced`) or explicitly requested by the user. Each profile has its own currency plausibility cap, max reasonable tax rate, reconciliation tolerance, and quality-score weighting. This is how the same code behaves more conservatively on financial data and more forgivingly on a generic dataset.

**Safety net**: `_assert_row_survival_or_abort` — if any step drops more than half the rows, the pipeline halts immediately with an explicit error rather than silently returning a decimated dataset (this catches bugs, not just data problems).

**Likely "why" Q**: *Why min-max scaling and not z-score/standardization?* → Because Agent 6's report must show numbers in real, human-readable units, and min-max keeps a known, invertible [0,1] range with the original min/max saved for exact reconstruction; z-scored values would need the same reconstruction machinery for no benefit here since no downstream ML model consumes the scaled column directly.

### Agent 4 — Statistical Analysis & Chart Generation ([agent_4.py](backend/agents/agent_4.py), [chart_planner.py](backend/agents/chart_planner.py), [chart_spec.py](backend/agents/chart_spec.py))
**Purpose**: Compute real statistics and select/generate charts. **No LLM calls.**

**Inputs**: `cleaned_df`, `schema_blueprint`. **Outputs**: `stats` (a large dict — descriptive, correlation, growth_rates, top_bottom, seasonality, anomalies, regression, distributions, plus several domain-specific families), `chart_paths` (PNG files), `chart_specs` (a unified, dataset-agnostic chart contract consumed by both the interactive front-end and the static report).

**First step, always**: `_restore_scaled_columns()` inverse-transforms Agent 3's min-max-scaled columns back to real units — every statistic and chart in this agent operates on real-world numbers, not 0..1.

**Chart planning is dataset-agnostic on purpose** — `_build_chart_plan()` classifies the dataset (`sales_timeseries` / `sales_categorical` / `time_series` / `mixed_analytics` / `numeric_table` / `categorical_table` / `general_table`) from what columns actually exist, then only turns on the chart "families" that are structurally possible (e.g. seasonality only if there's both a revenue-like column *and* a time axis). This is the difference between "template report" and "this report was actually built from this dataset."

**Statistical methods implemented, with the theory to defend each**:
- **Descriptive statistics**: count, mean, median, std, variance, min/max, Q1/Q3, **skewness**, **excess kurtosis** — per numeric column.
- **Correlation**: Pearson (linear) + Spearman (monotonic, rank-based) on every numeric-numeric pair; a pair is "strong" at |r|≥0.7, "moderate" at |r|≥0.5. Two dedicated anti-hallucination filters sit on top:
  - **Leakage detection** (`flag_leakage_columns`) — flags ID-like, `_score`/`_proba`/`predicted_`-named, or near-perfectly-correlated-with-exactly-one-other-column fields so they're excluded from "Top Correlations" instead of being narrated as a business insight.
  - **Formulaic-pair exclusion** — a derived metric correlating ~1.0 with its own source column (e.g. `derived_profit` vs `Revenue`) is not a *discovery*, it's algebra; these are tracked via an explicit derivation map from Agent 3, not a correlation-value cutoff, so it's not fooled by an *indirect* identity (e.g. `revenue_per_unit` being exactly `unit_price` through an intermediate formula).
- **Growth rates**: Month-over-Month and Quarter-over-Quarter % change on the primary revenue metric; charts auto-roll from monthly/quarterly to yearly grain once there are more than 40 periods, so the chart stays legible even on a multi-decade dataset (the underlying stats stay full fidelity — only the *chart* is coarsened).
- **Top/Bottom-N rankings**: revenue and profit broken down by categorical dimensions, with business-priority dimensions (region/category/segment/representative — matched by keyword) always guaranteed a ranking slot instead of losing to noisier high-cardinality columns.
- **Seasonality**: average revenue by month/quarter, best/worst period identified.
- **Anomaly detection** — **skew-aware**: plain z-score (|z|>3.5) for roughly-symmetric columns; a **log-transformed z-score** for positive, right-skewed columns; a wide **IQR ×3.0 "far-out" Tukey fence** for anything else skewed and not strictly positive. This exists because a flat z=3.5 either misses real anomalies on skewed data or over-flags a large chunk of a legitimate long tail.
- **Structural data-quality issues** (distinct from statistical anomalies!) — negative counts, discount % out of range, tax rate implausible, totals that don't reconcile: these are genuine *defects* and penalize the quality score far more heavily (scale 1.5, cap 40) than statistical outliers (scale 0.1, cap 5), because a legitimately huge but real transaction shouldn't be punished the same as a negative quantity.
- **Regression / trend analysis**: OLS linear regression (`scipy.stats.linregress`) of each numeric column against a monotonic time index; a trend is only reported/charted as significant at **p < 0.05**, and Agent 5 separately re-checks that any "significant" trend has at least `MIN_TREND_SAMPLE_SIZE = 10` data points — a p<0.05 fit on 4–5 points is noise, not a trend.
- **Cross-dimensional analyses** (dataset-shape-gated, not hardcoded to any one dataset): discount vs. return rate, margin-by-category-over-time, discount/margin by sales rep, average order value by segment, shipping cost by region, shipping lead-time analysis.

**Chart selection & the `chart_planner`**: rather than always drawing the same fixed chart set, `chart_planner.py` **scores every candidate visualization by statistical effect size** — ANOVA η² for "does this category actually explain variance in the metric", Pareto concentration (top-1/top-3 share) for "is this genuinely concentrated", skew/outlier interest for distribution charts, r² for trend charts, Cramér's V for categorical-categorical association — so the same code produces a *different, relevant* chart set on a sales dataset vs. an HR dataset vs. a support-ticket dataset. All candidates (planner + legacy) are pooled and only the top `MAX_CHARTS_PER_REPORT = 16` by score survive; the rest are deleted from disk, not just hidden.

**Chart rendering guarantees**: every PNG is capped at 1600px per side regardless of how many categories/periods drove its size; axis tick labels are thinned/rotated once there are more than a handful, so a dataset with hundreds of categories never produces an illegible wall of overlapping text.

### Agent 5 — Output Validation & Trust Gate ([agent_5.py](backend/agents/agent_5.py))
**Purpose**: The safety gate. Runs **after** Agent 4, **before** Agent 6 is allowed to write anything. **Zero LLM cost** for its main checks.

**Two tiers**:
- **Tier 1 — deterministic contract checks** (always run): row/column reconciliation against Agent 3's own row-accounting ledger; every schema column present in `cleaned_df` (or its documented canonical replacement); quality score within [0,100]; every descriptive stat finite and every correlation coefficient within [-1,1]; every chart file on disk and non-empty; business-rule failure rate under `MAX_VALIDATION_FAIL_PCT = 15%`; category-normalization safety (no fuzzy merge changed >5% of rows or merged two independently-common values); trend sample sufficiency (no "significant" trend below 10 points).
- **Tier 2 — Cohen's kappa** — computed **from scratch in pure Python** (no sklearn dependency) between Agent 2's LLM-assigned `intended_type` and the independent local heuristic sniffer, both coarsened to `{numeric, datetime, boolean, string, unknown}`. This requires **no ground-truth human labels** — it's an internal-consistency check: if the LLM's semantic judgment routinely disagrees with the mechanical type-sniffing baseline, that's evidence the schema needs manual review, gated at κ ≥ 0.4 ("fair" agreement, Landis & Koch 1977 scale).

**Gating logic**: `overall_validation_score = 100 × (passed + 0.5×warned) / total_checks`; `passed = (failed_checks == 0)`. If `passed` is False, `pipeline.py`'s conditional edge (`should_continue_after_agent5`) routes straight to `END` — **Agent 6 never runs.** This is the literal implementation of "don't let an LLM write a report on top of data the pipeline itself doesn't trust."

**Why this matters for the defense**: this is the single most defensible design decision in the whole project — it's the direct architectural answer to "how do you stop this from hallucinating," and it costs zero extra API calls to run.

### Agent 6 — Insight Report Generator ([agent_6.py](backend/agents/agent_6.py))
**Purpose**: Turn everything Agents 1–5 computed into a human-readable report, with the LLM used only for wording, never for numbers.

**Pipeline**:
1. **`_extract_insight_facts()`** — pulls a large, fully-deterministic fact dictionary out of `state` (shape, quality, correlations, growth, rankings, anomalies, regression, validation, reliability, chart summaries). This dictionary is the **only source of truth** the narrative is allowed to cite.
2. **LLM narrative call** (Groq → Gemini fallback → deterministic fallback) using a strict system prompt that instructs the model to write an executive summary, key findings, a three-part story (*What happened / Why it matters / What to do next*), recommendations, risks, and chart captions — **grounded only in the facts it's given**, in plain language, jargon explained inline.
3. **Hybrid composition (`_compose_hybrid_narrative`)** — the deterministic, fact-derived narrative (`_fallback_narrative`) is **always computed first as a guaranteed floor**. The LLM's version is layered on top of it *only where it passes hygiene checks*: no undefined chart IDs in captions, no unexplained jargon (checked against a jargon-pattern list + a dynamic glossary), a validly-shaped 3-part story. If the LLM's `bottom_line` or `story` contains jargon, the deterministic version silently replaces it — the report can never look worse than the guaranteed deterministic baseline, and it degrades gracefully rather than failing.
4. **Claim grounding (`_check_narrative_grounding`)** — every numeric-looking token in the LLM's prose is regex-extracted and checked against the flattened set of every number appearing in `insight_facts`, within an absolute+relative tolerance. Ungrounded claims are flagged, logged, and factored into Agent 6's own confidence score. Sample run: 21/21 grounded.
5. **Contradiction detection** — a separate pass scans the narrative for internally inconsistent statements (e.g. claiming data is both "complete" and "has significant gaps").
6. **Recommendation grounding (`_ground_recommendations`)** — recommendations must tie back to at least one actual reported finding, not be generic boilerplate.
7. **Dynamic glossary** — jargon terms that actually appear in the *rendered* text get a plain-language definition inline (`_build_dynamic_glossary`), built from a fixed base glossary plus terms the LLM itself introduced.
8. **Rendering**: Jinja2 template (`templates/insight_report.html.jinja`) → self-contained HTML (charts embedded as base64 PNGs) → PDF via WeasyPrint **if** its native libraries are available on the host, else the HTML is served as-is (this is exactly what happened on the report's own test machine — be ready to say "the code supports PDF, the demo machine just didn't have WeasyPrint's system libraries installed").

**Report structure**: KPI hero cards → "In Plain English" box → 3-part story → narratively-grouped chart sections → technical appendix in collapsible `<details>` → inline glossary.

**Agent 6's own confidence score**: 0.95 if the narrative came from the LLM path and passed hygiene checks, 0.55 if it fell back to pure-deterministic wording, then scaled down further by the claim-grounding confidence (`0.7 + 0.3 × grounding_confidence`) — so a report where the LLM contributed but got some numbers wrong scores lower than one where it contributed cleanly.

---

## 5. Backend, frontend, and infrastructure (for completeness/API questions)

- **Backend** (`backend/api/`): FastAPI app; routes for `analysis` (submit a job, `GET /stream` SSE progress, `GET /result`), `jobs` (list/delete), `reports` (serve HTML/PDF + chart images), `chat` (RAG dataset Q&A), `auth` (signup/login/logout), `settings` (per-user API-key management), `health` (incl. an LLM connectivity test endpoint).
- **Job orchestration**: `job_manager.py` runs the LangGraph pipeline per uploaded file in the background and streams progress via **Server-Sent Events**, so the frontend shows live per-agent progress rather than a spinner.
- **Per-user API keys**: users can supply their own Groq/Gemini keys via `settings`; these are AES-encrypted at rest (`.encryption_key`) and take priority over the shared server-side key for that user's jobs (`request_context.get_api_key_override`) — captured via a thread-local so concurrent jobs never leak one user's key usage into another's.
- **API-key usage transparency** (`agents/key_indicator.py`): every LLM call an agent makes is recorded (provider, a SHA-256 **fingerprint** of the key — never the key itself, model, purpose) and surfaced to the frontend, so a user can see exactly where and how many times their key was used.
- **RAG dataset chat** (`api/services/rag_service.py`): optional (needs PostgreSQL + pgvector + a Hugging Face token). Embeds row-level documents from the uploaded CSV *and* fact documents from the deterministic analysis result using `BAAI/bge-base-en-v1.5`; broad analytical questions stay grounded because fact-type documents (summaries, correlations, rankings, anomalies) are always included regardless of vector-similarity rank, not just the top-K nearest row documents. Answer generation: Groq → Gemini → deterministic fallback, same failover pattern as the main pipeline.
- **Frontend** (`frontend/AnalyzeAI/`): React 19 + Vite 8 + Tailwind CSS v4 + Framer Motion + React Router v7 (app name **AnalyzeAI**). Talks to the backend over the REST/SSE API described above.
- **Deployment**: `render.yaml` present — designed for Render.com-style deployment (backend service + optionally a managed Postgres for RAG).

---

## 6. Results snapshot (quote these numbers verbatim if asked)

Full pipeline run on `10000 Sales Records.csv` (10,000 rows × 14 columns):

| Agent | Result |
|---|---|
| 1 | Profiled 10,000×14; 0.0% missing, 0 duplicates |
| 2 | 14-column schema blueprint; type-sniffing vs. LLM agreement κ=1.0 |
| 3 | profile=`strict`, domain=`finance_sales`; 10,000×14 → 10,000×58; quality 100.0/100 |
| 4 | 22 descriptive columns; 10 correlation pairs |r|≥0.5 (strongest: Unit Price vs Unit Cost, r=0.99); 52 anomalous rows (0.52%); 8 regression candidates, **0** met the significance+sample-size bar; 16 charts |
| 5 | 9/9 Tier-1 checks passed; validation score 100/100; κ=1.0 |
| 6 | Narrative source = Groq; 21/21 claims grounded; report written (HTML; PDF needs WeasyPrint native libs) |

**Overall reliability**: mean confidence **0.97**, `decision_readiness = "ready"`.

**Head-to-head vs. a general-purpose Qwen chat model given the same CSV and asked to "analyze this"**:

| Dimension | This pipeline | Plain Qwen chat |
|---|---|---|
| Runtime | ~52 s | ~4 min 12 s (**4.8× slower**) |
| Numerical accuracy | Exact vs. source data | **10× scaling error** ($1.33B reported instead of $13.33B) |
| Self-validation | 23/23 figures cross-checked, confidence 1.0 | None |
| Statistical depth | Pearson/Spearman w/ tautology filtering, skew-aware anomaly detection, YoY/QoQ trends, cross-dimensional breakdowns | High-level totals/top-N only, no outlier or correlation analysis |
| Data quality | Duplicate/missing handling, anomaly $ impact ($412K/52 rows), 100/100 validation | No data-quality section |
| Traceability | Every figure reproducible from deterministic pipeline output | Not reproducible from the summary alone |
| Output | 27-page structured report w/ appendix + glossary | ~5-section Markdown summary |

**Why this comparison matters**: it's your strongest single talking point. It's not "our system uses AI," it's "we measured that separating deterministic computation from language generation prevents a specific, quantified 10× numerical error that a single-LLM approach produced on the exact same data."

**RAG chat retrieval quality** (K=8, on the same sample dataset): Precision@8 = 0.5938, nDCG@8 = 0.6227, MRR@8 = 0.7500 (Recall@8 is naturally tiny — 0.0049 — because the corpus has thousands of row-documents and only a handful are truly relevant per query; recall is not the right metric for retrieval among that many candidates, precision/nDCG/MRR are).

---

## 7. What to say about limitations (don't get caught off guard)

Be upfront about these — examiners respect "we know this isn't done" far more than a system that pretends everything is finished:

- **API-level file formats**: the *web upload route* only accepts CSV today; Excel/JSON/Parquet are supported in Agent 1's loader but not yet wired to the frontend upload — a scoped, honest future-work item, not a hidden bug.
- **Token/latency metrics aren't persisted yet** — the API-key usage tracker records *which* provider/model/key was used, but not prompt/completion token counts or per-call latency. The report is explicit that it does not claim numbers it can't measure.
- **No forecasting / predictive modeling** — the system is diagnostic (what happened, why) not predictive (what will happen). Regression here is trend detection, not a forecast model.
- **Auth is basic** — no OAuth2/OIDC, no RBAC, no multi-tenancy yet.
- **Single-dataset evaluation** — the numeric results above are from one representative sales dataset; a larger benchmark across 100+ diverse CSVs is future work, not yet done.
- **RAG recall is inherently low** at this corpus size/K — explained above, not a bug.

## 8. Future work (from the report — cite if asked "what's next")
1. Multi-format ingestion exposed at the API/upload level (not just internally).
2. Model-agnostic provider configuration (let users pick OpenAI/Anthropic/local Ollama models via settings).
3. More chart families (Sankey, treemap, geographic maps, time-series decomposition).
4. Proper OAuth2/OIDC + RBAC + multi-tenancy.
5. Larger-scale benchmarking (100+ datasets) for accuracy/speed/reliability across domains.
6. Interactive report customization (user picks chart types/tone).
7. Continuous learning from user corrections (e.g. fixing a mistagged column feeds back into future tagging).

---

## 9. If they ask "what's the one thing that makes this different from just using ChatGPT on my CSV?"

Say this: *"A single LLM asked to analyze a CSV has no separation between the part that's supposed to be exact (arithmetic, correlations, totals) and the part that's supposed to be fluent (explaining what it means). Our architecture forces that separation structurally: agents 1, 3, 4 and the Tier-1 half of agent 5 never call an LLM at all — every number in the final report is plain deterministic Python. The LLM only touches two things: guessing what a column means (agent 2), and writing the prose around numbers it's handed (agent 6) — and even there, we independently score its agreement with a heuristic baseline (Cohen's kappa) and grep its own sentences for numbers that don't match the facts before the report ships. That's the direct, measured reason our numbers were exact and the plain-LLM baseline was off by 10×."*

---

## 10. Quick run instructions (in case they ask you to demo)

```bash
cd backend
pip install -r requirements.txt
python pipeline.py
```
Runs the pipeline end-to-end on `backend/claude_data1.csv` (the default in `pipeline.py`'s `__main__` block) and prints a per-agent summary plus writes `outputs/agent_run_diagnostics.json`.

For the full web app: run the FastAPI backend (`backend/run.py` / `uvicorn`) and the frontend (`cd frontend/AnalyzeAI && npm run dev`).

---

*See [MAGIC_NUMBERS.md](./MAGIC_NUMBERS.md) for every hardcoded constant and its justification, and [VIVA_QUESTIONS.md](./VIVA_QUESTIONS.md) for ~500 rehearsed Q&A across every topic above.*
