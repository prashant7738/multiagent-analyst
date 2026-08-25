# FINAL REPORT UPDATE SPECIFICATION
### Multi-Agent Data Analysis and Insight Generation Platform for Financial and Sales Data
**IOE, Thapathali Campus — Minor Project (Final Report Build Specification)**

> **PURPOSE OF THIS DOCUMENT.** This is **not** the final LaTeX report. It is a complete, self-contained blueprint that a second AI can use to transform the existing mid-defense report (`reportfolder/report.tex`) into the **final** submission. It records: what to keep, what to correct, what to expand, what to add; the exact implemented facts, formulas, tables, figures, screenshots, and code evidence extracted from the actual project; and a section-by-section master plan.
>
> **SOURCE OF TRUTH RULE.** The **actual implemented code** is authoritative. Where the existing report contradicts the code, the contradiction is flagged. Nothing here is invented; any unverifiable item is explicitly marked **NOT VERIFIED / DO NOT CLAIM**.

---

## 0. CRITICAL CORRECTIONS (READ FIRST — these change the whole report)

These are contradictions between the current mid-term report and the real codebase. They must be fixed everywhere they occur (title page, abstract, requirement-status table, implementation snapshot, results, conclusion, remaining-tasks chapter).

| # | Current report claims | Actual implementation (source of truth) | Action |
|---|---|---|---|
| C1 | Title page: **"A MINOR PROJECT MID-TERM PROGRESS REPORT"** | This is now the **final** report. | Change to **"A MINOR PROJECT REPORT"** (drop "MID-TERM PROGRESS"). Keep everything else on the title page unchanged (see §1). |
| C2 | Abstract & multiple chapters: *"the first four agents are implemented"*, *"Agent 5 and Agent 6 are not yet implemented"*, *"planned"* | **All six agents are fully implemented and wired into the LangGraph pipeline** (`backend/pipeline.py` builds agent1→…→agent6). Agent 5 = `backend/agents/agent_5.py` (445 lines), Agent 6 = `backend/agents/agent_6.py` (1900 lines). | Rewrite all "planned/in-progress" language to describe a **complete end-to-end** system. |
| C3 | Chapter 4 (Theoretical Approach) is built entirely around **`llama-3.3-70b-versatile`** with Llama-3-specific GQA/RoPE/SwiGLU/RMSNorm and cites `dubey2024llama3`. | The active model is **`qwen/qwen3.6-27b`** on Groq (Llama 3.3 was **deprecated by Groq 2026-08-16**; see `agent_2.py` line 267 comment), **with an automatic Google **Gemini** fallback** (`gemini-flash-latest` → `gemini-3.6-flash` → `gemini-3.5-flash` → `gemini-2.5-flash`). Reasoning model run with `reasoning_effort="none"`. | Update Chapter 4 to describe **Qwen3-27B** as the primary model and the **dual-provider Groq→Gemini failover**. The generic decoder-only theory (attention, GQA, RoPE, SwiGLU, RMSNorm) still applies to Qwen3, so equations stay; only the model name, parameter count, provider description, and citation change. **DO NOT keep claiming Llama 3.3 70B is the model in use.** |
| C4 | Report describes only the **backend pipeline**; frontend "Planned", no API layer mentioned. | A full **FastAPI backend** (`backend/api/`) and a **React 19 + Vite + TailwindCSS frontend** (`frontend/AnalyzeAI/`) are implemented, including JWT-style auth, SSE progress streaming, PostgreSQL/file job persistence, report download, and a grounded **RAG dataset-chat**. | Add new chapters/sections for the backend API, SSE, storage, and frontend (see §4 master plan). |
| C5 | "Amazon Sales Dataset" is named as the working dataset in Chapter 5. | The repository's committed sample is **`10000 Sales Records.csv`** (10,000 rows × 21 cols) and test fixtures reference sales/finance CSVs. The pipeline default in `pipeline.py __main__` reads `claude_data1.csv`. | Verify which dataset was actually used for the final results screenshots. Use **`10000 Sales Records.csv`** for the reproducible results unless the team confirms otherwise. **NOT VERIFIED: that the mid-term "Amazon Sales Dataset" results still match — regenerate.** |
| C6 | Requirement-status / snapshot tables mark Agent 5, Agent 6, Frontend, Multi-format as "In progress / Planned". | All implemented except **multi-format ingestion is CSV-first** (API restricts uploads to `.csv`; Agent 1 also has an Excel loader path). | Flip statuses to "Implemented"; keep multi-format as partially done / CSV-primary (see §8). |
| C7 | Abbreviations list is Llama-centric (RoPE, GQA, KV) and omits new tech. | New components: FastAPI, SSE, RAG, JWT, pgvector, ORM/PostgreSQL, Vite, ECharts, WeasyPrint, Jinja2, MAPE, OLS, IQR, KS, MAD. | Extend the List of Abbreviations (see §1). |

**Fixed information that MUST remain unchanged** (verified in `report.tex`): project title, the four authors and roll numbers (Prashant Kafle THA080BCT026, Roshan Poudel THA080BCT036, Santosh Khadka THA080BCT039, Sushil Bhatta THA080BCT048), supervisor **Er. Rajad Shakya**, Department of Electronics and Computer Engineering, Thapathali Campus, and the LaTeX document class / geometry / heading styling.

---

## 1. EXISTING REPORT ANALYSIS (front matter + fixed content)

**Code evidence:** `reportfolder/report.tex`.

### Keep unchanged (KEEP)
- **Preamble / styling** (lines 1–110): `documentclass[12pt,a4paper]{report}`, geometry `left=1.5in,right=1in,top=1in,bottom=1in`, `mathptmx` (Times), `titlesec` heading formats, `tocloft`, listings `pystyle`, `\onehalfspacing`, fancy footer page numbers. This already matches the IOE Thapathali guidelines (Times New Roman, A4, 1.5" left margin, centered bottom page numbers, roman prefatory + arabic body). **Do not restyle.**
- **Title page block** (the `titlepage` environment): logo `tulogo.png`, university lines, submitted-by authors, submitted-to department. **Only** change the report-type line (C1) and the date if the team wants (currently "July 2026").
- **Acknowledgement** — keep; optionally update tense (project now complete).
- **Declaration / Certificate / Copyright pages**: The current `report.tex` does **not** contain Declaration, Certificate of Approval, or Copyright pages, but the IOE template requires them. **NEW (see below).**

### Modify (MODIFY)
- **Abstract** — currently states only four agents implemented and Agents 5–6 planned. **Rewrite** to describe the complete six-agent pipeline + FastAPI backend + React frontend + validation + HTML/PDF reporting + dataset chat. Keep it one dense paragraph + keyword line. Add keywords: *Cohen's kappa, FastAPI, RAG, React, Server-Sent Events, WeasyPrint*.
- **List of Abbreviations** — ADD: CORS, ECharts, FastAPI, IQR, JWT, KS (Kolmogorov–Smirnov), MAD, MAPE, MoM, OLS, ORM, PDF, pgvector, QoQ, RAG, REST, SSE, UUID, Vite, WeasyPrint. May REMOVE Llama-only ones if Chapter 4 no longer needs them, but GQA/RoPE/KV still apply to Qwen3 so they can stay.

### NEW prefatory pages (add to match template ordering)
1. **DECLARATION** — signed statement by the four authors (template page i).
2. **CERTIFICATE OF APPROVAL** — supervisor (Er. Rajad Shakya), external examiner, coordinator, HoD signature blocks (template page ii).
3. **COPYRIGHT** — standard IOE Thapathali copyright paragraph (template page iii).

Ordering (per template): Cover → Title → Declaration (i) → Certificate (ii) → Copyright (iii) → Acknowledgement (iv) → Abstract (v) → Table of Contents → List of Figures → List of Tables → List of Abbreviations → body.

---

## 2. FINAL REPORT TEMPLATE ANALYSIS (structural reference only)

The IOE Thapathali template prescribes this chapter skeleton (do **not** copy its filler text):

1. **INTRODUCTION** — Background, Motivation, Problem Definition, Objectives, Scope & Applications, **Report Organization** (the current report is missing an explicit *Report Organization* subsection — ADD it).
2. **LITERATURE REVIEW** — existing works, each cited.
3. **REQUIREMENT ANALYSIS** — software requirements + feasibility study + dataset analysis.
4. **SYSTEM ARCHITECTURE AND METHODOLOGY** — block diagram + flowcharts/algorithms.
5. **IMPLEMENTATION DETAILS** — how each module functions and interconnects.
6. **RESULTS AND ANALYSIS** — real outputs in tables/graphs/charts with discussion + error analysis/validation.
7. **FUTURE ENHANCEMENT** (template shows this as its own chapter).
8. **CONCLUSION**.
9. **APPENDICES** — dataset details, cost, timeline, sample outputs.
10. **REFERENCES** (IEEE, ascending order, not chapter-numbered).

**Gaps in current report vs template:**
- Missing **Declaration/Certificate/Copyright** (add — §1).
- Missing **Report Organization** subsection in Chapter 1 (add).
- Missing an explicit **Feasibility Study** subsection in Requirement Analysis (add: technical/operational/economic — the project is open-source + usage-priced LLM APIs, so economically feasible).
- **Results & Analysis** currently has no real numbers/figures — must be populated with actual pipeline outputs (§9).
- **Future Enhancement**: current report has a "REMAINING TASKS" chapter that lists Agents 5/6 as unbuilt — REPLACE with a genuine **Future Enhancement** chapter (multi-format ingestion, more chart families, model-agnostic provider config, deployment).

---

## 3. IMPLEMENTED SYSTEM — GROUND TRUTH (complete technical reference)

This section documents exactly what the code does, so the writer never has to re-read the repo.

### 3.1 Orchestration — LangGraph pipeline
**Code:** `backend/pipeline.py`, `backend/main.py`.

- Built with `langgraph.graph.StateGraph(GraphState)`. Nodes: `agent1..agent6`. Entry point `agent1`.
- **Conditional edges** gate the flow (functions `should_continue_after_agentN`):
  - after **agent1**: end if any error containing "Agent1" or no `raw_profile`, else → agent2.
  - after **agent2**: end if "Agent2" error or no `schema_blueprint`, else → agent3.
  - after **agent3**: end **only** if `cleaned_df is None` (non-fatal "Agent3:" warnings do **not** abort — important nuance), else → agent4.
  - after **agent4**: end if "Agent4" error, else → agent5.
  - after **agent5**: end if "Agent5" error **or** `validation_report["passed"]` is falsy — i.e. **Agent 5 is a hard quality gate**: a failed validation stops the pipeline before reporting, else → agent6.
  - **agent6** → END.
- `_write_run_diagnostics()` dumps a full per-run JSON (`outputs/agent_run_diagnostics.json`) capturing every agent's outputs, errors, and reliability — good screenshot/appendix material.

**`GraphState` (TypedDict, `backend/main.py`)** — the shared state carrying: `csv_path`, `raw_profile`, `raw_shape`, `_df_cache`, `schema_blueprint`, `analysis_config`, `preprocessing_config`, `preprocessing_profile`, `dataset_domain`, `cleaned_df`, `cleaned_csv_path`, `scaling_params`, `preprocessing_log`, `data_quality`, `column_ledger`, `category_normalization`, `rule_manifest`, `stats`, `chart_paths`, `chart_specs`, `run_id`, `validation_report`, `insight_facts`, `insight_narrative`, `report_path`, `errors`, `reliability`.

**Reliability model (`update_reliability`, `main.py`):** every stage contributes a confidence in [0,1] into `reliability.stage_confidence[stage]`; `overall_confidence` = mean of stage confidences; `decision_readiness` = `ready` (≥0.85), `needs_review` (≥0.65), `blocked` (<0.65). Evidence strings accumulate. **This is a real, implemented confidence-propagation mechanism — a headline feature for the report.**

### 3.2 Agent 1 — Structural Profiler
**Code:** `backend/agents/agent_1.py` (542 lines). *(Existing Chapter 5.1 already correct — keep, minor expansion.)*
- Loads CSV/Excel; **resilient mixed-delimiter CSV** ingestion `_read_mixed_delimiter_csv` (per-line `;` vs `,` detection with fallback), multi-encoding `_read_csv_lines` (`utf-8-sig`, `cp1252`, `latin-1`).
- Per-column profile: dtype, missing count & `missing_rate_pct`, unique count, first 3 samples. Dataset: shape, total cells, overall missing rate, duplicate rows/rate.
- **Confidence:** `c1 = clamp(1 − 0.5·m/100 − 0.3·d/100, 0, 1)` where m=missing %, d=duplicate % (Eq. already in report — keep).
- Captures `raw_shape` once at ingestion — the single source of truth for "raw" row/col counts used by Agent 6.

### 3.3 Agent 2 — Semantic Tagger (LLM)
**Code:** `backend/agents/agent_2.py` (1608 lines). *(Existing Chapter 5.2 mostly correct — MODIFY model facts per C3.)*
- Local heuristic `_infer_intended_types` (Pandas dtype + 80% parseability threshold) seeds prompt and fallback.
- **Model constants (line 267–279):** `GROQ_MODEL = "qwen/qwen3.6-27b"`, `GROQ_REASONING_EFFORT = "none"`, `GEMINI_MODEL = "gemini-flash-latest"`, `GEMINI_MODEL_FALLBACKS = ("gemini-3.6-flash","gemini-3.5-flash","gemini-2.5-flash")`. Temperature low (~0.1). **Batched** LLM calls with recursive halving on parse failure for wide schemas; TPM-aware batch sizing (Groq on-demand tier caps ~8000 tokens/min). Schema-response cache keyed by model + batch size + system prompt + payload.
- Defensive JSON parsing `_parse_schema_blueprint_response` (raw/fenced/outermost-brace); conservative `_fallback_blueprint` from sniffed types.
- Output `schema_blueprint`: per-column `intended_type`, `semantic_tag`, identifier flag, `analysis_allowed` (false if missing >20%), `null_policy`, `encoding_strategy`, confidence 0–100, `__metadata__` block.
- **Gemini failover** `_call_gemini_json_with_failover` iterates model candidates.

### 3.4 Agent 3 — Context-Aware Preprocessor
**Code:** `backend/agents/agent_3.py` (2162 lines). *(Existing Chapter 5.3 correct but INCOMPLETE — EXPAND with the items below.)*

**Preprocessing profiles** (`_build_preprocessing_config`) — table to add to report:

| Profile | currency_max_abs | max_tax_rate | recon_rel_tol | recon_abs_tol | quality weights (null / valfail / dup) |
|---|---|---|---|---|---|
| strict | 1.1e9 | 0.30 | 0.01 | 0.50 | 0.55 / 0.35 / 0.10 |
| balanced | 1.0e9 | 0.40 | 0.02 | 1.0 | 0.50 / 0.40 / 0.10 |
| lenient | 1.0e10 | 0.60 | 0.05 | 2.0 | 0.40 / 0.30 / 0.30 |

- **Domain detection** `_detect_dataset_domain` → "finance_sales" (⇒ strict) when ≥3 finance name hits {amount,revenue,cost,tax,price,discount,sales,profit,margin,invoice} OR ≥2 semantic-tag hits {currency,percentage}; else balanced.
- **Ordered steps (0–9):** dedup (with `_assert_row_survival_or_abort` if <50% survive) → currency cleaning → type coercion (`format="mixed"` for datetimes — fixes silent NaT, known-issue #1) → text standardisation + re-dedup → imputation → encoding → outlier clipping → scaling → date features → business metrics. Then validation + quality score.
- **Imputation strategies (ALL implemented, `_impute`):** mean, median, mode, `unknown_label` ("Unknown"), **forward_fill** (`ffill`), **KNN** (`sklearn.impute.KNNImputer`), **iterative/multivariate** (`sklearn.impute.IterativeImputer`), `drop_rows`, `drop_column`, `flag_only`, `none`. Strategy chosen per column from `null_policy.action` (Agent 2). **Currency/financial columns block imputation** regardless of policy. Multivariate imputer results cached across eligible (numeric, non-id, non-datetime, non-currency) columns. **⇒ report currently only lists mean/median/mode/unknown/flag/drop — ADD KNN, iterative, forward-fill.**
- **Adaptive outlier clipping** `_clip_outliers`/`_adaptive_outlier_clipping`: default **IQR 1.5×** (`lower=Q1−1.5·IQR`, `upper=Q3+1.5·IQR`); switches to **percentile clipping** when the raw profile shows significant outliers/skew/high risk — critical 1–99, high 5–95, moderate 2.5–97.5. Keeps `{col}_raw` and `{col}_was_clipped`. Skips currency/financial/datetime/identifier (known-issue #1 fix).
- **Scaling** `_scale_columns`: **Min-Max only** `x' = (x−min)/(max−min)`; stores `scaling_params[col]={min,max,raw_col,scaled_col}`; keeps `_raw`/`_scaled`. Never scales currency/financial/datetime/identifier/count/constant columns.
- **Encoding:** one-hot (`pd.get_dummies`) when cardinality ≤ 10; **top-8 + "Other"** bucket when higher; ordinal when `encoding_strategy.order` present (`{col}__ordinal`, Int64); safety-skip if cardinality/rows > 0.5.
- **Currency parsing** `_normalize_currency_text`: accounting negatives `(123)→−123`; strips symbols ₹$€£¥₩ and codes (RS/USD/EUR/GBP/INR/AUD/CAD/JPY/CNY/RMB/YEN/WON); **European vs US decimal resolution** by comparing last comma/dot positions; null-string normalisation (14+ variants). *(Code figure already in report — keep.)*
- **Fuzzy category normalisation** `_build_canonical_category_map`: **Levenshtein** merges with guards `FUZZY_MATCH_MIN_LENGTH=6`, `FUZZY_MATCH_MAX_DISTANCE=2`, first-char match, source ≤5% rows (`FUZZY_REVIEW_ROW_PCT`) and ≤1% rare (`FUZZY_RARE_VALUE_PCT`), skip if ≤3 distinct values. Logs `merges` and `flagged` (ambiguous → manual review) into `category_normalization`. **NEW content.**
- **Derived business metrics** `_derive_business_metrics` (whole-word `_find_col`): profit, profit_margin_pct, revenue_per_unit, days_to_ship, total_revenue, revenue_after_discount, discount_pct, budget_variance, budget_variance_pct, total_cost, total_cost_with_tax, total_spend. (Formulas in §6.)
- **Derived-metric reconciliation** `_reconcile_derived_metrics` vs any ground-truth column: requires Pearson r ≥ 0.99, MAPE ≤ 1.0%, ≥5 pairs, else marked `diverged`. **NEW content — a real hallucination/consistency guardrail.**
- **Quality score** `_compute_enhanced_quality_score` (§6, Eq.).
- **Validation** `_validate_count_ranges`, `_validate_financial_constraints` → `ColumnLedger` (`_range_failed`/`_rate_failed`/`_reconciliation_failed`/`_parse_failed` flags, `row_accounting`).

### 3.5 Agent 4 — Statistical Analysis & Visualization
**Code:** `backend/agents/agent_4.py` (2293 lines), plus `chart_planner.py`, `chart_spec.py`, `echarts_options.py`, `chart_render_static.py`, `key_indicator.py`. *(Existing Chapter 5.4 correct but INCOMPLETE — EXPAND.)*
- **Column selection / leakage** `flag_leakage_columns`: name patterns ({classifier, naive_bayes, _score, _proba, predicted_, id, index, clientnum, customerid, _uuid}; whole-word for short {id,index}); correlation signature (|r|>0.98 with exactly one column AND |r|<0.1 with ≥n−2 others); uniqueness == row count. **NEW: leakage/ID exclusion is a real feature.**
- **Descriptive stats** `_descriptive_stats`: count, mean, median, std, variance, min, max, q1, q3, skewness, kurtosis (rounded 4dp).
- **Correlation** `_correlation`: Pearson **and Spearman** matrices; strong pairs |r|≥0.5 (labelled *strong* ≥0.7, *moderate* 0.5–0.7); separates **formulaic** pairs (derived-from) and **excluded** (leakage) pairs from genuine business pairs; heatmap only if max|r|≥0.3.
- **Growth rates** `_growth_rates`: MoM `monthly.pct_change()×100`, QoQ `quarterly.pct_change()×100`; grain downshifts to yearly if >40 points.
- **Rankings** `_top_bottom_rankings`/`_select_ranking_dimensions`: priority dims {region, category, segment, representative} get guaranteed slots (if 2≤nunique≤20), others by revenue-share spread, up to 6 dims; share% = group_sum/total×100. (Fixes known-issue #3/#4.)
- **Seasonality** `_seasonality`: monthly averages, best/worst month, relative spread.
- **Anomaly detection** `_detect_anomalies`: skew-aware — |skew|≤1.0 ⇒ z-score `z=(x−μ)/σ`, flag |z|>3.5; |skew|>1.0 & positive ⇒ log-z on `log1p(x)`; heavy-skew/negatives ⇒ IQR with **3.0×** far-out fence. Reports per-column anomalies + unique affected rows + business-impact totals; quality tolerance 3% then 0.1×/pct penalty (cap 5.0).
- **Structural data-quality issues** `_detect_data_quality_issues`: rolls up Agent 3 flags + count/percentage/return-quantity rule checks; review if ≥90% rows hit a rule; penalty 1.5×/pct (cap 40).
- **Regression trends** `_regression_trends`: **OLS via `scipy.stats.linregress`** → slope, intercept, `r_squared = r²`, p_value, significant if p<0.05, records `n`; time axis `x = year·12 + month` when available.
- **Cross-dimensional analyses (6):** discount_return_rate, category_margin_trend, rep_discount_margin, segment_order_value, region_shipping_cost, shipping_lead_time — each empty-safe when required columns absent. **NEW.**
- **Charts:** dual-target — interactive **ECharts** option JSON + static **matplotlib** PNG twin. Chart types: bar, barh, line, scatter, histbox, heatmap, pareto. Size cap `MAX_CHART_DIM_PX=1600`, DPI auto-fit, x-tick thinning >40 labels, `safe_filename_component` filename safety, overwrite-clean per run. `_clear_chart_dir` resets `outputs/charts` each run.
- **Chart planner** (`chart_planner.py`): signal-strength scoring — ANOVA **η²** for dimension rankings (skip <0.08), Pareto concentration `0.6·top1%+0.4·top3%` (skip <30), distribution `|skew|+outliers`, trend `r²·100`, seasonality CV, scatter `|r|·100`, crosstab **Cramér's V** `√(χ²/(n·min(r−1,c−1)))`, anomaly density. `finalize_specs` dedups + sorts by priority + caps at 10. `SECTION_BY_FAMILY` groups charts into what_matters / shape / direction / relationships / watchlist.

### 3.6 Agent 5 — Output Validation & Trust Gate
**Code:** `backend/agents/agent_5.py` (445 lines). **ENTIRELY NEW — report says "not implemented".**
- **Tier 1 — deterministic contract checks** (no LLM): row-reconciliation (row_accounting vs cleaned_df), schema↔dataframe consistency, quality-score bounds [0,100], stats numeric sanity (finite descriptive, correlations in [−1,1]), chart artifact integrity (files exist & non-empty), business-rule validation (worst failure ≤ `MAX_VALIDATION_FAIL_PCT=15%`), category-normalization safety (reject merges changing >5% rows or merging two frequent values), trend sample sufficiency (significant trends need n ≥ `MIN_TREND_SAMPLE_SIZE=10`).
- **Tier 2 — Cohen's kappa** (`_cohen_kappa_score`, pure Python, no sklearn): agreement between Agent 2's LLM `intended_type` and the heuristic sniffer, coarsened to {numeric, datetime, boolean, string}. Threshold `MIN_ACCEPTABLE_KAPPA=0.4` ("fair", Landis & Koch). A ground-truth-free trust signal for the LLM tagging.
- **Scoring:** `overall_validation_score = 100·(passed + 0.5·warned)/total`. `passed = (failed_checks == 0)`. `passed` gates Agent 6.
- **Confidence** `_validation_confidence`: base = score/100, ×0.5 if review required, −0.05 per insufficient trend (cap −0.25). `ValidationLedger` records pass/warn/fail with detail; `flagged_issues` list.

### 3.7 Agent 6 — Insight Report Generator
**Code:** `backend/agents/agent_6.py` (1900 lines) + `report_style.py` + `templates/insight_report.html.jinja`. **ENTIRELY NEW.**
- **(1) Deterministic fact extraction** (`_extract_insight_facts`, no LLM): dataset shape, **shape-change transparency** (why cleaned cols/rows differ — categorised by one-hot/ordinal/derived/date-feature/audit-trail/validation-flag), quality facts, per-column missing-value actions **reconciled against reality** (won't claim an imputation that didn't run), top correlations (excluding leakage/formulaic), growth, rankings, profit breakdown, cross-dimensional, category normalisation, anomalies, significant trends, validation facts (incl. Cohen's kappa), reliability, chart summaries.
- **(2) LLM narrative** (`_call_llm_for_narrative`): Groq `qwen/qwen3.6-27b` → **Gemini fallback** → deterministic fallback. Strict system prompt: use ONLY given facts; raw shape must be raw_rows/raw_cols; **jargon-free** plain-language section for non-technical readers; returns JSON with executive_summary, key_findings, story (what_happened/why/next), chart_captions, glossary_terms, plain_language_insights, bottom_line, risks_and_caveats, recommendations. Prompt facts progressively compacted to stay under `MAX_NARRATIVE_PROMPT_CHARS=7000` (Groq TPM).
- **(3) Hybrid composition** (`_compose_hybrid_narrative`): deterministic floor **always** renders; LLM output layered on only where it passes hygiene (valid story, no jargon via `_JARGON_PATTERNS`, known chart ids). `_lint_plain_language` swaps residual jargon back to deterministic wording.
- **(4) Claim grounding** (`_check_narrative_grounding`): every number in the narrative must match a computed fact within tolerance (`CLAIM_GROUNDING_TOLERANCE=1.0` or 5% of value); reports claims_checked/grounded/flagged and a grounding confidence. **A real anti-hallucination check.**
- **(5) Recommendation grounding** (`_ground_recommendations`): each recommendation must anchor to a reported finding + traceable money figures.
- **(6) Table-cell guarantees** (`_validate_no_empty_required_cells`) and **raw-column guard** (`_validate_raw_column_count`) fail loudly on empty required cells / shape drift.
- **(7) Rendering:** Jinja2 (`insight_report.html.jinja`) with base64-embedded PNGs + embedded **ECharts** option JSON for interactive charts; KPI hero cards; sections grouped narratively; **WeasyPrint** HTML→PDF, gracefully **falls back to HTML** if PDF libs unavailable. Output `outputs/reports/<run_id>/insight_report.{pdf|html}`.
- **Confidence:** 0.95 (LLM narrative) or 0.55 (fallback), ×(0.7+0.3·grounding).

### 3.8 FastAPI Backend
**Code:** `backend/api/`. **ENTIRELY NEW.**
- **App** (`app.py`, `create_app()`): routers health, auth, analysis, reports, jobs, chat; global 422/500 JSON handlers; root `GET /`. CORS via `middleware/cors.py`. Launched by `run.py` (uvicorn).
- **Config** (`config.py`, `Settings` via `@lru_cache`): env-driven — CORS origins, `uploads_dir`, `outputs/charts|reports`, max upload **50 MB**, allowed ext `{.csv}`, SSE poll 0.15s / keepalive 15s, max concurrent jobs 4, job TTL 3600s, PostgreSQL (`DATABASE_URL` or `POSTGRES_*`), tables `analysis_jobs`/`app_users`, RAG embedding model `BAAI/bge-base-en-v1.5` (768-dim), HF token.
- **Endpoints:**
  - `GET /api/health` → HealthResponse.
  - `POST /api/auth/signup` (201), `POST /api/auth/login` (200) → AuthResponse; passwords hashed with **passlib PBKDF2-SHA256**; users in PostgreSQL `app_users`.
  - `POST /api/analyze` (202, multipart CSV + `preprocessing_profile` + `analysis_config`) → `{job_id, status, stream_url, result_url}`; streamed size check.
  - `GET /api/analyze/{job_id}/stream` → **SSE** progress.
  - `GET /api/analyze/{job_id}/result` → AnalysisResult (409 failed / 425 not ready).
  - `GET /api/jobs`, `GET /api/jobs/{job_id}` → JobSummary.
  - `GET /api/report/{job_id}` → PDF/HTML FileResponse.
  - `GET /plots/{filename}` → PNG (path-traversal guarded).
  - `GET|POST /api/analyze/{job_id}/chat` → dataset Q&A (ChatResponse: answer, source groq|gemini|fallback, optional generated chart, index_status).
- **Job manager** (`job_manager.py`): thread-safe `Job` dataclass (status queued/processing/completed/failed, per-agent progress, append-only `events` for SSE, `state`, `result`, `chat_history`, `rag_status`), `threading.Condition` notify. Optional persistence: **PostgresJobStore** (JSONB columns) or **FileJobStore** (`outputs/analysis_jobs.json`, atomic writes).
- **Pipeline runner** (`pipeline_runner.py`): runs compiled LangGraph in a **daemon thread**, `pipeline.stream(..., stream_mode="values")`, `_MilestoneEmitter` emits SSE events per agent completion / charts_generated / validation_passed|failed / report_generated.
- **SSE** (`sse.py`): `event: <name>\n data: <json>\n\n`, replays past events, polls 0.15s, keepalive 15s, closes on terminal event; multi-subscriber safe.
- **RAG chat** (`rag_service.py` + `chat_service.py`): pgvector table `dataset_embeddings`, **BAAI/bge-base-en-v1.5** embeddings via HF Inference API, row-docs + fact-docs, background build thread, top-k retrieval (facts 6 / rows 8), grounded answers (no raw rows to LLM), Groq→Gemini→deterministic fallback, optional freshly generated chart.
- **Result builder** (`result_builder.py`): projects final state into frontend-friendly `AnalysisResult`; chart paths → `/plots/...` URLs; JSON-safe coercion.
- **API deps** (`requirements_api.txt` / `pyproject.toml`): fastapi, uvicorn[standard], python-multipart, pydantic, psycopg[binary], passlib[bcrypt], pgvector, huggingface-hub.

### 3.9 React Frontend
**Code:** `frontend/AnalyzeAI/`. **ENTIRELY NEW.**
- **Stack (package.json):** React **19.2.7**, react-dom 19.2.7, **react-router-dom 7.18.1**, **TailwindCSS 4.3.2** (+@tailwindcss/vite), shadcn 4.12.0, radix-ui 1.6.1, framer-motion 12.42.2, lucide-react, three 0.185.0, DM Sans/Geist/Space Grotesk fonts. Dev: **Vite 8.1.0**, @vitejs/plugin-react 6.0.2, oxlint. **No axios (native fetch), no charting lib (charts are backend PNGs/ECharts), no Redux (React Context only).**
- **Vite** (`vite.config.js`): react + tailwind plugins, alias `@`→`src`, backend base `VITE_API_BASE_URL` (default `http://localhost:8000`), dev on :5173.
- **Routing** (`App.jsx`, BrowserRouter): `/` LandingPage, `/analyze` + `/analyze/:jobId` (RequireAuth) AnalyzePage, `/history` HistoryPage, `/login`, `/signup`, `/profile`. `RequireAuth` redirects to `/login`.
- **API client** (`src/lib/api.js`): `analyzeCsv` (FormData), `subscribeToJobStream` (**EventSource** listening progress/csv_loaded/pipeline_started/charts_generated/validation_passed|failed/report_generated/pipeline_finished/completed/pipeline_failed/error), `fetchJobResult`, `fetchJobs`, chat, `reportDownloadUrl`.
- **State:** `AuthContext` (user in localStorage `analyzeai_user`), `ThemeContext` (dark/light, `analyzeai_theme`). Per-page useState for upload→running→done phases.
- **Key components:** AnalyzePage (upload + live agent progress + results), DatasetChat (grounded Q&A panel), HistoryPage (past analyses w/ rows, cols, quality, confidence, duration), AppNavbar, ThemeToggle, shadcn/radix `ui/` primitives. Agent colour coding blue→rose for agents 1–6.

---

## 4. SECTION-BY-SECTION UPDATE INSTRUCTIONS

Format per the request: **Section / Status / Current / Required / Technical / Formulas / Algorithms / Tables / Figures / Screenshots / Code Evidence.**

### 4.1 Chapter 1 — INTRODUCTION
- **Status:** MODIFY (small) + ADD *Report Organization*.
- **Current:** Good background/motivation/problem/objectives/scope; no Report Organization subsection.
- **Required:** Keep narrative. In **Objectives**, keep the two objectives but reframe as achieved. **ADD §1.6 Report Organization** summarising each chapter. Update Scope to say all six agents + web app implemented (remove "four agents currently implemented").
- **Code evidence:** whole repo.

### 4.2 Chapter 2 — LITERATURE REVIEW
- **Status:** KEEP (light MODIFY).
- **Required:** Keep all subsections and citations. Optionally add one short paragraph on **retrieval-augmented generation (RAG)** and **grounded LLM reporting** to justify the implemented anti-hallucination design (Agent 5 kappa gate + Agent 6 claim grounding). Cite an existing RAG reference (see §11 — add a real citation, do not fabricate). Tie the "unverified/hallucinated insights" gap (already in report) explicitly to the implemented grounding checks.

### 4.3 Chapter 3 — REQUIREMENT ANALYSIS
- **Status:** MODIFY + EXPAND.
- **Required:** Keep functional/non-functional lists. **ADD Software Requirements** subsection listing the real stack (§7). **ADD Feasibility Study** (technical: open-source + hosted LLM APIs; operational: no-code web UI; economic: only variable cost is LLM API usage — see cost table). **UPDATE the requirement-status table** (`tab:req-status`) — flip Validation, Report generation, Frontend to **Implemented**; multi-format = **Partial (CSV primary, Excel loader present)**.
- **Table (MODIFY `tab:req-status`):** set Agent 5 "Implemented — Tier-1 contract checks + Cohen's kappa gate"; Agent 6 "Implemented — HTML/PDF via Jinja2/WeasyPrint + grounded LLM narrative"; Frontend "Implemented — React 19 + Vite + Tailwind"; Backend "Implemented — FastAPI + SSE + PostgreSQL/File store".
- **ADD Dataset Analysis subsection:** describe `10000 Sales Records.csv` (10,000 rows × 21 columns; order_id (identifier), order_date (datetime), unit_price (currency), country (geographic/categorical), etc.). Use the Agent-2 tag examples from the provided screenshots (order_id→identifier drop; order_date→datetime; country→geographic one-hot mode; unit_price→currency flag_only).

### 4.4 Chapter 4 — THEORETICAL APPROACH
- **Status:** MODIFY (model facts) — **critical (C3)**.
- **Required:** Keep the generic decoder-only Transformer theory (Eqs. embed/attention/softmax/GQA/RoPE/SwiGLU/RMSNorm all still valid for Qwen3). **Replace the model identity:** primary model **Qwen3-27B** (`qwen/qwen3.6-27b`) served on **Groq LPU**, run as a reasoning model with `reasoning_effort="none"`. **Add the dual-provider design:** automatic **Gemini** failover (`gemini-flash-latest` and 3.x fallbacks) and deterministic fallback. Change/replace citation `dubey2024llama3` → a Qwen technical report citation (add real ref, see §11) and keep `ainslie2023gqa`, `su2021rope`, `shazeer2020swiglu`, `zhang2019rmsnorm`, `vaswani2017`. Update §4.2 "The Llama 3.3 70B Model" heading → "The Qwen3-27B Model"; adjust the "70-billion-parameter"/"80 decoder blocks" specifics to Qwen3-27B (**NOT VERIFIED: exact Qwen3-27B layer count — do not state a precise block count unless confirmed from the model card; describe generically as a multi-billion-parameter decoder-only model**).
- **Figures:** `transformer_architecture.png` (keep), `llm_transformer_architecture.png` (keep but recaption to "Qwen3-style decoder-only Transformer with GQA, RoPE, SwiGLU, RMSNorm"). The provided **"Ollama Inference Architecture"** diagram is mislabeled for this project (project uses Groq/Gemini APIs, not Ollama) — **either recaption as a generic LLM inference/KV-cache diagram or omit; DO NOT claim Ollama is used.**
- **Code evidence:** `agent_2.py` L162–279, 785–879; `agent_6.py` `_call_llm_for_narrative`.

### 4.5 Chapter 5 — SYSTEM ARCHITECTURE AND METHODOLOGY
- **Status:** EXPAND.
- **Required:** Keep pipeline/shared-state/methodology. **ADD** subsections: (a) **LangGraph orchestration & conditional routing** (Agent 5 as hard gate — §3.1); (b) **Reliability & confidence propagation** (Eq. §6); (c) **Backend architecture** (FastAPI + job manager + SSE + storage — §3.8); (d) **Frontend workflow** (§3.9). Replace `last.jpg`/`second2.png` with the up-to-date **6-agent pipeline**, **backend architecture**, and **frontend workflow** diagrams provided.
- **Figures:** system architecture (6-agent), LangGraph workflow, backend architecture, frontend workflow (see §10).

### 4.6 Chapter — IMPLEMENTATION DETAILS
- **Status:** EXPAND Agents 3 & 4; ADD Agents 5 & 6, Backend, Frontend.
- **Required:** Keep Agents 1–4 subsections; **EXPAND Agent 3** (KNN/iterative/forward-fill imputation, fuzzy normalisation, reconciliation, profiles table); **EXPAND Agent 4** (Spearman, leakage flagging, cross-dimensional, ECharts+matplotlib dual charts, chart planner scoring); **ADD Agent 5** (Tier-1 checks + Cohen's kappa gate) with kappa formula; **ADD Agent 6** (fact extraction, hybrid narrative, claim grounding, Jinja2/WeasyPrint) with claim-grounding + MAPE; **ADD Backend API** (endpoints table, SSE, storage, RAG); **ADD Frontend** (routing, SSE consumption, upload/report/chat).
- **Tables/Figures/Code:** profiles table (§3.4); imputation-strategy table (§3.4); anomaly-method table (§3.5); endpoints table (§3.8); Agent-5 kappa code snippet (`_cohen_kappa_score`); Agent-6 claim-grounding snippet (`_check_narrative_grounding`).

### 4.7 Chapter — RESULTS AND ANALYSIS
- **Status:** REWRITE with real outputs (§9).

### 4.8 Chapter — FUTURE ENHANCEMENT (replaces "REMAINING TASKS")
- **Status:** NEW (replace). Remaining-tasks chapter currently lists Agents 5/6 as unbuilt — **delete that framing**. New content: full multi-format ingestion (Excel/JSON/Parquet), model-agnostic provider config, more chart families, containerised deployment, auth hardening, larger-scale evaluation.

### 4.9 CONCLUSION
- **Status:** REWRITE — from "functioning backend up to Agent 4" to "complete end-to-end platform (six agents + FastAPI + React) that ingests CSVs and produces validated, grounded HTML/PDF reports with interactive charts and a dataset chat."

### 4.10 APPENDICES + REFERENCES
- **Status:** EXPAND. Appendices: dataset details (`10000 Sales Records.csv`), cost estimate (keep + refine), timeline (mark all complete), sample generated report screenshots, `agent_run_diagnostics.json` excerpt. References: add Qwen, RAG, Cohen's kappa (Landis & Koch), FastAPI/LangGraph, WeasyPrint as needed (real sources only).

---

## 5. DETAILED PER-AGENT SPEC (for the writer) — already given in §3
See §3.2–3.9 for exhaustive per-agent inputs/outputs/logic/thresholds. Every function name and threshold there is verified from source.

---

## 6. MATHEMATICAL / ALGORITHMIC DETAILS (exact LaTeX)

Include these equations. For each: what it computes / variables / where used / agent / render-as.

1. **Agent 1 confidence** (Eq. exists — keep). Agent 1. Equation.
$$c_1=\mathrm{clamp}\!\left(1-0.5\tfrac{m}{100}-0.3\tfrac{d}{100},0,1\right)$$ m=missing %, d=duplicate %.

2. **Min-Max scaling** (keep). Agent 3. Equation. $x'=\dfrac{x-x_{\min}}{x_{\max}-x_{\min}}$.

3. **Data-quality score** (NEW). Agent 3, `_compute_enhanced_quality_score`. Equation.
$$Q=w_{c}\,S_{c}+w_{v}\,S_{v}+w_{d}\,S_{d},\quad S_c=100-\text{missing\_penalty\%},\ S_v=100-\text{valfail\%},\ S_d=100-\text{dup\%}$$ weights per profile (§3.4 table); risk penalty −5 (critical)/−2.5 (high); clamp [0,100].

4. **Reconciliation tolerance** (NEW). Agent 3. Inline. $\text{tol}=\max(\text{abs\_tol},\,|\text{expected}|\cdot\text{rel\_tol})$.

5. **MAPE (derived-metric reconciliation)** (NEW). Agent 3. Equation.
$$\text{MAPE}=\frac{100}{n}\sum_{i=1}^{n}\frac{|d_i-g_i|}{|g_i|},\quad \text{diverged}\iff r<0.99 \lor \text{MAPE}>1.0\%$$ d=derived, g=ground-truth column.

6. **Z-score anomaly** (keep). Agent 4. Equation. $z=\dfrac{x-\mu}{\sigma}$, flag $|z|>3.5$.

7. **IQR far-out fence** (NEW). Agent 4 anomalies. Inline. $\text{lower}=Q_1-3.0\,\text{IQR},\ \text{upper}=Q_3+3.0\,\text{IQR}$ (Agent 3 clipping uses 1.5×).

8. **OLS regression trend** (NEW). Agent 4. Equation. $\hat{y}=\beta_1 x+\beta_0,\ R^2=r^2,$ significant iff $p<0.05$ (via `scipy.stats.linregress`).

9. **Pearson & Spearman r** — strong pair $|r|\ge0.5$, strong label $\ge0.7$. Agent 4.

10. **MoM / QoQ growth** (NEW). Agent 4. $g_t=\dfrac{v_t-v_{t-1}}{v_{t-1}}\times100$.

11. **ANOVA η² (chart priority)** (NEW). chart_planner. $\eta^2=\dfrac{SS_{between}}{SS_{total}}$, skip <0.08.

12. **Cramér's V (crosstab)** (NEW). chart_planner. $V=\sqrt{\dfrac{\chi^2}{n\,\min(r-1,c-1)}}$.

13. **Cohen's kappa (LLM-vs-heuristic agreement)** (NEW — key). Agent 5. Equation.
$$\kappa=\frac{p_o-p_e}{1-p_e},\quad p_o=\text{observed agreement},\ p_e=\sum_{k}\hat p^A_k\hat p^B_k$$ accept if $\kappa\ge0.4$.

14. **Validation score** (NEW). Agent 5. $\text{VS}=100\cdot\dfrac{\text{passed}+0.5\,\text{warned}}{\text{total}}$; pass iff failed=0.

15. **Claim-grounding confidence** (NEW). Agent 6. $\text{conf}=\dfrac{\text{grounded}}{\text{checked}}$, a claim grounded iff $|c-k|\le\max(1.0,0.05|k|)$ for some known fact k.

16. **Overall reliability** (NEW). main.py. $\bar c=\frac{1}{N}\sum c_i$; readiness ready≥0.85 / needs_review≥0.65 / blocked<0.65.

17. **Business metric formulas** (NEW — Agent 3): profit=rev−cost; margin%=profit/rev×100; rev/unit=rev/units; total_rev=price×units; rev_after_disc=rev−disc; disc%=disc/rev×100; budget_var=rev−budget; budget_var%=var/budget×100; total_cost=cost+tax+shipping; days_to_ship=(ship−order).days.

Render 3, 5, 8, 13, 15 as **numbered equations**; the profile/imputation/anomaly/endpoint items as **tables**; the anomaly and kappa loops as **algorithm listings** (reuse existing `pystyle` code figures — snippets already exist for Agent 1 CSV, Agent 3 currency, Agent 4 anomaly; add Agent 5 kappa and Agent 6 grounding).

---

## 7. TECHNOLOGY STACK (exact, from project files)

**Python ≥ 3.12.** Backend (`pyproject.toml`): google-genai ≥1.0.0, groq ≥1.5.0, langchain-core ≥1.4.8, langgraph ≥1.2.6, pandas ≥3.0.3, numpy, scipy, scikit-learn ≥1.9.0, matplotlib, jinja2 ≥3.1.0, weasyprint ≥69.0, fastapi ≥0.141.1, uvicorn[standard] ≥0.52.0, python-multipart ≥0.0.32, pydantic ≥2.13.4, psycopg[binary] ≥3.3.4, passlib[bcrypt] ≥1.7.4, pgvector ≥0.5.0, huggingface-hub ≥1.26.1, python-dotenv ≥1.0.0; dev: pytest ≥9.1.1.

**LLM providers/models (actual):** Groq **`qwen/qwen3.6-27b`** (`reasoning_effort="none"`); Google **Gemini** fallback `gemini-flash-latest` → `gemini-3.6-flash` → `gemini-3.5-flash` → `gemini-2.5-flash`. **RAG embeddings:** `BAAI/bge-base-en-v1.5` (768-dim) via HF Inference API.

**Frontend (`package.json`):** React 19.2.7, react-dom 19.2.7, react-router-dom 7.18.1, TailwindCSS 4.3.2, @tailwindcss/vite 4.3.2, shadcn 4.12.0, radix-ui 1.6.1, framer-motion 12.42.2, lucide-react 1.22.0, react-icons 5.7.0, three 0.185.0, class-variance-authority, clsx, tailwind-merge; dev: Vite 8.1.0, @vitejs/plugin-react 6.0.2, oxlint 1.69.0. **Charts on screen: ECharts option JSON embedded from backend; no npm charting lib.**

**Storage:** PostgreSQL (tables `analysis_jobs`, `app_users`, `dataset_embeddings` w/ pgvector) **optional**, with JSON **FileJobStore** fallback (`outputs/analysis_jobs.json`). **Do NOT claim Redis** — config/services use PostgreSQL + in-memory + file store, **not Redis** (the provided "Redis Queue" backend diagram is aspirational — either relabel its box to "In-memory job queue / PostgreSQL + File store" or omit; **NOT VERIFIED: Redis is not in the codebase**).

---

## 8. IMPLEMENTATION DECISIONS TO SURFACE IN THE REPORT

Confirmed in code — include: mixed-delimiter CSV detection; multi-encoding read; European number & accounting-negative currency parsing; KNN + iterative multivariate imputation; adaptive IQR/percentile outlier clipping; Min-Max scaling with invertible params; one-hot + top-N "Other" bucketing + ordinal encoding; fuzzy (Levenshtein) category normalisation with review flags; derived business metrics + ground-truth reconciliation (MAPE/r); leakage/ID column exclusion; Pearson+Spearman with formulaic-pair exclusion; skew-aware anomaly detection (z / log-z / IQR-3×); OLS trend with sample-size sufficiency gate; **dual interactive/static charts (ECharts + matplotlib)**; signal-strength chart planning (η², Pareto, Cramér's V); **Agent 5 Cohen's-kappa trust gate + Tier-1 contract checks that hard-stop the pipeline**; **Agent 6 deterministic-first hybrid narrative with claim grounding + jargon linter**; Jinja2 HTML + WeasyPrint PDF with HTML fallback; FastAPI + SSE streaming; thread-based pipeline execution; PostgreSQL/File job persistence; grounded RAG dataset chat with Groq→Gemini→deterministic fallback; JWT-style auth with PBKDF2 hashing; per-stage reliability/confidence propagation.

**Partially implemented (state honestly):** multi-format ingestion (CSV-primary; Excel loader path exists; JSON/Parquet not implemented — **NOT VERIFIED for JSON/Parquet, do not claim**).

---

## 9. RESULTS AND EVALUATION (what to document)

Regenerate on **`10000 Sales Records.csv`** (or the team's confirmed dataset) and capture from console + `agent_run_diagnostics.json` + generated report. Verified-shaped outputs to present (use the provided console screenshots as evidence; **numbers must come from an actual run — do not invent**):

- **Agent 1:** "Profiled 10000 rows × 21 cols | Missing 0.0% | Duplicates 0" (screenshot provided).
- **Agent 2:** "Type sniffing summary {unknown:16, numeric:5}; Blueprint built for 21 columns"; example tags (order_id→identifier/drop/conf 70; order_date→datetime/conf 60; country→geographic/one_hot/mode/conf 60; unit_price→currency/flag_only/conf 85) — screenshots provided.
- **Agent 3:** "profile=strict domain=finance_sales input=10000×21 → 10000×115 quality=100.0/100 raw_missing=0.0% remaining_nulls=0.0%; deduped=0, scaled=1, added_cols=94"; cleaned CSV exported (screenshot provided).
- **Agent 4:** 10-step log — descriptive 27 cols, correlation 8 strong pairs, anomalies 235 rows (2.35%) across 1 col, distributions 4 charts, regression 27 cols, **6 charts saved** (screenshot provided).
- **Agent 5:** validation score/100, passed n/total, Cohen's kappa value, flagged issues — **capture from a real run**.
- **Agent 6:** report path (`outputs/reports/<run_id>/insight_report.pdf|html`), narrative_source (groq/gemini/fallback), claims grounded X/Y, pdf_written — **capture**.
- **Generated charts** (real files present in `outputs/charts/`): `correlation_heatmap.png`, `boxplot_numeric_cols.png`, `monthly_total_revenue_growth.png`, `profit_margin_trend.png`, `margin_by_product_category_over_time.png`, `top_5_product_category_total_revenue.png`, `top_5_region_total_revenue.png`, `scatter_derived_profit_vs_derived_revenue_after_discount.png`, `derived_metrics_summary.png`, `dist_order_status.png` — include 3–5 in Results with captions.
- **Final HTML/PDF report** screenshot (KPI hero cards + a chart section + plain-language insights + glossary tooltips).

**Tables for Results:** (a) per-agent reliability confidences + overall + decision_readiness; (b) validation Tier-1 checks pass/warn/fail; (c) top strong correlations (col1,col2,pearson_r,strength,direction); (d) top/bottom category rankings with revenue share%.

**Error analysis / validation discussion:** cite the ground-truth reconciliation fix (known_issues #1: `format="mixed"` datetime fix + currency-clip guard corrected an 18.6% revenue understatement and 51.7% silent NaT) as a concrete validation win; discuss Cohen's-kappa agreement as LLM-tagging reliability; discuss claim-grounding as hallucination control. **Do not fabricate accuracy percentages.**

---

## 10. REQUIRED VISUALS

For each: caption / contents / section / diagram-or-screenshot / suggested filename.

1. **System Architecture (6-agent pipeline)** — CSV upload → Agent1..Agent6 → outputs; each agent's one-line role. Ch. System Architecture. *Diagram.* `fig_pipeline_6agents.png` (the provided vertical agent-pipeline diagram works).
2. **LangGraph Workflow / routing** — nodes + conditional edges incl. Agent 5 gate to END. System Architecture. *Diagram.* `fig_langgraph_routing.png`.
3. **Backend Architecture** — User → React/Vite → FastAPI (JWT, file validation, jobs, SSE, reports) → PostgreSQL + File store → LangGraph orchestrator → agents. System Architecture. *Diagram (relabel the "Redis" box — see §7).* `fig_backend_arch.png`.
4. **Frontend Workflow** — login → upload CSV → live SSE agent progress → results/charts → report download + dataset chat. System Architecture. *Diagram.* `fig_frontend_flow.png` (provided frontend diagram).
5. **Decoder-only Transformer** — keep. Ch. 4. *Diagram.* `transformer_architecture.png`.
6. **Qwen3-style block (GQA/RoPE/SwiGLU/RMSNorm)** — recaption. Ch. 4. *Diagram.* `llm_transformer_architecture.png`.
7. **LLM inference / KV-cache flow** — recaption the "Ollama" image to generic API inference **or omit**. Ch. 4. *Diagram.*
8. Agent workflow flowcharts (keep): `agent1pic.png`, `agent21/22/23.png`, `agent3pic.png`, `agent4pic.png`. Implementation.
9. **Agent 5 validation flow** — Tier-1 checks + kappa gate. Implementation. *Diagram (NEW).* `fig_agent5_validation.png`.
10. **Agent 6 report generation flow** — facts → LLM narrative → hybrid+grounding → Jinja2/WeasyPrint. Implementation. *Diagram (NEW).* `fig_agent6_report.png`.
11. **Screenshots:** Agent 1/2/3/4 console (provided); Agent 5/6 console (capture); web app upload page; live progress; results dashboard; DatasetChat; generated HTML/PDF report; correlation heatmap; a ranking bar chart; growth line chart. Results/Appendix.
12. **Tables (figures):** profiles table; imputation strategies; anomaly methods; API endpoints; tech stack; reliability results.

---

## 11. REFERENCES / ACADEMIC CONTENT

Keep existing IEEE refs. **Add real citations (do not fabricate identifiers — the writer must fill exact details):**
- **Qwen technical report** (replace/supplement `dubey2024llama3` in Ch. 4) — Qwen team model report.
- **Cohen's kappa / Landis & Koch (1977)** — agreement interpretation (Agent 5).
- **RAG** — Lewis et al., "Retrieval-Augmented Generation" (Lit. Review + Agent 6/chat).
- **FastAPI**, **LangGraph**, **WeasyPrint**, **scikit-learn imputation (KNNImputer/IterativeImputer)**, **BGE embeddings (BAAI/bge-base-en-v1.5)** — tool/library references where first used.
- Keep `vaswani2017`, `ainslie2023gqa` (GQA), `su2021rope` (RoPE), `shazeer2020swiglu`, `zhang2019rmsnorm`.
- **Remove or repurpose** `dubey2024llama3` if Llama is no longer described as the model in use.
Maintain **ascending citation order** and IEEE format; references not chapter-numbered.

---

## 12. MASTER UPDATE SPECIFICATION (ordered build plan)

Do in this order. K=keep, M=modify, X=expand, N=new.

1. **[M] Title page** — "MID-TERM PROGRESS REPORT" → "PROJECT REPORT". Keep authors/roll/dept/logo/date. *(C1)*
2. **[N] Declaration, [N] Certificate of Approval, [N] Copyright** — add IOE prefatory pages (authors + supervisor Er. Rajad Shakya). Order before Acknowledgement.
3. **[M] Acknowledgement** — tense to completed project. Keep names.
4. **[M] Abstract** — complete six-agent + FastAPI + React + validation + HTML/PDF + chat system; add keywords (Cohen's kappa, FastAPI, RAG, React, SSE, WeasyPrint). Remove "four agents / Agents 5–6 planned". *(C2)*
5. **[M] Abbreviations** — add SSE, RAG, JWT, FastAPI, Vite, ECharts, WeasyPrint, Jinja2, IQR, OLS, MAPE, KS, MAD, MoM, QoQ, pgvector, ORM, REST, UUID, CORS.
6. **[M/X] Ch.1 Introduction** — reframe achieved; add §1.6 Report Organization.
7. **[K/M] Ch.2 Literature Review** — keep; add short RAG/grounded-LLM paragraph + citation.
8. **[M/X] Ch.3 Requirement Analysis** — add Software Requirements, Feasibility Study, Dataset Analysis (`10000 Sales Records.csv`); update `tab:req-status` to Implemented. *(C6)*
9. **[M] Ch.4 Theoretical Approach** — Qwen3-27B + Groq LPU + Gemini failover; keep generic equations; recaption/replace Llama-specific text & citation; recaption/omit "Ollama" image. Do not state exact Qwen block count unless verified. *(C3)*
10. **[X] Ch. System Architecture** — add LangGraph routing (Agent 5 gate), reliability propagation, backend architecture, frontend workflow; refresh diagrams.
11. **[X/N] Ch. Implementation** — expand Agent 3 (KNN/iterative/forward-fill, fuzzy normalisation, reconciliation, profiles table) and Agent 4 (Spearman, leakage, cross-dimensional, dual charts, planner scoring); **add Agent 5** (kappa gate + Tier-1) and **Agent 6** (facts→hybrid narrative→grounding→Jinja2/WeasyPrint); **add Backend API** (endpoints table, SSE, storage, RAG) and **Frontend**.
12. **[N] Formulas** — insert Eqs. from §6 (quality score, MAPE, OLS, Cohen's kappa, claim grounding, reliability, business metrics) as numbered equations/tables/algorithms.
13. **[R] Ch. Results & Analysis** — real per-agent outputs, charts, tables, validation, error-analysis (§9). Regenerate numbers; do not invent.
14. **[N] Ch. Future Enhancement** — replace "Remaining Tasks"; list genuine future work.
15. **[R] Conclusion** — complete end-to-end platform.
16. **[X] Appendices** — dataset details, cost (keep/refine), timeline (all complete), sample report screenshots, diagnostics excerpt.
17. **[M] References** — add Qwen, Landis & Koch, RAG, tool refs; keep order/format.
18. **[X] List of Figures/Tables** — regenerate after all figures/tables added.

**Facts to include verbatim (verified):** model `qwen/qwen3.6-27b` + Gemini fallback; embeddings `BAAI/bge-base-en-v1.5`; profiles strict/balanced/lenient thresholds; kappa≥0.4 gate; validation fail ≤15%; anomaly z=3.5 / IQR 3×; trend sig p<0.05 & n≥10; reconciliation r≥0.99 & MAPE≤1%; quality-score weights; upload cap 50 MB, `.csv` only; SSE 0.15s/15s; 6 chart families/sections; charts cap 10, dim cap 1600px; report → `outputs/reports/<run_id>/`.

**Do NOT claim (unverified/absent):** Redis; JSON/Parquet ingestion; Ollama; Llama 3.3 as the live model; any fabricated accuracy/precision numbers; exact Qwen3-27B layer count.

**Code-evidence index:** pipeline `backend/pipeline.py`, `backend/main.py`; Agent 1 `agents/agent_1.py`; Agent 2 `agents/agent_2.py` (L162–279, 785–879); Agent 3 `agents/agent_3.py`; Agent 4 `agents/agent_4.py`; charts `agents/chart_planner.py|chart_spec.py|echarts_options.py|chart_render_static.py|key_indicator.py|rule_definitions.py`; Agent 5 `agents/agent_5.py`; Agent 6 `agents/agent_6.py` + `templates/insight_report.html.jinja` + `agents/report_style.py`; API `backend/api/app.py|config.py|routes/*|services/*|models/schemas.py`; frontend `frontend/AnalyzeAI/package.json|vite.config.js|src/App.jsx|src/lib/api.js|src/pages/*|src/contexts/*`; deps `backend/pyproject.toml|requirements_api.txt`; known-issues `docs/known_issues.md`.

*End of specification.*
