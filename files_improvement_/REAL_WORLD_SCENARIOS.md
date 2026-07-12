# Real-World Data Problems & Solutions

## Problem 1: Sentinel Values Not Detected

### ❌ Current Behavior
**Input Data:**
```
user_id | age | salary
1       | 25  | 45000
2       | 30  | -1        ← Missing data encoded as -1
3       | 28  | 52000
4       | -999| 48000     ← Missing age encoded as -999
```

Agent 1 treats `-1` and `-999` as real data. Agent 3 tries to "improve" them:
- Statistical calculations polluted by fake values
- Outlier detection flags legitimate values
- Imputation skewed by sentinels
- Final data quality score artificially low

### ✅ Solution with Improvement
**Agent 1 now detects:**
```json
{
  "implicit_missing_values": {
    "age": [
      {"sentinel": -999, "count": 1, "pct": 20.0, "recommendation": "treat as missing"}
    ],
    "salary": [
      {"sentinel": -1, "count": 1, "pct": 20.0, "recommendation": "treat as missing"}
    ]
  }
}
```

**Agent 3 can now:**
- Identify true nulls vs. sentinels
- Use appropriate imputation (median, not mean contaminated by -999)
- Report accurate statistics
- Quality score reflects actual data quality

---

## Problem 2: Wrong Imputation Strategy

### ❌ Current Behavior
**Input: Right-skewed salary data**
```
salary: [30000, 32000, 31500, 35000, 32500, ..., 500000]
        # Most values 30-35k, one outlier 500k (CEO)
        # Missing: 2 values
```

Default Agent 3 behavior: Uses mean imputation
- Mean = (30000+32000+31500+...+500000) / n ≈ $42,000
- Imputes missing as $42,000
- But typical employees earn $31,000-$32,000
- **Result: Overstates salary for missing values**

### ✅ Solution with Improvement
**New adaptive imputation detects skewness:**
```python
skewness = 2.3  # High positive skew
→ Use median imputation instead
median = $31,750
→ Imputes realistically for typical employee
```

**Also available to Agent 2 for better schema:**
```json
{
  "semantic_tag": "currency",
  "distribution": {
    "skewness": 2.3,
    "distribution_type": "right_skewed"
  },
  "recommended_imputation": "median"
}
```

---

## Problem 3: Outliers vs. Legitimate High Values

### ❌ Current Behavior
**Input: E-commerce transaction dataset**
```
amount: [12.50, 15.99, 18.75, ..., 2500.00]
       # 99% of values $10-$50
       # Few bulk orders $500-$2500 (legitimate)
```

IQR method (current):
- Q1 = $15, Q3 = $35, IQR = $20
- Upper bound = Q3 + 1.5×IQR = $35 + $30 = **$65**
- Clips all values > $65 to $65
- **Result: Destroys legitimate bulk orders**

### ✅ Solution with Improvement
**Agent 1 now provides distribution insights:**
```json
{
  "distribution_analysis": {
    "skewness": 1.8,
    "has_significant_outliers": true,
    "outlier_count_iqr": 45,
    "outlier_count_zscore": 12,
    "concern": "bimodal distribution - bulk orders vs. retail"
  }
}
```

**Agent 2 tags appropriately:**
```json
{
  "semantic_tag": "currency",
  "confidence": {
    "confidence_score": 65,
    "evidence": ["currency symbols detected", "high outlier count suggests data anomaly"]
  }
}
```

**Agent 3 uses context-aware clipping:**
```python
# For currency with high outlier count and bimodal distribution
# Use 1st-99th percentile instead of IQR
lower = 5th_percentile = $12.00
upper = 99th_percentile = $2400.00
# Preserves legitimate business transactions
```

---

## Problem 4: Semantic Tag Confidence Issues

### ❌ Current Behavior
**Input: Ambiguous column**
```
booking_id | booking_ref
1001       | BOOK-2024-001
1002       | BOOK-2024-002
1003       | BOOK-2024-003
```

Current Agent 2: Unsure if `booking_ref` is identifier or categorical_label
- Uses fallback heuristics
- No confidence score
- Downstream Agent 3 treats it conservatively
- May over-encode or under-encode

### ✅ Solution with Improvement
**Agent 2 now scores confidence:**
```json
{
  "booking_ref": {
    "semantic_tag": "identifier",
    "confidence": {
      "confidence_score": 78,
      "confidence_level": "high",
      "evidence": [
        "name_match: 'id' keyword in column name",
        "type_alignment: string ✓ identifier",
        "quality: zero nulls in identifier",
        "cardinality: high uniqueness ✓ identifier"
      ]
    }
  }
}
```

Agent 3 can now:
- Trust the tagging and use identifier-specific handling
- Not encode it (identifiers shouldn't be one-hot encoded)
- Handle it specially in validation
- Make confident preprocessing decisions

---

## Problem 5: Missing Data Quality Context

### ❌ Current Behavior
**Messy real-world dataset:**
```
- 35% missing values (incomplete data entry)
- 2500 duplicate rows (data pipeline error)
- Multiple sentinel values (-1, 999, "N/A")
- 40% outliers (data quality issue or domain-specific?)
```

Agent 3 treats all datasets the same:
- Strict imputation (might be too aggressive)
- Or lenient imputation (might be too permissive)
- No early warning about data quality
- Quality score doesn't reflect actual fitness-for-purpose

### ✅ Solution with Improvement
**Agent 2 now provides risk assessment:**
```json
{
  "__metadata__": {
    "data_quality_assessment": {
      "risk_assessment": "critical",
      "preprocessing_recommendation": "strict",
      "quality_issues": [
        "critical_missingness: 35.0%",
        "critical_duplication: 8.3%",
        "multiple_implicit_nulls: 4 columns affected"
      ]
    }
  }
}
```

Agent 3 now:
- Applies strict preprocessing profile (more aggressive cleaning)
- Validates every step carefully
- Reports detailed quality metrics by component:
  ```json
  {
    "completeness": 65,     # How many nulls?
    "consistency": 72,      # Validation pass rate?
    "deduplication": 91,    # Duplicate rate?
    "structure": 85         # Rows preserved?
  }
  ```
- Stakeholders understand WHY the quality score is what it is

---

## Problem 6: Distribution-Driven Transformations Ignored

### ❌ Current Behavior
**Log-normally distributed data (income, website traffic, latencies):**
```
values: [100, 150, 200, 250, 500, 1000, 5000, 50000]
```

Current min-max scaling:
- min = 100, max = 50000
- 100 → 0.0
- 50000 → 1.0
- Everything else compressed into [0, 0.1]
- **Loses most of the variance**

### ✅ Solution with Improvement
**Agent 1 detects distribution:**
```json
{
  "distribution_analysis": {
    "skewness": 3.2,
    "distribution_type": "right_skewed",
    "is_normal": false,
    "recommendation": "consider log transformation before scaling"
  }
}
```

**Agent 3 can then:**
- Apply log transformation first (optional enhancement)
- Or use quantile-based scaling (percentile bounds)
- Preserves the distributional shape
- Better for downstream modeling

---

## Problem 7: Categorical Encoding Mismatch

### ❌ Current Behavior
**Mixed cardinality categorical data:**
```
shirt_size: ["XS", "S", "M", "L", "XL"]        # 5 values - ordinal!
color: ["red", "blue", "green", ..., "coral"]  # 500+ values - high cardinality!
```

Agent 2 default: One-hot encode everything marked as categorical
- `shirt_size`: Creates 5 binary columns (wasteful, ignores order)
- `color`: Creates 500+ sparse columns (noise, curse of dimensionality)

### ✅ Solution with Improvement
**Agent 2 now intelligently selects encoding:**
```json
{
  "shirt_size": {
    "semantic_tag": "categorical_label",
    "encoding_strategy": {
      "method": "ordinal",
      "order": ["XS", "S", "M", "L", "XL"],
      "reason": "apparent order detected in category values"
    }
  },
  "color": {
    "semantic_tag": "categorical_label",
    "encoding_strategy": {
      "method": "none",
      "reason": "high cardinality (500) - encoding would create sparse features"
    }
  }
}
```

Agent 3 now:
- Encodes `shirt_size` as [0, 1, 2, 3, 4] preserving order
- Leaves `color` unencoded (or suggests target encoding)
- Much more efficient and meaningful

---

## Problem 8: Quality Score Opacity

### ❌ Current Behavior
**Final output:**
```
Data Quality Score: 73/100
```

Stakeholders don't know:
- Is 73 "acceptable"?
- What part of the pipeline failed?
- Is the data safe to use?
- What should we do differently?

### ✅ Solution with Improvement
**New detailed quality report:**
```json
{
  "overall_quality_score": 73,
  "quality_assessment": "good",
  "component_scores": {
    "completeness": 82,      # How complete is the data?
    "consistency": 68,       # How many validation checks failed?
    "deduplication": 95,     # Are duplicates removed?
    "structure": 72          # How many rows were preserved?
  },
  "metrics": {
    "raw_null_pct": 15.2,
    "clean_null_pct": 8.1,
    "completeness_improvement": 7.1,
    "duplicate_rate_pct": 2.3,
    "row_survival_rate": 96.8,
    "validation_pass_rate": 68.0
  }
}
```

Now stakeholders understand:
- **Completeness (82)**: Data is mostly complete after cleaning
- **Consistency (68)**: Some validation checks failed - review needed
- **Deduplication (95)**: Duplicate removal worked well
- **Structure (72)**: Most rows preserved, acceptable data loss
- **Recommendation**: Good quality, but investigate the 68% consistency rate

---

## Problem 9: Currency Cleaning Failures Silent

### ❌ Current Behavior
**International transactions dataset:**
```
amount_usd: ["$1,234.56", "€1.000,00", "₹50,000", "invalid"]
```

Current currency cleaner:
- Strips most symbols
- Handles commas/periods
- Replaces unparseable with NaN
- No record of what failed

Result: Data analyst sees:
```
1234.56
1000.00
50000.00
NaN
```

No way to know that row 4 failed to parse. Lost visibility.

### ✅ Solution with Improvement
**Enhanced currency cleaning with audit trail:**
```python
# Agent 3 now creates failure flag columns
amount_usd_parse_failed = [0, 0, 0, 1]

# And comprehensive logging
preprocessing_log: [
  "amount_usd: currency cleaned, 1 unparseable value → NaN, "
  "1 failures flagged in [amount_usd_parse_failed]"
]
```

**Full audit available:**
```json
{
  "column_ledger": {
    "amount_usd": {
      "action": "currency_clean",
      "before_nulls_pct": 0.0,
      "after_nulls_pct": 0.05,
      "parse_fail_pct": 0.05,
      "parse_fail_count": 1
    }
  }
}
```

Data analysts can now:
- See exactly which rows failed parsing
- Decide whether to drop or manually fix
- Audit the cleaning process
- Build confidence in the results

---

## Problem 10: Correlation and Redundancy Invisible

### ❌ Current Behavior
**Dataset with redundant features:**
```
customer_age | customer_age_years | age_in_years
    25       |      25            |     25
    30       |      30            |     30
    28       |      28            |     28
```

Current pipeline processes all three as independent features
- Multicollinearity not detected
- Model training gets confused
- Model interpretability suffers
- No warning to data scientist

### ✅ Solution with Improvement
**Agent 1 now detects relationships:**
```json
{
  "column_relationships": {
    "numeric_correlations": [
      {
        "col1": "customer_age",
        "col2": "customer_age_years",
        "correlation": 0.9998,
        "concern": "potential redundancy - consider dropping one"
      }
    ]
  }
}
```

**Data scientist now sees:**
- Which columns are highly correlated
- Which are potential keys
- Early warning about redundancy
- Can make informed decisions about feature engineering

---

## Summary: Impact Across Pipeline

| Problem | Before | After |
|---------|--------|-------|
| Sentinel values | Silent data corruption | Detected and flagged |
| Imputation choice | One-size-fits-all | Adaptive to distribution |
| Outlier handling | Destroys legitimate values | Context-aware bounds |
| Semantic confidence | Unknown | 0-100 score with evidence |
| Data quality signals | None | Risk assessment provided |
| Distribution insights | Ignored | Used for transformations |
| Categorical encoding | Wasteful | Intelligent selection |
| Quality metrics | Single number | Detailed component breakdown |
| Cleaning transparency | Opaque | Full audit trail |
| Redundancy detection | Invisible | Correlation analysis |

---

## Migration Path for Your Data

### Step 1: Enable Agent 1 Enhancements
- Add distribution analysis
- Activate implicit missing detection
- Check `raw_profile["column_relationships"]`

### Step 2: Review Agent 2 Output
- Check confidence scores in `schema_blueprint`
- Review data quality assessment in `__metadata__`
- Adjust preprocessing profile if needed

### Step 3: Observe Agent 3 Behavior
- Adaptive imputation applied automatically
- Quality score shows component breakdown
- Preprocessing log shows what happened

### Step 4: Use New Insights
- Fix data quality issues upstream (if possible)
- Use confidence scores for model feature selection
- Trust detailed quality metrics for stakeholder communication

---

## Recommended Testing Dataset

Create a test CSV with known problems:
```csv
id,age,income,status,amount,created_date
1,25,45000,active,150.50,2024-01-01
2,-999,52000,active,-1,2024-01-02
3,28,n/a,inactive,0,0000-00-00
4,30,48000.5,active,2500.00,2024-01-04
5,25,45000,active,150.50,2024-01-01
```

**Expected improvements:**
- Agent 1: Detects `age=-999`, `income='n/a'`, `amount=-1`, `created_date='0000-00-00'` as implicit nulls
- Agent 2: Confidence scores low due to quality issues; recommends strict preprocessing
- Agent 3: Uses median imputation (age), mode for status, smart clipping for amount, quality score reflects the real messy state

This is your validation that improvements are working.
