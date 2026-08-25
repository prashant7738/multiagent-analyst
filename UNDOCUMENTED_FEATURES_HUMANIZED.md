# Undocumented Features in MultiAgent Analyst Codebase

## Agent 1: Data Profiling

### Distribution Analysis
Agent 1 classifies numeric columns by computing skewness and kurtosis. Right-skewed columns have positive skewness > 1. Normal columns have |skewness| ≤ 0.5 and |kurtosis| ≤ 1. Everything else is symmetric. This matters because later agents use distribution type to choose outlier-clipping strategy: percentile bounds for skewed data, IQR 1.5× for normal data.

### Implicit Missingness Detection
Some datasets encode missing values as special numbers: -999, -9999, -99 in numeric columns, or strings like "n/a", "none", "missing", "#n/a" in text fields. Agent 1 flags these per-column with row counts affected. This catches what simple null checks miss, especially in financial data where -999 is standard practice for missing values.

### Column Relationships
Agent 1 spots potential primary keys (entirely unique values), duplicate columns (identical data, different names), and strong correlations (|r| ≥ 0.5). These relationships show schema structure and reveal redundant columns before analysis starts.

## Agent 2: Schema and LLM Reliability

### LLM Failover Strategy
Agent 2 tries Groq first, then Gemini. For Gemini, you can supply multiple API keys via environment variables: GEMINI_API_KEYS (comma/space/semicolon-separated), or GEMINI_API_KEY_1 through GEMINI_API_KEY_5. When one key hits quota, the system rotates to the next without retry backoff. This avoids 429 rate-limit cascades.

### Schema Confidence Scores
Each semantic tag gets a confidence score (0-100) based on whether the LLM tag matches the heuristic type detector, accounting for dtype, sample values, and missing rates. Low-confidence tags flag columns that need human review.

### LLM Batching for Wide Schemas
Datasets with 100+ columns get split into batches to avoid token-limit truncation. If a response truncates or fails to parse, the batch size halves recursively. This handles wide datasets without requiring users to manually exclude columns.

## Agent 3: Data Cleaning

### Adaptive Outlier Clipping
Clipping strategy depends on distribution shape. Right-skewed columns use percentile bounds (5th to 95th). Normal columns use 1.5× IQR. This avoids over-clipping rare-but-real values in skewed data while still catching true outliers. Bounds are logged for audit purposes.

### Business Metrics Derivation
When the system finds columns named revenue, cost, quantity, or price, it automatically computes profit (revenue - cost), margin (profit / revenue), discount (listed_price - sale_price), and per-unit revenue. Column name matching uses whole-word logic to avoid false matches on "total_discount_rate" when looking for "discount".

### Preprocessing Profiles
Users pick a strictness level at runtime: strict (tighter thresholds, max currency 1.1B), balanced (default), or lenient (looser thresholds, max currency 10B). The system detects whether the dataset is financial or generic and suggests a profile, but users can override. Reconciliation tolerance also changes per profile (1%, 2%, or 5%).

### Column Ledger
Every transformation logs before/after null counts, parse failure rates, range-check failures, clipping bounds, and notes. This audit trail shows where data quality degrades and makes results reproducible.

### Row Safety Checks
Deduplication and filtering include safeguards. If a single step removes >50% of rows, the pipeline stops with a diagnostic. This prevents silent data loss from bugs.

## Agent 4: Chart Planning

### Statistical Chart Selection
Agent 4 doesn't use keyword lists. Instead it scores eight chart families on statistical strength:
- Dimension ranking (ANOVA eta²: category groups vs. metric)
- Pareto (top-N value concentration)
- Distribution (histogram: spread, skew, outliers)
- Trend (regression r²: metric over time)
- Seasonality (coefficient of variation: month effects)
- Correlation scatter (Pearson r: strongest pairs)
- Crosstab heatmap (Cramér's V: two category columns)
- Anomaly overlay (statistical outliers)

Builders are independent, so failures in one family don't block others. Charts are ranked and capped at a target count (e.g., 12 charts max per report).

### Materiality Gating
A "clear leader" claim requires either 1.5× higher value or 5+ percentage points ahead of second place. Pareto charts group weak performers (<5% share) as "Other". This filters out trivial differences.

### Trend Wording
Even statistically significant trends with <3% actual change get labeled "flat". Statistical significance doesn't always mean business relevance.

### Unified Chart Specs
All families output the same ChartSpec JSON. Data is pre-aggregated so static PNG and interactive ECharts renderers consume identical bytes, preventing inconsistencies between views.

## Agent 5: Validation and Grounding

### Temporal Logic
Impossible date sequences flag data defects: orders before creation dates, shipments before orders, deliveries before shipments.

### Formula Reconciliation
Checks quantity × price ≈ revenue within 2% mean absolute error. Mismatches suggest missing cost data or column artifacts.

### Near-Perfect Correlations
Correlations > 0.98 usually indicate duplicates or data quality signals, not business relationships. They're logged to quality metrics but excluded from narrative findings.

### Broken Rule Filtering
Rules firing on >95% of rows get marked as likely misconfigured. They're kept in audit logs but removed from issue counts, preventing garbage rules from drowning out real problems.

### Cohen's Kappa
Measures how well LLM semantic tags match the local heuristic type detector. Low agreement flags columns needing review.

## Agent 6: Reporting and Grounding

### Narrative Grounding
Before publication, Agent 6 extracts numeric claims ("revenue increased 25%") and verifies them against deterministic facts. Hallucinations are logged with examples.

### Contradiction Detection
Scans the narrative for opposite claims ("we must fix this urgent issue" contradicts "data is solid"). Reports contradiction count and examples.

### Chart Deduplication
Identical specs appearing in multiple sections only render once. This removes redundancy and reduces report size.

### Dynamic Glossary
Instead of a full glossary, only terms used in that specific report get definitions. Maximum 12 terms, matched against narrative text.

### Section Ordering
Sections reorder by combined chart priority (strongest signal first). Readers encounter impactful findings upfront rather than following fixed order.

## APIs and Infrastructure

### Progress Streaming
GET /api/analyze/{job_id}/stream returns Server-Sent-Events: agent progress, charts ready, validation status, report generation. Avoids polling.

### Multi-Key LLM Rotation
Health checks cache status for 90 seconds to spare quota on free tiers. Multiple Gemini keys rotate on quota hit instead of retry storms.

### Optional PostgreSQL Persistence
Job metadata, auth, and chat history can store in PostgreSQL (DATABASE_URL environment variable) or stay in-memory. This supports multi-instance deployments.

### Dataset Q&A
After analysis, users ask questions about the data. The chat service builds context from relevant sections (correlation, trend, ranking) based on detected question topics, then queries the LLM with grounded facts to prevent hallucination.

### On-Demand Charts
Chat service supports chart requests. Allowed types: bar, line, histogram, box, scatter. Allowed operations: count, sum, mean, median, min, max, nunique. Whitelist prevents unexpected requests and data abuse.

### RAG and Semantic Search
Row embeddings and analysis facts store in PostgreSQL pgvector. Two doc families: dataset rows and analysis facts (summaries, correlations, trends, anomalies). Enables AI-powered dataset discovery across jobs.

## Configuration

### Profile Selection at Runtime
Users pick preprocessing strictness (strict/balanced/lenient) at analysis time via analysis_config. This propagates through the entire pipeline.

### Multi-Gemini-Key Strategies
GEMINI_API_KEYS (comma/space/semicolon list) or GEMINI_API_KEY_1..5 environment variables enable key rotation without code changes.

### Gemini Model Fallback Chain
Tries gemini-flash-latest first, then gemini-2.5-flash, gemini-2.5-flash-lite, gemini-2.0-flash. Handles model deprecation without code updates.

### Health Check Caching
Provider checks (Groq, Gemini, HuggingFace, PostgreSQL) cache for 90 seconds. Manual checks available via POST /api/health/test-llm.

### Scoped LLM Context
Chat service attaches only relevant analysis sections based on detected question topics. Reduces tokens and grounds responses in dataset facts.

## Data Ingestion

### Mixed Delimiters
CSV reader handles rows with inconsistent delimiters (comma vs semicolon) by detecting field-count mismatches and reconstructing rows.

### Multi-Encoding Fallback
Tries UTF-8, cp1252, and Latin-1 in sequence. Handles international business datasets.

### Schema Structure Discovery
Detects primary key candidates, duplicate columns, and strong numeric correlations early.
