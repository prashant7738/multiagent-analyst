# Undocumented Features in MultiAgent Analyst Codebase

## Agent 1: Data Profiling Enhancements

### Distribution Analysis
Agent 1 analyzes column distributions by computing skewness and excess kurtosis to classify each numeric column into three types: right-skewed (positive skewness > 1), normal (|skewness| <= 0.5 and |excess kurtosis| <= 1), and symmetric. This distribution classification enables downstream agents to apply appropriate statistical transformations. For example, adaptive outlier clipping uses distribution type to decide between percentile bounds (for skewed columns) versus IQR-based bounds (for normal columns).

### Implicit Missingness Detection
The platform identifies values that encode missingness implicitly. For numeric columns, it checks against common sentinel values (-999, -9999, -99, -1, 999, etc.). For text columns, it matches patterns like "n/a", "na", "none", "null", "missing", "#n/a", "nil", and "unknown". Each flagged column reports the sentinel/pattern and row count affected. This catches data quality issues that simple null-count detection would miss, especially in financial datasets where -999 often indicates missing values.

### Column Relationship Detection
Agent 1 identifies potential primary keys (columns with entirely unique values), duplicate column pairs (identical data under different names), and strong numeric correlations (|r| >= 0.5). These relationships help understand schema structure and spot redundant columns before analysis.

## Agent 2: Schema Intelligence and LLM Reliability

### Multi-Model LLM Failover
Agent 2 implements a cascading failover strategy: Groq API first, then Gemini with multiple-key rotation. The system supports up to 5 Gemini API keys via environment variables (GEMINI_API_KEYS as a comma/space/semicolon-separated list, or GEMINI_API_KEY_1 through GEMINI_API_KEY_5). When a key hits quota, the rotation advances to the next one without retry-storm backoff, preventing rate-limit 429 errors from cascading.

### Schema Confidence Scoring
Each semantic tag assigned to a column receives a confidence score (0-100) based on heuristic agreement with LLM signals. Scores account for dtype match, sample consistency, and missing-value rates. This allows downstream agents to flag low-confidence columns that need review.

### LLM Batching for Wide Schemas
When a dataset has many columns (100+), Agent 2 batches the schema inference requests to avoid token-limit truncation. If the LLM response is truncated or unparseable, the batch size recursively halves. This strategy keeps wide datasets processable without manual column selection.

## Agent 3: Intelligent Data Cleaning

### Adaptive Outlier Clipping
Outlier clipping adapts to distribution shape. For right-skewed columns, it uses percentile-based bounds (e.g., 5th-95th percentiles). For normal columns, it applies the 1.5× IQR rule. This avoids over-clipping rare-but-legitimate values in skewed data while protecting against true outliers in normal distributions. The system records clipping bounds in a ColumnLedger for audit trail.

### Business Metrics Derivation
Agent 3 auto-constructs business metrics when columns like revenue, cost, quantity, and price are detected. It derives profit (revenue - cost), margin (profit / revenue), discount (listed_price - sale_price), and revenue_per_unit. Pattern matching uses whole-word column name matching to avoid false hits on columns like "total_discount_rate" when deriving "discount".

### Preprocessing Profiles (Strict / Balanced / Lenient)
Users can select preprocessing strictness at runtime. Strict profile applies stricter thresholds for outlier detection, lower max currency values (1.1B), and tighter reconciliation tolerance (1%). Lenient profile accepts higher currency values (10B) and looser reconciliation checks (5%). The platform auto-detects dataset domain (finance vs. generic) and recommends a default profile, but users can override.

### Column Ledger Audit Trail
Every transformation is logged to a ColumnLedger: before/after null counts, parse failure percentage, range-check failures, clip bounds, and notes. This audit trail enables reproducibility and helps identify where data quality degrades through the pipeline.

### Row Survival Assertions
Deduplication and other filtering steps include safety checks. If more than 50% of rows are removed in a single step, the pipeline aborts with a diagnostic message. This prevents silent data loss from logic errors.

## Agent 4: Statistical Chart Planning

### Data-Driven Chart Selection
Instead of domain-specific keyword matching, Agent 4 scores eight chart families on statistical signal strength:
- Dimension ranking: ANOVA eta-squared (category groups vs. numeric metric)
- Pareto: concentration of value (top-N share)
- Distribution: histogram (numeric spread, skewness, outliers)
- Trend: regression r² (metric vs. time)
- Seasonality: coefficient of variation (month-of-year effect)
- Correlation scatter: Pearson r (strongest numeric pairs)
- Crosstab heatmap: Cramér's V (two category columns)
- Anomaly overlay: statistical outlier detection

Each builder is isolated, so a failure in one family doesn't block others. Charts are scored and ranked; the top N stay under MAX_CHARTS_PER_REPORT (e.g., 12).

### Materiality Gating
Rankings only claim "clear leader" when one group's metric is 1.5× higher or 5+ percentage points ahead of the next. Weak performers (<5% share in Pareto) are grouped as "Other". This prevents trivial differences from being reported as insights.

### Trend Direction Wording
Even when a trend's regression r² is statistically significant, a slope < 3% actual change is labeled "flat" rather than upward/downward. This avoids false positives where statistical significance doesn't translate to business relevance.

### Chart Specification Unification
All chart families return a unified ChartSpec JSON format consumed by both static PNG and interactive ECharts renderers. Pre-aggregated data ensures both outputs use identical bytes, preventing divergence between views.

## Agent 5: Validation and Grounding

### Temporal Logic Validation
Agent 5 detects impossible date orderings: orders before creation dates, shipments before orders, or deliveries before shipments. These flag structural data quality defects.

### Formula Reconciliation
The system checks quantity × price ≈ revenue within 2% mean absolute percentage error (MAPE). Mismatches flag missing cost data or column-name artifacts.

### Near-Perfect Correlation Flagging
Correlations > 0.98 are flagged as likely data quality signals (e.g., duplicate columns) rather than business insights. They're logged to data quality metrics but excluded from narrative recommendations.

### Broken Rule Downgrading
Validation rules that fire on >95% of rows are marked "is_likely_misconfigured" and excluded from issue counts, though kept in audit logs. This prevents garbage rules (e.g., checking for negative values when all records are legitimately negative) from drowning out real issues.

### Cohen's Kappa Agreement
The system computes Cohen's kappa between LLM semantic tags and local heuristic type sniffing. Low agreement flags columns needing manual review.

## Agent 6: Report Generation and Narrative Grounding

### Narrative Claim Grounding
Before publishing, Agent 6 extracts numeric claims from the LLM narrative (e.g., "revenue increased 25%") and verifies them against deterministic insight_facts. Flagged hallucinations are logged with examples.

### Contradiction Detection
The narrative is scanned for opposite claims ("we must fix this urgent issue" vs. "data is solid and reliable"). Contradiction counts and examples help catch LLM inconsistencies.

### Chart Deduplication
If identical chart specs appear in multiple sections, only the first is retained. This avoids redundant rendering and report bloat.

### Dynamic Glossary
Instead of including a full glossary, only terms actually used in that report are defined. The system extends DEFAULT_GLOSSARY with domain-specific terms from EXTENDED_GLOSSARY but caps the final glossary at 12 entries matched against the narrative text.

### Section Priority Reordering
Report sections are reordered by combined chart priority (strongest statistical signal first) rather than fixed order. This ensures readers encounter the most impactful findings first.

## API and Infrastructure Features

### Server-Sent-Events Progress Stream
The /api/analyze/{job_id}/stream endpoint returns Server-Sent-Events (SSE) progress updates: agent completions, chart generation, validation pass/fail, and report readiness. This allows the frontend to show real-time pipeline progress without polling.

### Multi-Key LLM Rotation
The health check endpoint (/api/health) caches provider status for 90 seconds to avoid exhausting free-tier quotas. Multi-Gemini-key rotation prevents retry storms when individual keys hit quota limits.

### Optional PostgreSQL Persistence
The job manager can store job metadata, authentication, and chat history in PostgreSQL (via DATABASE_URL environment variable) or fall back to in-memory storage. This enables multi-instance deployments.

### Dataset Chat Q&A Service
After analysis completes, users can ask questions about the dataset. The chat service builds topic-scoped context from relevant analysis sections (correlation, trend, ranking, etc.) based on question keywords, then queries the LLM with grounded context to prevent hallucination.

### On-Demand Chart Generation
Users can request new charts within the chat service. The request is validated against a whitelist of allowed chart types (bar, line, histogram, box, scatter) and allowed query operations (count, sum, mean, median, min, max, nunique). This prevents unexpected chart requests and data query abuse.

### RAG Embeddings and Semantic Search
Row embeddings and analysis facts are stored in PostgreSQL pgvector with semantic search. Two doc families are indexed: dataset rows and analysis facts (dataset_summary, correlation, trend, anomaly). This enables AI-powered dataset discovery across jobs.

## Environmental Configuration

### Preprocessing Profile Selection
Users can override the auto-detected preprocessing profile at runtime via analysis_config.preprocessing_profile. This propagates through the entire pipeline (Agent 3, Agent 4, Agent 5).

### Multi-Gemini-Key Strategies
Environment variables GEMINI_API_KEYS (comma/space/semicolon-separated list) and GEMINI_API_KEY_1..5 enable key rotation without code changes. The rotation index advances when a key hits quota, preventing retry storms.

### Gemini Model Fallback Chain
The system defines GEMINI_MODEL_FALLBACKS trying gemini-flash-latest first, then gemini-2.5-flash, gemini-2.5-flash-lite, and gemini-2.0-flash. This gracefully handles model deprecation without code updates.

### Health Check Caching
Provider health checks (Groq, Gemini, HuggingFace, PostgreSQL) are cached for 90 seconds. This prevents quota exhaustion on free-tier accounts while allowing manual checks via POST /api/health/test-llm.

### LLM Context Scoping
The chat service dynamically attaches only relevant analysis sections to the LLM prompt based on question topics detected via keyword matching. This reduces token usage and grounds responses in dataset-specific facts.

## Data Ingestion Resilience

### Mixed-Delimiter CSV Handling
The CSV reader detects inconsistent delimiters (comma vs. semicolon) and reconstructs rows when field counts mismatch. This handles real-world business exports that mix delimiter conventions.

### Multi-Encoding Fallback
CSV ingestion tries UTF-8, cp1252, and Latin-1 encoding in sequence. This ensures compatibility with international business datasets.

### Column Relationship Detection
The platform detects potential primary keys, suspicious duplicate columns, and strong numeric correlations to surface schema structure issues early.
