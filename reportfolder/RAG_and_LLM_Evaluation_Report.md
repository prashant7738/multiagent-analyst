# RAG & LLM Performance Evaluation Report

**Project:** MultiAgent DataAnalyst
**Dataset evaluated:** `amazon_sales_dataset (1).csv`
**Job ID:** `953164f396044c57914e2cf2775ec4bb`
**Date:** 2026-08-25

All numbers in this report are from real, live runs against the actual application — the real embedding model (Hugging Face `BAAI/bge-base-en-v1.5`), the real vector index (Postgres/pgvector), the real Groq model (`qwen/qwen3.6-27b`), and the real 6-agent pipeline. Nothing here is simulated.

---

## 1. Dataset Description

| Property | Value |
|---|---|
| Filename | `amazon_sales_dataset (1).csv` |
| Raw rows | 10,000 |
| Raw columns (original CSV) | 21 |
| Columns after Agent 3 preprocessing | 70 (62 analysis columns + 8 internal audit columns, e.g. `*_parse_failed`, `*_was_clipped`) |
| Missing data | 0.0% |
| Duplicate rows | 0.0% |
| Overall data quality score | 99.64 / 100 |
| Validation | Passed |
| Overall confidence | 0.89 |
| Decision readiness | `needs_review` |
| Charts generated | 16 |

**Original columns:** `order_id, order_date, ship_date, delivery_date, order_status, customer_id, customer_name, country, state, city, product_id, product_name, category, sub_category, brand, quantity, unit_price, discount, shipping_cost, total_sales, payment_method`

**Semantic tag distribution** (Agent 2, LLM-classified): geographic ×3, categorical_label ×5, currency ×9, identifier ×3, count ×1, datetime ×3, text ×2, encoded_category ×14 (40 columns tagged total, including intermediate encoding entries).

**Categorical value distributions** (used as ground truth for the retrieval evaluation below):
- `category`: Home 3,379 · Electronics 3,352 · Fashion 3,269
- `sub_category`: Furniture 1,738 · Footwear 1,673 · Kitchen 1,641 · Clothing 1,596 · Mobile 1,145 · Laptop 1,118 · Accessories 1,089
- `payment_method`: COD 2,541 · Card 2,525 · NetBanking 2,490 · UPI 2,444
- `order_status`: Delivered 10,000 (single value — no variation in this dataset)

**RAG index:** 3,000 of 10,000 rows are embedded and searchable (`RAG_MAX_ROWS=3000`, stratified sampling — guarantees coverage of every category value, not pure random).

---

## 2. RAG Retrieval Quality — Precision, Recall, F1, MRR, nDCG

**Methodology:** 12 test questions, each with an objective, checkable ground-truth relevance set defined by a filter condition on the 3,000 indexed rows' actual metadata (e.g. "orders paid via UPI" → ground truth = every indexed row where `payment_method == "UPI"`). Retrieval is the app's real `rag_service.retrieve()` — real embedding call, real pgvector cosine search. K = 8 (`RAG_TOP_K_ROWS`, the app's actual default).

### Summary

| Metric | Value |
|---|---|
| Mean Precision@8 | **0.635** |
| Mean Recall@8 | **0.016** ⚠️ see note below |
| Macro F1 | **0.030** ⚠️ see note below |
| MRR | **0.642** |
| Mean nDCG@8 | **0.616** |
| Mean retrieval latency | 0.83s |

> **Recall/F1 caveat — read before drawing conclusions:** Recall@8 is mathematically capped near-zero here by construction, not by a flaw in the system. With only 8 rows retrieved out of a ground-truth set that's often 300–1,200+ rows (e.g. "Electronics" has 1,010 matching rows in the index), even a *theoretically perfect* retriever could score at most 8/1010 ≈ 0.008 recall. Recall@8 and the F1 derived from it are not meaningful quality signals at this K — **Precision@8, MRR, and nDCG@8 are the metrics that actually reflect retrieval quality here**, since they measure "are the top-8 results correct/well-ranked," not "did we return everything relevant."

### Per-query results

| Query | Relevant in index | Precision@8 | Recall@8 | Reciprocal Rank | nDCG@8 |
|---|---:|---:|---:|---:|---:|
| Show me orders paid using UPI | 747 | **1.00** | 0.011 | 1.00 | **1.00** |
| Show me orders paid using COD | 733 | 0.875 | 0.010 | 1.00 | 0.840 |
| Find orders in the Electronics category | 1,010 | **1.00** | 0.008 | 1.00 | **1.00** |
| Find orders in the Fashion category | 961 | **1.00** | 0.008 | 1.00 | **1.00** |
| Find laptop orders | 332 | **1.00** | 0.024 | 1.00 | **1.00** |
| Find footwear orders | 473 | **1.00** | 0.017 | 1.00 | **1.00** |
| Kitchen category orders paid by NetBanking (2 conditions) | 122 | **1.00** | 0.066 | 1.00 | **1.00** |
| Show me orders with discount above 25% | 424 | 0.00 | 0.00 | 0.00 | 0.00 |
| Show me orders with unit price above 45000 | 324 | 0.125 | 0.003 | 0.125 | 0.080 |
| Show me orders with shipping cost above 100 | 1,178 | 0.125 | 0.001 | 0.167 | 0.090 |
| Accessories orders under 10000 unit price (2 conditions) | 71 | 0.25 | 0.028 | 0.25 | 0.207 |
| Mobile orders with quantity above 3 (2 conditions) | 133 | 0.25 | 0.015 | 0.167 | 0.174 |

### The pattern this reveals

**Single-attribute categorical queries retrieve near-perfectly** (Precision@8 = 0.875–1.0, nDCG@8 = 0.84–1.0): the embedding model reliably surfaces rows matching a category/payment-method/sub-category mentioned by name.

**Numeric-threshold and compound-condition queries retrieve poorly** (Precision@8 = 0.0–0.25): vector similarity has no concept of ">45000" or "AND" — it can only match semantic "aboutness," not numeric comparison or boolean logic. This is the exact, quantified confirmation of the qualitative limitation identified earlier in this project's RAG work, and is precisely why the constrained data-query engine (real pandas filters, not vector search) was added as a complementary retrieval path for that class of question.

---

## 3. LLM Latency — Prompt Processing vs. Response Generation

**Methodology:** 8 real RAG chat questions through the actual app code path (`_build_rag_user_content` → Groq `qwen/qwen3.6-27b`). Groq's API returns authoritative server-side timing per call (`usage.prompt_time`, `usage.completion_time`, `usage.queue_time`, `usage.total_time`) — these are used directly rather than approximated from client-side timestamps.

### Summary (Groq server-side timing — authoritative, retry-immune)

| Metric | Value |
|---|---|
| Avg prompt tokens | 3,828 |
| Avg completion tokens | 127–129 |
| **Avg prompt processing time** | **0.309s** |
| **Avg response generation time** | **0.251s** |
| Avg total Groq inference time | 0.560s |
| Avg queue time (wait before processing started) | 0.113s |
| Prompt processing throughput | ~12,400 tokens/sec |
| Response generation throughput | ~516 tokens/sec |
| Avg retrieval latency (embedding + pgvector search) | 0.75–1.3s |

### Per-question detail

| Question | Prompt tokens | Completion tokens | Prompt processing (s) | Generation (s) | Total inference (s) |
|---|---:|---:|---:|---:|---:|
| What are the strongest correlations...? | 3,936 | 178 | 0.293 | 0.340 | 0.632 |
| Show me orders paid using UPI | 3,748 | 116 | 0.292 | 0.221 | 0.513 |
| Which category performs best? | 3,719 | 124 | 0.276 | 0.235 | 0.511 |
| Are there any anomalies...? | 3,916 | 132 | 0.340 | 0.267 | 0.607 |
| How reliable is this analysis? | 3,926 | 124 | 0.326 | 0.236 | 0.562 |
| Give me a real example of a delivered order... | 3,686 | 114 | 0.328 | 0.223 | 0.551 |
| Average unit price for Electronics? | 3,789 | 118 | 0.318 | 0.227 | 0.544 |
| Summarize overall data quality | 3,905 | 129 | 0.300 | 0.257 | 0.557 |

### ⚠️ Important operational finding: rate-limit-induced client latency inflation

Running these 8 questions back-to-back (even with a 4-second gap between them) caused **client-observed wall-clock time to balloon to 20–26 seconds** for most questions, despite Groq's own reported inference time staying under 0.65s. Root cause, confirmed directly: this Groq account tier has a **200,000 tokens/day** cap on `qwen/qwen3.6-27b` (this session's testing alone used 197,900/200,000 before hitting it), and a **8,000 tokens/minute** per-request cap. The Groq Python SDK retries silently on `429`/rate-limit responses (`max_retries=2` by default) — so a request that gets rate-limited doesn't fail, it just silently waits and retries, which is invisible unless you look at server-side vs. client-side timing separately as done here.

**Practical implication:** the model itself answers in ~0.5–0.6 seconds. If real users see multi-second-or-longer delays on this deployment, the model is not the bottleneck — Groq's per-account rate limits under concurrent/rapid usage are. This is directly relevant to the earlier finding this session that 6/8 concurrently-submitted analysis jobs fell back to heuristic tagging for the same underlying reason.

---

## 4. Agentic Pipeline vs. Direct Single-Shot LLM — Timing Comparison

**Methodology:** Same dataset (10,000-row `amazon_sales_dataset`), two approaches, both timed with real wall-clock measurements:
- **Agentic pipeline:** a fresh, real run through the actual API (`/api/analyze`), all 6 agents, polled to completion.
- **Direct LLM:** one single Groq call given a CSV sample and asked to produce the same *scope* of output (executive summary, key findings, data quality assessment, recommendations) — the naive approach someone might reach for before building a proper pipeline.

### Agentic pipeline (fresh run, job `9fff413343244fa9ae1f5572c2d0ee64`)

| Stage | Duration |
|---|---:|
| Agent 1 — Structural profiler | 3.01s |
| Agent 2 — Semantic tagger (LLM) | 5.61s |
| Agent 3 — Preprocessor | 3.45s |
| Agent 4 — Statistics & chart generation | **16.46s** (heaviest stage — 16 charts + full statistical suite) |
| Agent 5 — Validation guardrail | 0.07s |
| Agent 6 — Report/narrative (LLM) | 6.55s |
| **Server-side pipeline total** | **40.75s** |
| **Client-observed total** (incl. upload + polling overhead) | **44.49s** |

### Direct single-shot LLM

*Note: originally planned at 100 sample rows, reduced to 40 after hitting this account's 8,000 TPM per-request cap (100 rows needed ~12,981 tokens).*

| Metric | Value |
|---|---|
| Rows shown to the model | 40 / 10,000 (0.4% of the dataset) |
| Prompt tokens | 4,699 |
| Completion tokens | 1,172 |
| Prompt processing time | 0.374s |
| Generation time | 2.313s |
| **Total wall-clock time** | **3.32s** |

### The comparison

| | Agentic pipeline | Direct single-shot LLM |
|---|---|---|
| Wall-clock time | 44.5s | 3.3s |
| Data actually analyzed | 10,000/10,000 rows (100%) | 40/10,000 rows (0.4%) |
| Statistics computed by | pandas/NumPy/SciPy (Agents 1, 3, 4) — deterministic, verified | The LLM's own arithmetic/estimation on a tiny sample — unverified |
| Validated against source data | Yes (Agent 5 guardrail; report withheld below 0.95 confidence) | No guardrail — whatever the model says ships as-is |
| Charts generated | 16, rendered from real computed data | None |
| LLM calls | 2, narrow and targeted (schema tagging on metadata only; narrative writing from precomputed facts) | 1, broad (the model reasons over raw rows directly) |

**The direct-LLM approach is ~13x faster** in raw wall-clock time — but it only ever sees 0.4% of the dataset and every number in its output is the model's own read of that small sample, with no verification against the actual full data. The agentic pipeline is slower specifically *because* Agent 4 computes real statistics over all 10,000 rows and renders 16 real charts from them, and Agent 5 exists specifically to catch cases where the numbers don't add up — none of which a single LLM call can do by construction, regardless of how fast it responds. The speed/reliability tradeoff is the whole design rationale documented in this project's own `CLAUDE.md`: *"Statistics before stories... nothing ships unvalidated."*

---

## Appendix: Raw data files

- `retrieval_results.json` — full per-query retrieval evaluation data
- `latency_results.json` — full per-question latency data
- `agentic_vs_direct.log` — raw agentic pipeline run output
- `direct_llm_full.json` — raw direct-LLM comparison output
- `dataset_description.json` — raw dataset description data
