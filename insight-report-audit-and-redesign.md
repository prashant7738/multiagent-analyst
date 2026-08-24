# Audit & Redesign Plan — Multi-Agent Data Analyst Report

## 0. The one thing to read first

Before any UX/formatting conversation: **the underlying data appears to be synthetic/randomly generated, and several of your derived formulas don't reconcile with their own inputs.** No amount of redesign fixes that — and right now the report presents fabricated-looking numbers ("$56.4 billion in revenue") with full confidence. This is the highest-priority finding in this whole audit. Details in §1.

---

## 1. Critical Audit — what's actually wrong

### 1.1 The report contradicts itself in consecutive sections
Page 4, "In Plain English": *"you must fix the data scaling issue affecting all records."*
Page 4, "Why It Matters" (30 words later): *"the data is solid enough to act on with confidence."*

These two sentences are talking about the same dataset and say opposite things. This isn't a nuance — it's a narrative-generation bug where two agents wrote contradictory conclusions and nothing cross-checked them before publishing. This should never ship.

### 1.2 The headline "data quality" issue is a broken validation rule, not a business finding
The report flags **100% of rows** because `derived_revenue_after_discount` falls outside an expected range of **0–100** — but revenue in this dataset runs into the tens/hundreds of thousands per row. A validation rule checking "is revenue between 0 and 100" is almost certainly a leftover threshold from a different dataset or a percentage-scale check applied to a currency column. This is a **pipeline bug masquerading as a business insight**, and it's currently the lead item in your "In Plain English" summary and Risks section. Presenting a broken assertion check as if it were a finding about the user's business is the single most damaging thing in the report — it actively misleads a non-technical reader into distrusting good data, or worse, "fixing" data that isn't broken.

### 1.3 A much more serious, real data problem is never mentioned: deliveries before orders
Row-level example data (Technical Appendix) shows:
- Order A10000: ordered 2026-01-31, shipped 2026-01-31, **delivered 2026-01-08** — delivered 23 days *before* it was ordered.
- Order A10004: ordered 2026-01-27, shipped 2026-01-04, delivered 2026-01-23 — shipped 23 days before ordering.
- The days-to-ship distribution spans **−40 to +40 days**, i.e., roughly half of all "shipping" happens before the order was placed.

This is a genuine, severe temporal-integrity defect — far more consequential than the fake 0–100 rule — and the report never surfaces it. It only shows a shipping lead-time histogram with a neutral caption ("orders took −0.06 days on average"), treating a physically impossible number as if it were a normal descriptive statistic.

### 1.4 Revenue doesn't reconcile with its own inputs
Take order A10000: `quantity=3`, `unit_price=$42,467.79`, `discount=0.867`. Quantity × unit price = $127,403. Apply the stated discount and you get roughly $16,900. The report's `total_sales` for that row is **$94,339** — nowhere near either number. Same mismatch on other example rows. Either `total_sales` isn't actually computed from `quantity`, `unit_price`, and `discount`, or one of those columns is randomly generated independent of the others. Combined with §1.3, this points to **synthetic/randomly generated data with no real internal business logic** — not a live company's transaction log.

### 1.5 Profit margin (~99.6%) is not a real number
Every category shows profit margins of 99.6–99.7%. Real product businesses very rarely clear 99% margin on physical goods (Kitchen items, Laptops, Furniture). This means `derived_profit` ≈ `total_sales` almost exactly (Pearson r = 1.00, and the scatter plot literally shows a perfect line) — i.e., **cost is barely being subtracted at all**. This is the most important statistical relationship in the whole report, and the report presents it as an exciting "strong positive correlation" finding (§ How Things Connect, leading with this exact chart) rather than recognizing it as a red flag that cost data is missing, zeroed out, or the margin formula is broken.

### 1.6 The category "concentration" story is overstated
Electronics (35.15%), Home (34.38%), and Fashion (30.47%) are within 5 points of each other — essentially an even three-way split. But the report calls Electronics "the clear market leader" and "your biggest money-maker... critical to keep stocked." A 35/34/30 split isn't concentration, it's near-uniformity. Same pattern in payment method (Cod 26.2% vs Card 24.4%, a 1.8-point gap dressed up as "customers prefer Cash on Delivery... ensure cash handling is robust"). These read as manufactured insights from noise-level differences, which is exactly the "AI slop" pattern you asked me to hunt for.

### 1.7 Non-informative dimensions are treated as real business content
`customer_name`, `city`, and especially `product_name` are populated with values like "without," "school," "step," "bit," "I," "trouble," "maintain" — these are clearly placeholder/lorem-style tokens, not real product names. Any report claiming insight into "which products drive revenue" is standing on nothing here. A trustworthy pipeline should detect near-random/low-cardinality-nonsense text fields and either exclude them or flag them as unusable, rather than rendering a bar chart of "Distribution of product_name" as if it were informative.

### 1.8 Duplicated content inflates the report without adding insight
The Correlation Heatmap, the Profit-vs-Revenue-after-Discount scatter, the Monthly Total Sales Growth chart, the Total Sales histogram, the Profit Margin Trend line, and the Derived Metrics Summary panel each appear **twice**, verbatim, once in the main body and again in "Direction of travel" / near the appendix. This isn't a second, deeper look — it's the same chart, same caption style, no new framing. It roughly doubles page count (37 pages) for the same content, which actively works against the progressive-disclosure goal you described.

### 1.9 Only two months of data support a 70% "trend"
"Monthly Total Sales Growth — max MoM swing 70.4%" is computed from exactly two data points (Jan and Feb 2026), and Feb is very likely a partial month (report generated Aug 24, 2026 but only Jan–Feb rows exist, and Feb's bar is roughly a third the height of Jan's — consistent with an incomplete month, not a real decline). Presenting a 2-point trend line with a specific decimal ("70.4%") gives false statistical confidence. This should be labeled "insufficient history to assess trend" rather than charted as a finding.

### 1.10 No fact/inference/hypothesis/recommendation distinction anywhere
Every sentence in the report reads at the same confidence level — "Electronics is the clear market leader" (near-fact from the aggregation) sits next to "so keeping this category stocked and promoted is critical" (a recommendation with zero supporting evidence about inventory, promotion cost, or elasticity) with no visual or linguistic distinction between the two. This is exactly the failure mode you flagged in your brief.

### 1.11 Numeric inconsistency in the discount field
Raw `discount` values in the row samples run 20–87% (e.g., `discount: 0.867`), but `derived_discount_pct` for those same rows computes to ~0.0003% — a mismatch of roughly five orders of magnitude between two columns that are supposed to describe the same thing. This is a real, checkable bug (unit/scale mismatch in the discount formula), and it's more concrete and fixable than most of what the report currently flags as risk.

### 1.12 What the report does well (to keep)
- The "In Plain English → The Story (What happened / Why it matters / What to do)" scaffold is the right instinct — it's the one part of the report already attempting the audience-layering you want. It just needs to say true, non-contradictory things.
- Glossary with hover definitions is a good progressive-disclosure move for non-technical readers.
- The internal-consistency check (22/22 narrative figures match pipeline output) is a genuinely valuable trust mechanism — it's just checking the wrong thing (narrative-vs-pipeline, not pipeline-vs-source-data, which it says explicitly). That distinction should be surfaced, not buried in one line at the very end.
- Correctly excluding tautological pairs (total_sales vs. derived_profit) from the "Top Correlations" table in the appendix, even though — per §1.5 — that same tautological pair is still the *lead* chart in the main "How Things Connect" section. The appendix logic is right; the main-body logic contradicts it.

---

## 2. Scores (0–100)

| Dimension | Score | Why |
|---|---|---|
| Insight quality | 25 | Most "insights" are either noise-level differences or the report's own broken validation rule dressed up as a finding. |
| Business usefulness | 20 | A real business owner would walk away with two false beliefs ("Electronics dominates," "fix the 0–100 scaling bug") and no visibility into the two real problems (§1.3, §1.5). |
| Technical depth | 45 | Correct correlation math, decent appendix tables, real z-score outlier methodology — but no causal reasoning, no segmentation beyond one dimension at a time, no cross-agent validation of contradictions. |
| Visualization | 40 | Charts are clean individually; titles are descriptive, not insight-driven ("Monthly Total Sales Growth" instead of stating the finding); heavy duplication. |
| UX/readability | 30 | 37 pages, same charts twice, executive summary buried after "In Plain English" and "The Story," which themselves disagree with each other. |
| Actionability | 30 | Recommendations exist but aren't tied to evidence strength or expected impact; "investigate Accessories" repeats three times in different words. |
| AI reasoning quality | 20 | Failed to catch its own internal contradiction (§1.1), failed to recognize a near-1.0 correlation as a red flag rather than a headline (§1.5), failed to notice temporally impossible dates (§1.3). |
| Data storytelling | 25 | No fact/inference/hypothesis/recommendation separation; no second-order insights (the brief explicitly asked for "Product A vs Product B" style reasoning — none appears anywhere). |
| Novelty | 15 | Every finding is a Level-1 "what happened" statement (biggest category, most common payment method). Nothing at Level 3–5 (predictive/prescriptive/strategic).|
| Trustworthiness | 20 | The self-contradiction in §1.1 and the false-confident "$56.4 billion in revenue" claim on data that doesn't reconcile internally are trust-breaking, not just cosmetic issues. |

**Overall: 27/100.** The pipeline is structurally capable (real stats, real z-scores, a decent narrative scaffold) but the reasoning layer isn't validating its own outputs, and the underlying dataset likely isn't real enough to support confident business claims in the first place.

---

## 3. Ten biggest problems, ranked by impact

1. **Self-contradiction within the same page** (§1.1) — destroys trust immediately.
2. **Broken validation rule presented as the top business risk** (§1.2) — actively misleads the reader.
3. **Real data-integrity defect (delivery before order) never detected** (§1.3).
4. **Revenue doesn't reconcile with quantity × price × discount** (§1.4) — undermines every dollar figure in the report.
5. **99.6% profit margin never questioned** (§1.5) — the report's single strongest correlation is treated as a headline instead of a red flag.
6. **No signal-vs-noise filter** — near-even splits (35/34/30, 26/25/25/24) reported as decisive findings (§1.6).
7. **Meaningless text fields (product/customer/city names) charted as if informative** (§1.7).
8. **~40% of the report is duplicated content** (§1.8) — actively works against the progressive-disclosure goal.
9. **Two-point trend line reported with false precision** (§1.9).
10. **No fact/inference/hypothesis/recommendation labeling anywhere** (§1.10) — the report can't be safely acted on because the reader can't tell what's proven vs. suggested.

## 4. Ten most valuable improvements, ranked by priority

1. Add a cross-agent contradiction check before publishing (would have caught §1.1 immediately).
2. Replace/remove the 0–100 validation rule; validate rules like this against actual observed column ranges, not hardcoded assumptions.
3. Add a temporal-logic validator: flag any row where `delivery_date < ship_date < order_date` order is violated — this is a structural check, not a statistical outlier check, and belongs in the same tier as the discount-bounds rule that already exists.
4. Add a formula-reconciliation check: recompute `total_sales` from `quantity × unit_price × (1-discount)` and flag rows (or the whole dataset) where it doesn't match within tolerance.
5. Add a "near-tautological/near-1.0 correlation" guard: when r > 0.98 between two derived metrics, treat it as a data-quality signal to investigate (missing cost data, duplicated columns) rather than a headline "how things connect" chart.
6. Add a materiality/effect-size threshold before a comparison is allowed to become a narrative claim — e.g., don't call something "the clear leader" unless it beats the next-highest group by some real margin (not 0.8 points).
7. Add a cardinality/entropy check on categorical text fields before charting them as insights — flag columns that look like random tokens.
8. De-duplicate the report: each chart should appear once, in the section where it's most decision-relevant.
9. Add minimum-sample-size gating on trend claims (a 2-point MoM comparison shouldn't get a decimal-precision "swing" label).
10. Tag every sentence in the narrative generator with Fact / Inference / Hypothesis / Recommendation and render them with distinct visual treatment.

---

## 5. Proposed report structure (redesigned)

| # | Page | Purpose | Audience | Key content |
|---|---|---|---|---|
| 1 | Cover + Data Trust Panel | Set expectations before any numbers are read | Both | Data quality score **and**, new: a "Can this data be trusted for decisions?" panel that surfaces §1.3/§1.4/§1.5-style structural issues *before* the executive summary, not after it |
| 2 | Executive Summary | Everything in one page | Business owner | Top 3 real findings, top 1 real risk, top 3 actions — nothing that contradicts itself |
| 3 | Business Snapshot | Orientation | Business owner | 4–5 KPIs max, each with a materiality check (is the gap real or noise?) |
| 4 | What Happened / Why | Diagnostic | Business owner, then technical | Only findings that clear the effect-size bar |
| 5 | Hidden Insights | The strongest section | Both | Genuine second-order findings only — if none clear the bar honestly, say so rather than manufacturing them |
| 6 | Risks & Data Trust Detail | The real risks | Both | §1.3 and §1.4-style structural defects, ranked by severity, not the fake 0–100 rule |
| 7 | Recommendations | Action | Business owner | Priority/Action/Reason/Impact/Effort table, each tagged with evidence strength |
| 8 | Deep Dive | Full stats | Technical | Correlation tables, distributions, appendix — shown once |
| 9 | Methodology & Data Quality | Caveats | Technical | Explicit statement on whether this dataset shows signs of being synthetic/test data, and what that means for the conclusions above |

---

## 6. Before → After examples

**1.**
*Current:* "Electronics is your biggest money-maker, bringing in over $56 billion, so keeping this category stocked and promoted is critical."
*Why weak:* States a near-tie (35% vs. 34%) as dominance; jumps straight to a merchandising recommendation with no cost or elasticity data behind it; the dollar figure itself is unreconciled with the row-level formula (§1.4).
*Improved:* "Electronics (35.2%), Home (34.4%), and Fashion (30.5%) are close to an even three-way split — no category is currently dominant. Before making stocking decisions, note that dollar totals in this dataset don't reconcile with unit price × quantity at the row level (see Data Trust panel), so treat these shares as directional, not exact."
*Why better:* Accurate about the actual margin between groups; doesn't invent a recommendation the data can't support; surfaces the trust caveat where it's decision-relevant instead of burying it in an appendix.

**2.**
*Current:* "Customers prefer paying Cash on Delivery (26.17%) over using Cards (24.38%), so ensure your cash handling processes are robust."
*Why weak:* A 1.8-point gap across four near-equal payment methods is noise, not preference; the recommendation doesn't follow from the finding.
*Improved:* "Payment method share is essentially even across all four methods (24–26% each) — there's no dominant payment preference in this data."
*Why better:* Doesn't manufacture a decision-driving claim out of a gap smaller than normal week-to-week variance would produce.

**3.**
*Current:* "A data quality rule flags 100% of rows because 'derived_revenue_after_discount' values fall outside the 0-100 range, indicating a likely scaling issue."
*Why weak:* This is the report's own bug, not a fact about the business — the "0-100" expected range is almost certainly wrong for a currency field with values in the tens of thousands.
*Improved:* "One internal validation rule expects revenue values between 0 and 100 and is flagging every row. This rule is very likely misconfigured for this dataset's currency scale rather than describing a real problem — recommend the rule be reviewed rather than the source data."
*Why better:* Correctly assigns the defect to the pipeline instead of the business, and gives a fixable, specific next step.

**4.**
*Current:* "Orders took -0.06 days on average to ship, with a median of 0.0 days and a range of -40.0 to 40.0 days."
*Why weak:* States a physically impossible range (deliveries before orders) as neutral descriptive statistics, with no flag.
*Improved:* "Roughly half of all orders in this dataset show ship or delivery dates that occur *before* the order date — including some deliveries dated 23 days before the order was placed. This is a data-integrity defect, not a shipping-performance metric, and any shipping-time analysis should be treated as unreliable until it's fixed."
*Why better:* Correctly identifies a serious structural defect instead of quietly averaging over it.

**5.**
*Current:* "Profit vs Revenue After Discount — Link strength (r): 1" presented as the lead item in "How things connect."
*Why weak:* r=1.00 between profit and revenue almost always means one is derived from the other with near-zero cost subtracted — it's a data artifact, not a discovered relationship.
*Improved:* "Profit and revenue move in perfect lockstep (r=1.00) across every record, implying costs are close to zero in this dataset. Either cost data isn't being captured, or margins are unrealistically high (avg. 99.6%) for a physical-goods business — worth checking the cost/COGS field before trusting any profit-based conclusion in this report."
*Why better:* Converts what the pipeline treated as a finding into the actual finding: something is wrong with cost data.

---

## 7. Insight-engine / pipeline changes (Agents 1–6)

- **Cross-agent contradiction detection**: before final assembly, run a pass that checks whether any two narrative statements assert opposite things about the same fact (§1.1). Simple heuristic: flag sentence pairs with high lexical/topical overlap but opposite-polarity claims for human or secondary-agent review.
- **Structural-check agent needs a "does this rule make sense for this column's actual distribution" pre-check.** Right now a rule (0–100 bounds) fired on 100% of rows and was accepted without a sanity check ("does the rule's expected range look anything like the observed range?"). Any rule that fires on >95% of rows should be treated as *probably a broken rule*, not a dataset-wide catastrophe, and downgraded/flagged for review rather than promoted to the top of the report.
- **Add temporal-logic and formula-reconciliation as first-class structural checks**, same tier as the existing discount-bounds checks — these caught nothing in this run despite being more consequential (§1.3, §1.4).
- **Correlation agent should treat r > 0.98 between two derived (non-tautological-by-name) columns as a data-quality flag first, insight second** — right now it's the opposite.
- **Add a materiality gate before the narrative agent is allowed to make a comparative claim** ("X is the leader," "customers prefer Y") — require a minimum effect size (e.g., >1.5x the next group, or a stated confidence interval) before that language is permitted.
- **Add a categorical-cardinality/coherence check**: before charting or narrating a text column, check whether its values look like real business entities (product names, city names) vs. random tokens; suppress or caveat columns that fail.
- **Insight ranking**: score each candidate insight on novelty, effect size, evidence strength, and actionability before inclusion; cut anything below threshold rather than including it for page count.
- **Evidence tagging**: require every generated sentence to carry a Fact/Inference/Hypothesis/Recommendation tag from generation time, not applied after the fact — this is what makes the downstream visual distinction (§6 above) possible at all.
- **De-duplication pass**: before final render, hash chart configs and drop repeats.
- **Sample-size gating**: any trend/rate-of-change computed from fewer than ~4–5 time periods should be labeled "insufficient history" rather than charted with decimal precision.

---

## 8. Implementation roadmap

**Phase 1 — Critical fixes (do first, cheapest)**
- Fix/remove the 0–100 validation rule.
- Add the contradiction check between "In Plain English" and "Why It Matters."
- De-duplicate repeated charts.
- Add materiality gating on comparative claims (Electronics/Home/Fashion, payment methods).

**Phase 2 — Intelligence improvements**
- Temporal-logic validator (delivery-before-order).
- Formula-reconciliation validator (revenue vs. quantity × price × discount).
- Correlation-agent flag for r > 0.98 as data-quality signal.
- Fact/Inference/Hypothesis/Recommendation tagging in the narrative agent.

**Phase 3 — Visualization & UX**
- Restructure per §5 (Data Trust panel before Executive Summary).
- Insight-driven chart titles (state the finding, not the chart type).
- Progressive disclosure layers (Layer 1 summary → Layer 4 technical appendix), single occurrence per chart.

**Phase 4 — Advanced intelligence**
- Cardinality/coherence check for categorical text fields, with automatic suppression of unusable columns.
- Insight scoring/ranking system (novelty, impact, confidence, actionability) gating what makes the final report.
- Cross-run consistency tracking (does a finding persist across re-runs on updated data, or was it a one-off artifact).

---

## Bottom line

Right now this report would tell a business owner three things that are actively wrong (deliveries happen before orders and nobody flagged it; a broken 0–100 rule is presented as the top risk instead of that; a near-perfect profit/revenue correlation is celebrated instead of investigated) and several things that are true but trivial (three categories are roughly evenly split; four payment methods are roughly evenly split). The fix isn't more polish — it's giving the pipeline the ability to catch its own contradictions and distinguish "the data looks broken" from "my validation rule is broken," before any of it reaches the page.
