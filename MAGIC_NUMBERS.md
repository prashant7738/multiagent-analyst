# Magic Numbers & Thresholds — Full Reference

Every hardcoded constant/threshold that shows up in the pipeline, grouped by agent/module. For each: **what it is → where it lives → why that value (from code comments/logic) → the "gotcha" if asked to justify it further.**

This file exists because "where did that number come from?" is one of the most common viva questions, and "we picked it empirically / it's a documented convention" is a perfectly good, honest answer as long as you can say *which*.

---

## Agent 1 — Structural Profiler ([agent_1.py](backend/agents/agent_1.py))

| Constant | Value | Location | Why |
|---|---|---|---|
| Outlier fence (informational) | Q1 − **1.5**×IQR .. Q3 + **1.5**×IQR | `agent1_structural_profiler` | The classic **Tukey fence** (Tukey, 1977) — the textbook-standard mild-outlier boundary, used here only as descriptive metadata, not to remove/flag anything to the user. |
| Numeric sentinel catalogue | `{-999, -9999, -99, -9, -1, 0, 999, 9999, 99999, -99999, ...}` | `_NUMERIC_SENTINELS` | Common placeholder values legacy systems use to mean "missing" instead of a real NULL. |
| Zero-sentinel guard | `zero_pct < 0.25` → skip flagging `0` as a sentinel | `_detect_implicit_missingness` | `0` is an extremely common *legitimate* value (e.g. zero units sold); only flag it as suspicious "missingness" if it's disproportionately frequent (≥25% of the column). |
| Text null-pattern catalogue | 14 variants: `n/a, na, none, null, missing, unknown, #n/a, nil, -, ., ?, n.a., not available, not applicable` | `_TEXT_NULL_PATTERNS` | Real-world "null string" catalogue built from common spreadsheet/export conventions. |
| Candidate-key cardinality | `cardinality_ratio ≥ 0.95` and 0 missing | `agent1_structural_profiler` | 95% uniqueness (not 100%) still flags near-key columns (e.g. one accidental duplicate) as *candidate* keys worth a second look. |
| Distribution "normal" bounds | `\|skewness\| ≤ 0.5` **and** `\|excess kurtosis\| ≤ 1.0` | `_analyze_column_distribution` | Common rule-of-thumb bands for "close enough to normal" in applied stats (not a formal normality test like Shapiro-Wilk, chosen for cheap per-column screening at scale). |
| Right-skew cutoff | `skewness > 1.0` | `_analyze_column_distribution` | Conventional threshold for "substantially skewed" (George & Mallery-style rule of thumb). |
| Datetime parseability threshold | `≥ 80%` of non-null values parse as dates | `_analyze_parseability`, reused in Agent 2's `_infer_intended_types` | High bar so a text column with a handful of date-*looking* strings isn't misclassified; 80% tolerates some genuine junk/garbled rows without over-fitting to a stricter 100%. |
| File-encoding fallback order | `utf-8-sig → cp1252 → latin-1` | `_read_csv_lines` | Covers the three encodings that actually show up in the wild for Windows-exported CSVs (BOM UTF-8, Windows-1252, Latin-1), tried strictly, cheapest/most-common first. |
| Sample values shown | first **3** | `agent1_structural_profiler`, reused everywhere downstream (LLM prompt too) | Enough to signal format/content without inflating the LLM prompt size (cost control) or leaking excessive raw data. |

---

## Agent 2 — Semantic Tagger ([agent_2.py](backend/agents/agent_2.py))

| Constant | Value | Why |
|---|---|---|
| `GROQ_MODEL` | `qwen/qwen3.6-27b` | Selected for Groq's LPU-driven low-latency inference (see report Ch.4) — fast enough for a per-column tagging call to stay off the pipeline's critical-path budget. |
| `GROQ_REASONING_EFFORT` | `"none"` | Verified: with reasoning enabled the model emits a `<think>...</think>` block that either breaks strict JSON parsing or burns the token budget for nothing — every call site here needs pure JSON. |
| `temperature` | `0.1` | Near-zero temperature makes the softmax output sharply peaked (near-deterministic token choice) — required because the response must be strictly parseable JSON, not creative prose. |
| `GROQ_MAX_TRANSIENT_RETRIES` | `2` | A single transient blip (e.g. several jobs hitting Groq's rate limit simultaneously) shouldn't permanently downgrade a job's tagging to heuristics-only; 2 retries balances resilience against latency. |
| `GROQ_RETRY_BACKOFF_SECONDS` | `3` | Short enough not to blow up total pipeline latency, long enough to ride out a brief rate-limit window. |
| `GEMINI_MODEL` + fallbacks | `gemini-flash-latest` → `gemini-3.6-flash` → `gemini-3.5-flash` | Older `gemini-2.5-flash/-lite`, `gemini-2.0-flash` return 404 "no longer available to new users" — list kept to only currently-live model IDs; failover skips any that still 404. |
| `LLM_BATCH_SIZE` | `10` columns per call | Keeps each batch's response small enough to avoid truncation on wide schemas. |
| `LLM_SINGLE_CALL_THRESHOLD` | `15` columns | Below this, one call for the whole schema is cheaper/simpler than batching overhead; above it, batch. |
| `LLM_MAX_TOKENS` | `2000` | Enough headroom for a full JSON blueprint of a batch of columns without over-provisioning cost. |
| `MISSINGNESS_ANALYSIS_THRESHOLD_PCT` | `20.0%` | Columns missing more than this are excluded from downstream analysis (`analysis_allowed=False`) — beyond ~1/5 missing, statistics on that column are considered unreliable enough to flag rather than silently compute. |
| Confidence score base | `50.0` (out of 100) | Neutral starting point before evidence is added/subtracted — see `_calculate_semantic_confidence`. |
| Confidence: name-match bonus | `+20.0` | Column name contains the tag's expected keyword (e.g. "revenue" for `currency`). |
| Confidence: type-alignment bonus/penalty | `+15.0` / `−10.0` | Inferred type matches (or contradicts) what that semantic tag expects (e.g. `currency` should be numeric). |
| Confidence: format-hint bonus | `+15.0` (currency symbols / date patterns), `+10.0` (identifier pattern) | Independent corroborating evidence from Agent 1's format-hint detector. |
| Confidence: cardinality bonus | `+10.0` (clean identifier), `+5.0` (candidate-key hint), `+10.0` (1 < unique < 20 for categorical) | Rewards internally-consistent evidence between the tag and the column's actual cardinality. |
| Confidence: high-missingness penalty | `−10.0` if `missing_rate > 50%` | A tag guessed from a half-empty column deserves lower trust. |
| Confidence: outlier-signal penalty | `−5.0` | Small penalty when Agent 1 already flagged significant outliers. |
| Confidence level bands | `≥80 high`, `≥60 medium`, `<60 low` | Coarse, human-readable bucketing of the 0–100 score. |
| Column-suitability missingness caps | identifier ≤5%, categorical/geo/text ≤30%, datetime ≤25%, currency/pct/count ≤35%, unknown ≤20% | `_assess_column_suitability` — different semantic roles tolerate different amounts of missing data before the column is judged unfit for analysis; identifiers are strictest because a missing key literally breaks row identity. |
| "Too sparse" override | `missing_rate > 60%` | Regardless of tag, a column this empty is reclassified `too_sparse` rather than whatever its normal suitability rule would say. |
| Null-policy thresholds (selected) | `25%` (categorical too sparse), `40%` (categorical flag-only), `35%` (numeric flag-only ceiling), `20%` (mean-imputation ceiling for near-normal data), `10%`/`30%` (KNN/iterative eligibility band), `60%` (drop-column trigger) | `_derive_null_policy` — a full decision table combining semantic tag, missingness %, distribution shape, and correlation strength; thresholds are conservative engineering judgment calls documented inline in the function, not derived from a formal statistical test. |
| Multivariate-imputation trigger | ≥2 correlated partners with `\|r\| ≥ 0.9` **and** `10–35%` missing → iterative; `\|r\| ≥ 0.85` **and** `10–30%` missing → KNN | Only reach for a more complex/expensive imputation method when there's real correlated signal to exploit — otherwise fall back to simple median/mean. |
| Percentage `unit_scale` auto-detect | `ratio` if 95th percentile ≤ 1.0, else `percent` | `_enrich_missingness_metadata` — a simple, robust rule to tell "0.0–1.0 scale" from "0–100 scale" percentages without hardcoding per-dataset assumptions. |

---

## Agent 3 — Preprocessor ([agent_3.py](backend/agents/agent_3.py))

| Constant | Value(s) by profile (`strict` / `balanced` / `lenient`) | Why |
|---|---|---|
| `currency_max_abs_value` | 1.1B / 1.0B / 10.0B | Plausibility ceiling for a single currency cell — catches a currency-parsing bug (e.g. decimal-separator mis-detection producing a 1000× inflated number) as a **hard pipeline-halting error**, tuned looser for `lenient` domains where huge legitimate values are more plausible. |
| `max_reasonable_tax_rate` | 0.30 / 0.40 / 0.60 | Flags a row where tax exceeds this fraction of the amount as implausible — `strict` (finance domain) assumes tax rates are realistically capped near 30%; `lenient` tolerates more before flagging. |
| `reconciliation_rel_tol` / `reconciliation_abs_tol` | 1% & 0.50 / 2% & 1.0 / 5% & 2.0 | Tolerance for `total ≈ amount + tax − discount` — the wider absolute+relative combination (`max()` of the two) avoids false failures from floating-point rounding on tiny amounts while still catching real reconciliation breaks on large ones. |
| `quality_weights` | e.g. strict: null 0.55 / fail 0.35 / dup 0.10 | How much each defect type docks the 0–100 quality score — `strict` weights missing data most heavily (financial data with gaps is riskiest), `lenient` spreads weight more evenly including duplicates. |
| `DEFAULT_KNN_NEIGHBORS` | `5` | Standard default `k` for `sklearn.KNNImputer` — a common, unremarkable default that works reasonably across dataset sizes; clamped to `min(k, n_rows−1)` so it never errors on tiny datasets. |
| `DEFAULT_ITERATIVE_MAX_ITER` | `10` | `sklearn.IterativeImputer`'s convergence budget — enough rounds for the MICE-style algorithm to stabilize on typical business datasets without excessive runtime. |
| Row-survival floor | `≥ 50%` of input rows must survive any single step | `_assert_row_survival_or_abort` — if more than half the rows vanish in one step, that's almost certainly a **bug** (e.g. a bad merge key), not legitimate deduplication; the pipeline halts loudly instead of silently shipping a decimated dataset. |
| `FUZZY_MATCH_MAX_DISTANCE` | `2` (Levenshtein edit distance) | Empirically verified against real dataset category values to catch typo-level variants (`"Cancelled"`/`"Canceled"` = distance 1) without being so loose it merges unrelated short words. |
| `FUZZY_MATCH_MIN_LENGTH` | `6` characters | Guards against short codes/antonyms trivially within distance 2 of each other (`"North"`/`"South"` = distance 2, `"Cc"`/`"Dc"` = distance 1) being spuriously merged — verified this length gate keeps every legitimate merge found in real data while excluding every observed false-positive risk. |
| First-letter match requirement | same first character (case-insensitive) | Real spelling variants/typos of the same word essentially never change the leading character; this alone stops `"Houston"`/`"Boston"` (distance 2, both 6+ chars, but genuinely different real names) from merging, without rejecting any legitimate merge. |
| `FUZZY_REVIEW_ROW_PCT` | `5.0%` | A merge candidate's row-count share must be ≤5% of the column to even be considered a "rare variant" worth merging — a value already common enough to be 5%+ of the column is unlikely to be a typo of something else. |
| `FUZZY_RARE_VALUE_PCT` | `1.0%` | The *source* label being merged away must be ≤1% of rows — protects against merging two independently common, legitimately different categories. |
| `LOW_CARDINALITY_MAX` | `3` | Columns with ≤3 distinct values skip fuzzy matching entirely — too few categories for "near-duplicate spelling" to be a meaningful concept (they're more likely genuinely distinct short labels). |
| `FUZZY_MAX_CATEGORY_LABELS` | `500` | Pairwise edit-distance comparison is O(n²) and stops being meaningful for high-cardinality, product-name-like fields; skip entirely above 500 distinct labels rather than pay a quadratic cost for noise. |
| `RECONCILIATION_MIN_CORR` | `0.99` | A derived metric vs. its raw-column equivalent must correlate at least this strongly to be judged "the same concept" — high bar because these should be near-exact algebraic identities, not just related. |
| `RECONCILIATION_MAX_MAPE_PCT` | `1.0%` | Mean absolute percentage error ceiling for the same reconciliation check — a genuinely-matching formula should track within 1%, not just correlate. |
| `RECONCILIATION_MIN_PAIRS` | `5` | Minimum overlapping non-null rows before even attempting a correlation/MAPE check — avoids false confidence from a 2-3-point coincidental match. |
| Domain-detection thresholds | `≥3` finance-keyword column names **or** `≥2` currency/percentage tags → `finance_sales` domain | `_detect_dataset_domain` — a simple, explainable majority-signal rule (not ML-based) for auto-selecting the `strict` preprocessing profile. |
| `ONE_HOT_LOW_CARDINALITY` | `10` | ≤10 distinct categories get full one-hot encoding — a widely-used practical cutoff before column-count explosion becomes a real problem. |
| `ONE_HOT_TOP_N` | `8` | Above the cardinality threshold, keep the top 8 most frequent categories + a single "Other" bucket — preserves signal from the dominant categories without an unbounded column count. |
| One-hot near-unique safety net | skip encoding if `cardinality / n_rows > 0.5` and `cardinality > 10` | A column this close to unique-per-row is very likely a mistagged identifier/date that slipped past upstream checks — one-hot/Top-N+Other would be meaningless (the "Other" bucket would swallow nearly every row). |
| Adaptive outlier clipping — base rule | IQR **×1.5** (Q1−1.5IQR .. Q3+1.5IQR) | Standard Tukey mild-outlier fence, used as the *default* clipping bound. |
| Adaptive outlier clipping — percentile mode | `1–99%` (critical risk) / `5–95%` (high risk) / `2.5–97.5%` (else) — triggered only when Agent 1's own distribution analysis shows real skew/outliers **or** the dataset's assessed risk tier is high/critical | Switching to percentile bounds only on *evidenced* skew (not by semantic tag alone) was a direct fix for a documented bug where percentage/count columns were always percentile-clipped regardless of whether they actually had outliers, manufacturing a fake ~5% "outlier rate" purely by construction. |

---

## Agent 4 — Statistical Analysis & Charts ([agent_4.py](backend/agents/agent_4.py), [chart_planner.py](backend/agents/chart_planner.py))

| Constant | Value | Why |
|---|---|---|
| `ANOMALY_Z_THRESHOLD` | `3.5` | Wider than the "textbook" z=3 — chosen to reduce false positives on business data where a z=3 rule flags too many merely-large-but-legitimate transactions; 3.5 is a common, slightly more conservative convention. |
| `ANOMALY_SKEW_THRESHOLD` | `1.0` (absolute skewness) | Beyond this, a plain mean/std z-score is unreliable (skew inflates std enough to hide or over-flag anomalies), so the method switches to log-z or IQR instead. |
| `ANOMALY_IQR_MULTIPLIER` | `3.0` (Tukey's "**far-out**" fence, not the 1.5 "outer fence" used for clipping in Agent 3) | An audit measured that the 1.5× rule flags ~24% of rows on a real right-skewed column — far too noisy to *report as anomalies* (vs. Agent 3's 1.5× which is fine for silent *clipping*). 3.0 keeps this a rare, meaningful *flag* (surfaced, never removed). Overridable via `ANOMALY_IQR_MULTIPLIER` env var. |
| `CORRELATION_HEATMAP_MIN_R` | `0.3` | A heatmap of near-zero correlations tells the reader nothing — skip drawing it entirely unless at least one pair reaches this minimum relationship strength. |
| `MAX_CHARTS_PER_REPORT` | `16` (env-overridable) | Without a cap, a wide dataset produces dozens of charts of wildly uneven value; capping and ranking by informativeness score keeps the report focused on what's actually worth showing. |
| `CHART_SAVE_DPI` / `MAX_CHART_DIM_PX` | `150` dpi / `1600` px | Hard ceiling on saved PNG dimensions *regardless of how many categories/periods drove the figure's size* (500 months, 1000 categories, etc.) — keeps report file size and rendering sane. |
| `MAX_XTICK_LABELS` | `18` | Beyond this many x-axis ticks, labels overlap into illegible mush at the report's ~700px display width — thinned to an evenly-spaced readable subset instead. |
| `ROTATE_XTICK_LABELS_ABOVE` | `8` | Below this, labels fit horizontally; above it, rotate 45° for legibility. |
| `MAX_TIME_SERIES_CHART_POINTS` | `40` | Beyond 40 time periods, a bar-per-period chart is illegible even after tick thinning — the **chart** (not the underlying stats, which stay full-fidelity) rolls up to a coarser grain (e.g. monthly→yearly). |
| `min_cv` (coefficient of variation) | `0.03` | `_has_meaningful_variation` — a scale-free, cheap signal-strength check (std/mean) to avoid drawing a time-series/trend chart for data that's essentially flat noise. |
| Correlation strength bands | `\|r\|≥0.5` reported, `\|r\|≥0.7` "strong" (else "moderate"), `\|r\|>0.98` "near-perfect" (flagged as possible data-quality artifact) | Conventional correlation-strength conventions; the near-perfect flag exists because r>0.98 pairs are more often duplicated/derived columns than genuine business relationships. |
| `PRIORITY_DIMENSION_KEYWORDS` / `MAX_RANKING_DIMENSIONS` | `region, category, segment, representative` / `6` | Guarantees business-priority dimensions a ranking slot instead of losing to noisier high-cardinality columns (a documented past bug); raised from an unconditional top-3 to leave room for these plus the most metric-differentiated others. |
| Ranking dimension cardinality bounds | `2 ≤ unique categories ≤ 20` | Fewer than 2 can't be ranked meaningfully; more than 20 makes "bottom N" a single-row noise comparison rather than a real underperformer group. |
| `STRUCTURAL_RULE_REVIEW_PCT` | `90.0%` | If a structural data-quality rule fires on more than 90% of rows, that row-level detail needs human review rather than being narrated as-is. |
| `BROKEN_RULE_FIRE_RATE_PCT` | `95.0%` | If a rule fires on **more than 95%** of rows, it's more likely the rule itself is misconfigured for this dataset than that 95% of the data is genuinely broken — such rules are filtered out (`_filter_broken_validation_rules`) rather than shown as a scary but probably-wrong finding. |
| `ANOMALY_QUALITY_TOLERANCE_PCT` / `SCALE` / `CAP` | `3.0%` / `0.1` / `5.0` | Statistical outliers may be entirely legitimate long-tail values, so they dock the quality score only lightly (small scale, low cap) — tolerance means the first 3% of flagged rows cost nothing at all. |
| `DQ_ISSUE_PENALTY_SCALE` / `CAP` | `1.5` / `40.0` | **Structural** violations (negative quantities, discount >100%, broken reconciliation) are real defects and dominate the score far more heavily than statistical outliers — by design, per the project's data-quality philosophy (statistical extremity ≠ defect). |
| Regression significance | `p < 0.05` | Standard statistical convention for "significant" — a trend line fit to p≥0.05 noise is not reported/charted as a real trend. |
| Chart-planner constants (`chart_planner.py`) | `MAX_BAR_LABELS=15`, `MAX_SCATTER_POINTS=400` (stride-sampled), `MAX_OUTLIERS_LISTED=30`, `MIN_GROUP_ROWS=3`, `MIN_ROWS_FOR_GROUPS=8`, `CAT_MAX_UNIQUE=25`, `CROSSTAB_MAX_UNIQUE=8`, `MAX_SPECS_PER_FAMILY=2` | Practical legibility/performance caps — e.g. a scatter of 50,000 points renders as an unreadable smear and is slow to draw; a stride sample of 400 preserves the visual shape at a fraction of the cost. |
| Pareto-spec minimum score | best_score `≥ 30` (0.6×top1-share + 0.4×top3-share) | Below this, the concentration isn't strong enough to be worth a dedicated "market concentration" chart. |

---

## Agent 5 — Output Validation ([agent_5.py](backend/agents/agent_5.py))

| Constant | Value | Why |
|---|---|---|
| `MIN_ACCEPTABLE_KAPPA` | `0.4` | The Landis & Koch (1977) boundary for "**fair**" agreement or better — below this, the LLM's semantic judgment is diverging too often from the mechanical baseline to be trusted without review. |
| `MAX_VALIDATION_FAIL_PCT` | `15.0%` | Ceiling on Agent 3's worst business-rule failure rate before Agent 5 flags it — allows for some genuine edge-case data without treating every dataset with *any* imperfect row as an outright failure. |
| `MIN_TREND_SAMPLE_SIZE` | `10` | Re-validates Agent 4's "significant" (p<0.05) trends against a minimum sample size — a significant fit on 4–5 points is statistical noise dressed up as a trend, not something worth reporting. |
| Validation score formula | `100 × (passed + 0.5×warned) / total_checks` | Warnings count as "half credit" rather than a full failure or a full pass — reflects that a warning is real but not gate-breaking. |
| Category-normalization safety | `changed_pct > 5.0%` **or** (`raw_pct > 1.0%` **and** `canonical_pct > 1.0%`) → unsafe | Rejects a fuzzy merge (from Agent 3) that either touched too many rows at once, or merged two values that were each independently common enough to plausibly be genuinely different categories rather than a typo. |
| Decision-readiness thresholds (in `main.py`, shared by all agents) | `overall_confidence ≥ 0.85 → "ready"`, `≥ 0.65 → "needs_review"`, else `"blocked"` | A simple three-tier bucketing of the mean per-stage confidence score into an actionable label. |

---

## Agent 6 — Insight Report Generator ([agent_6.py](backend/agents/agent_6.py))

| Constant | Value | Why |
|---|---|---|
| `TOP_CORRELATIONS_LIMIT` | `5` | Cap on how many correlation pairs are cited in the narrative — enough to be substantive without overwhelming a plain-language report. |
| `TOP_RANKING_LIMIT` | `3` | Top/bottom-3 per ranking dimension shown in the narrative (Agent 4 itself computes top/bottom-5 internally; the narrative trims further for readability). |
| `TOP_REGRESSION_LIMIT` | `5` | Same rationale — cap the number of trend lines cited in prose. |
| `MIN_TREND_SAMPLE_SIZE` | `10` | Mirrors Agent 5's threshold exactly — trends below this sample size are never cited as fact in the narrative either. |
| `CLAIM_GROUNDING_TOLERANCE` | `1.0` absolute, **also scaled by 5% of the known value** | A number the LLM writes must match a computed fact within either a flat ±1.0 or ±5% (whichever is larger) — accounts for legitimate rounding ("about 45%" vs. computed 45.3%) without letting genuinely wrong numbers pass. |
| `MAX_CHART_CAPTIONS_FROM_LLM` | `12` | Caps how many LLM-written chart captions are trusted per report — keeps prompt/response size bounded. |
| `MAX_NARRATIVE_PROMPT_CHARS` | `7000` | Prompt-size ceiling for the narrative-generation call — keeps token cost and latency predictable regardless of how large the underlying dataset's fact-set is. |
| Confidence: LLM vs. fallback narrative | `0.95` vs `0.55` | A narrative that came from the (hygiene-checked) LLM path is trusted substantially more than the guaranteed deterministic floor — but the floor still scores meaningfully (0.55), not near-zero, since it's still fact-accurate. |
| Confidence scaling by grounding | `confidence × (0.7 + 0.3 × grounding_confidence)` | Even an LLM-sourced narrative that cites some ungrounded numbers gets docked — the 0.7 floor ensures grounding issues discount rather than zero out an otherwise good narrative. |
| Material-difference check | `threshold_multiplier=1.5`, `absolute_threshold_pct=5` | `_is_material_difference` — used to decide whether two rankings/shares are different enough to be worth calling out as a real gap versus noise-level variation. |

---

## Reliability layer ([main.py](backend/main.py))

| Constant | Value | Why |
|---|---|---|
| `decision_readiness` bands | `≥0.85 ready`, `≥0.65 needs_review`, `<0.65 blocked` | Applies uniformly across every agent's `update_reliability()` call — a single, consistent policy for "how much should a human trust this run" rather than a per-agent ad-hoc rule. |

---

## Rule versioning ([rule_definitions.py](backend/agents/rule_definitions.py))

- `RULE_DEFINITION_VERSION = "2026.08.1"` and a SHA-256-derived 12-char `RULE_DEFINITION_HASH` are stamped onto every run's quality/anomaly output (`rule_manifest()`), so a report can be traced back to *exactly* which version of the business-rule definitions (percentage bounds, count ranges, tax-rate ceiling, reconciliation tolerance) produced it — this is an auditability feature, not a statistical threshold, and is a good example to cite if asked "how would someone reproduce this exact report six months from now."

## Formatting helper ([report_style.py](backend/agents/report_style.py))

- `humanize_number` divisors: **1,000,000,000 → "B"**, **1,000,000 → "M"**, **1,000 → "K"** — standard human-readable number abbreviation, applied consistently across matplotlib PNGs, interactive charts, and report prose so all three always agree on how a number is displayed.
- `safe_filename_component` max length: **120** characters — filesystem-safe cap on generated chart filenames derived from column names/labels, with a SHA-256 suffix appended whenever the human-readable slug had to be altered, so filenames stay both readable and collision-free.

---

## The meta-answer for "how were these chosen?"

Be honest and confident about this if pushed: **most of these are documented engineering judgment calls, not values derived from a formal optimization** — several (Tukey's 1.5/3.0 IQR fences, Cohen's kappa 0.4 "fair" band, p<0.05 significance, z=3.5) are widely-used statistical conventions; a few (fuzzy-match distance/length, one-hot cardinality cutoffs, chart caps) were **empirically verified against real dataset behavior** (the code comments cite specific observed false-positive/false-negative cases that shaped the exact number chosen); and the **profile system** (`strict`/`balanced`/`lenient`) exists specifically so these aren't one-size-fits-all — the same pipeline can be tuned tighter for financial data and looser for generic/exploratory data without touching code.
