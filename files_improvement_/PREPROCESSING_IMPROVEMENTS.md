# MultiAgent DataAnalyst: Preprocessing Improvements Guide

## 🎯 Strategic Overview

The current pipeline is solid but can be enhanced in three key areas:
1. **Agent 1**: Deeper structural insights and anomaly detection
2. **Agent 2**: More sophisticated semantic inference and confidence scoring
3. **Agent 3**: Adaptive preprocessing strategies and better quality scoring

---

## 📊 AGENT 1: Enhanced Structural Profiling

### Current State
✅ Basic profiling, encoding detection, delimiter handling
❌ Limited outlier detection, no correlation analysis, missing pattern recognition

### Recommended Changes

#### 1. **Add Distribution Analysis**
```python
def _analyze_column_distribution(series: pd.Series) -> dict:
    """Detect skewness, kurtosis, and distribution type."""
    non_null = series.dropna()
    if len(non_null) < 10:
        return {"skewness": 0, "kurtosis": 0, "distribution_type": "insufficient_data"}
    
    from scipy.stats import skew, kurtosis, shapiro
    
    numeric = pd.to_numeric(non_null, errors="coerce").dropna()
    if len(numeric) < 3:
        return {"skewness": 0, "kurtosis": 0, "distribution_type": "not_numeric"}
    
    skewness = float(skew(numeric))
    kurt = float(kurtosis(numeric))
    
    # Shapiro-Wilk test for normality (works for n < 5000)
    if len(numeric) <= 5000:
        _, p_value = shapiro(numeric)
        is_normal = p_value > 0.05
    else:
        is_normal = abs(skewness) < 0.5 and abs(kurt) < 1
    
    return {
        "skewness": round(skewness, 3),
        "kurtosis": round(kurt, 3),
        "is_normal_distribution": is_normal,
        "distribution_type": "normal" if is_normal else "skewed" if abs(skewness) > 0.5 else "symmetric"
    }
```

#### 2. **Detect Implicit Missing Values**
```python
def _detect_implicit_missingness(df: pd.DataFrame) -> dict:
    """Find patterns like -1, 999, 0000-00-00, or column-specific sentinels."""
    implicit_patterns = {}
    
    for col in df.columns:
        series = df[col]
        implicit_flags = []
        
        # Check for numeric sentinels
        if pd.api.types.is_numeric_dtype(series):
            numeric = pd.to_numeric(series, errors="coerce")
            # Common sentinel values
            for sentinel in [-1, -999, 9999, 0]:
                count = (numeric == sentinel).sum()
                if count > 0 and count / len(numeric) > 0.01:  # >1% of data
                    implicit_flags.append({
                        "sentinel": sentinel,
                        "count": int(count),
                        "pct": round((count / len(numeric)) * 100, 2)
                    })
        
        # Check for string patterns (0000-00-00, empty strings after strip)
        if pd.api.types.is_object_dtype(series):
            stripped = series.astype("string").str.strip()
            for pattern in ["0000-00-00", "1900-01-01", "n/a", "none", ""]:
                count = (stripped == pattern).sum()
                if count > 0 and count / len(series) > 0.01:
                    implicit_flags.append({
                        "pattern": pattern,
                        "count": int(count),
                        "pct": round((count / len(series)) * 100, 2)
                    })
        
        if implicit_flags:
            implicit_patterns[col] = implicit_flags
    
    return implicit_patterns
```

#### 3. **Add Outlier Pre-Detection**
```python
def _detect_potential_outliers(series: pd.Series) -> dict:
    """Detect outliers using multiple methods for early warning."""
    non_null = series.dropna()
    if len(non_null) < 10:
        return {}
    
    numeric = pd.to_numeric(non_null, errors="coerce").dropna()
    if len(numeric) < 4:
        return {}
    
    # IQR method
    q1 = numeric.quantile(0.25)
    q3 = numeric.quantile(0.75)
    iqr = q3 - q1
    
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    
    iqr_outliers = ((numeric < lower_bound) | (numeric > upper_bound)).sum()
    
    # Z-score method
    from scipy import stats
    z_scores = np.abs(stats.zscore(numeric, nan_policy='omit'))
    z_outliers = (z_scores > 3).sum()
    
    return {
        "iqr_outlier_count": int(iqr_outliers),
        "iqr_outlier_pct": round((iqr_outliers / len(numeric)) * 100, 2),
        "z_score_outlier_count": int(z_outliers),
        "z_score_outlier_pct": round((z_outliers / len(numeric)) * 100, 2),
        "iqr_bounds": {"lower": float(lower_bound), "upper": float(upper_bound)},
        "has_significant_outliers": iqr_outliers > (len(numeric) * 0.05)  # >5%
    }
```

#### 4. **Detect Column Relationships Early**
```python
def _detect_column_relationships(df: pd.DataFrame) -> dict:
    """Find potential keys, parent-child relationships, and correlations."""
    relationships = {
        "potential_keys": [],
        "potential_foreign_keys": [],
        "numeric_correlations": [],
        "suspicious_duplicates": []
    }
    
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    
    # Find strong correlations
    if len(numeric_cols) >= 2:
        corr_matrix = df[numeric_cols].corr()
        for i, col1 in enumerate(numeric_cols):
            for col2 in numeric_cols[i+1:]:
                corr_val = abs(corr_matrix.loc[col1, col2])
                if corr_val > 0.95:  # Very strong correlation
                    relationships["numeric_correlations"].append({
                        "col1": col1,
                        "col2": col2,
                        "correlation": round(float(corr_val), 3),
                        "warning": "highly correlated - may indicate redundancy or multicollinearity"
                    })
    
    # Detect potential keys
    for col in df.columns:
        unique_ratio = df[col].nunique() / len(df)
        if unique_ratio > 0.98 and df[col].isna().sum() == 0:
            relationships["potential_keys"].append(col)
    
    return relationships
```

### Integration Point in agent1_structural_profiler():
```python
# Add after column_profiles loop, before creating raw_profile:
distribution_analysis = {}
implicit_missing = _detect_implicit_missingness(df)
relationships = _detect_column_relationships(df)

for col in df.columns:
    distribution_analysis[col] = _analyze_column_distribution(df[col])
    # Add outlier detection
    if df[col].dtype in [np.float64, np.int64]:
        column_profiles[col]["outlier_analysis"] = _detect_potential_outliers(df[col])

raw_profile["distribution_analysis"] = distribution_analysis
raw_profile["implicit_missing_values"] = implicit_missing
raw_profile["column_relationships"] = relationships
```

---

## 🏷️ AGENT 2: Advanced Semantic Inference

### Current State
✅ LLM-based tagging with fallback, null policies
❌ No confidence scoring, limited domain adaptation, no data quality signals

### Recommended Changes

#### 1. **Add Confidence Scoring**
```python
def _calculate_semantic_confidence(
    column_name: str,
    profile: dict,
    inferred_type: str,
    semantic_tag: str,
    format_hints: dict
) -> dict:
    """Calculate confidence score for semantic tag inference (0-100)."""
    score = 50  # baseline
    evidence_points = []
    
    # Name-based signals
    name_tokens = _name_tokens(column_name)
    if semantic_tag in ["identifier", "currency", "datetime"]:
        # Strong semantic tags should have name support
        keywords = {
            "identifier": {"id", "identifier", "uuid", "key", "code"},
            "currency": {"sales", "revenue", "cost", "price", "amount"},
            "datetime": {"date", "time", "timestamp", "created", "updated"}
        }
        if name_tokens & keywords.get(semantic_tag, set()):
            score += 20
            evidence_points.append(f"column_name_hint: {semantic_tag} keyword found")
    
    # Type alignment
    type_alignment = {
        "currency": ["numeric"],
        "datetime": ["datetime"],
        "identifier": ["string", "numeric"],
        "count": ["numeric"],
        "percentage": ["numeric"],
        "geographic": ["string"],
        "categorical_label": ["string"]
    }
    
    if inferred_type in type_alignment.get(semantic_tag, []):
        score += 15
        evidence_points.append(f"type_alignment: {inferred_type} matches {semantic_tag}")
    
    # Format hints
    if semantic_tag == "currency" and format_hints.get("currency_like"):
        score += 15
        evidence_points.append("format_hint: currency symbols detected")
    
    if semantic_tag == "datetime" and format_hints.get("date_like"):
        score += 15
        evidence_points.append("format_hint: date patterns detected")
    
    # Cardinality signals
    missing_rate = float(profile.get("missing_rate_pct", 0))
    unique_count = int(profile.get("unique_count", 0))
    
    if semantic_tag == "identifier":
        if missing_rate == 0:
            score += 10
            evidence_points.append("quality: no missing values in identifier")
    elif semantic_tag == "categorical_label":
        if unique_count < 20 and unique_count > 1:
            score += 10
            evidence_points.append(f"cardinality: {unique_count} unique values suitable for categorical")
    
    # Penalize high uncertainty
    if missing_rate > 50:
        score -= 10
        evidence_points.append(f"penalty: high missingness ({missing_rate}%)")
    
    return {
        "confidence_score": min(100, max(0, score)),
        "evidence": evidence_points,
        "confidence_level": "high" if score >= 70 else "medium" if score >= 50 else "low"
    }
```

#### 2. **Enhance Semantic Tag Inference with Context**
```python
def _infer_semantic_tag_contextual(
    column_name: str,
    profile: dict,
    inferred_type: str,
    all_columns: list,
    raw_profile: dict
) -> str:
    """Infer semantic tags using column context and relationships."""
    name = column_name.lower()
    tokens = _name_tokens(column_name)
    
    # Check for related columns (e.g., if "user_id" exists, "user_email" is likely related)
    related_cols = [c.lower() for c in all_columns if column_name.lower() in c.lower() or c.lower() in column_name.lower()]
    
    # CONTEXT: If user_id exists and this is a text column, likely an identifier-like attribute
    if inferred_type == "string" and len(related_cols) > 1:
        if any("id" in c for c in related_cols):
            return "categorical_label"  # supporting column, not key itself
    
    # Check temporal patterns: if multiple datetime cols exist, this is likely a dimension
    datetime_cols = [
        c for c in all_columns 
        if raw_profile.get("columns", {}).get(c, {}).get("format_hints", {}).get("date_like")
    ]
    if len(datetime_cols) > 1 and format_hints.get("date_like"):
        return "datetime"
    
    # Default fallback with original logic
    return _infer_semantic_tag_from_metadata(column_name, profile, inferred_type)
```

#### 3. **Add Data Quality Signals**
```python
def _assess_data_quality_signals(df: pd.DataFrame, raw_profile: dict) -> dict:
    """Extract signals that impact downstream preprocessing quality."""
    signals = {
        "data_quality_concerns": [],
        "recommended_preprocessing_rigor": "balanced",  # strict, balanced, lenient
        "risk_level": "low"
    }
    
    total_cells = df.shape[0] * df.shape[1]
    missing_pct = (df.isna().sum().sum() / total_cells) * 100
    duplicate_pct = (df.duplicated().sum() / len(df)) * 100
    
    # Assess overall quality
    if missing_pct > 40:
        signals["data_quality_concerns"].append(f"high_missingness: {missing_pct:.1f}%")
        signals["recommended_preprocessing_rigor"] = "strict"
        signals["risk_level"] = "high"
    elif missing_pct > 20:
        signals["data_quality_concerns"].append(f"moderate_missingness: {missing_pct:.1f}%")
    
    if duplicate_pct > 10:
        signals["data_quality_concerns"].append(f"high_duplication: {duplicate_pct:.1f}%")
        signals["risk_level"] = "high"
    
    # Check for potential data entry errors
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        if col in raw_profile.get("columns", {}):
            profile = raw_profile["columns"][col]
            if profile.get("outlier_analysis", {}).get("has_significant_outliers"):
                signals["data_quality_concerns"].append(f"suspicious_outliers: {col}")
    
    if len(signals["data_quality_concerns"]) > 5:
        signals["risk_level"] = "critical"
    
    return signals
```

### Integration Point in agent2_semantic_tagger():
```python
# After inferred_types calculation:
data_quality_signals = _assess_data_quality_signals(df, raw_profile)
schema_blueprint["__metadata__"] = {
    "data_quality_assessment": data_quality_signals,
    "preprocessing_recommendation": data_quality_signals["recommended_preprocessing_rigor"]
}

# Add confidence scoring to each column:
for col in schema_blueprint:
    if col != "__metadata__":
        meta = schema_blueprint[col]
        confidence = _calculate_semantic_confidence(
            col,
            raw_profile.get("columns", {}).get(col, {}),
            inferred_types.get(col, "unknown"),
            meta.get("semantic_tag", "unknown"),
            raw_profile.get("columns", {}).get(col, {}).get("format_hints", {})
        )
        meta["confidence"] = confidence
```

---

## 🧹 AGENT 3: Smarter Preprocessing Strategies

### Current State
✅ Comprehensive 10-step pipeline, good business metrics derivation
❌ One-size-fits-all strategies, no adaptive handling, rigid quality scoring

### Recommended Changes

#### 1. **Adaptive Imputation Based on Data Patterns**
```python
def _choose_adaptive_imputation_strategy(series: pd.Series, meta: dict, profile: dict) -> str:
    """Select imputation strategy based on data distribution and semantics."""
    missing_count = series.isna().sum()
    if missing_count == 0:
        return "none"
    
    missing_rate = missing_count / len(series)
    semantic_tag = meta.get("semantic_tag", "unknown")
    intended_type = meta.get("intended_type", "string")
    
    # For very sparse columns, flag only
    if missing_rate > 0.5:
        return "flag_only"
    
    # For numeric columns, check distribution
    if intended_type in ("float", "int"):
        non_null = pd.to_numeric(series.dropna(), errors="coerce")
        if len(non_null) > 0:
            # Check if data is right-skewed (use median)
            skewness = float(non_null.skew())
            if abs(skewness) > 1.0:  # significant skew
                return "median"
            else:
                return "mean"
    
    # For categorical, prefer mode
    if semantic_tag == "categorical_label":
        return "mode"
    
    # For currency (sensitive domain), use median
    if semantic_tag == "currency":
        return "median"
    
    # Fallback
    return meta.get("imputation_strategy", "median" if intended_type in ("float", "int") else "mode")
```

#### 2. **Context-Aware Outlier Handling**
```python
def _adaptive_outlier_clipping(df: pd.DataFrame, meta: dict, col: str) -> tuple:
    """Clip outliers with domain awareness."""
    if col not in df.columns:
        return df, 0, {}
    
    series = pd.to_numeric(df[col], errors="coerce")
    non_null = series.dropna()
    
    if len(non_null) < 10:
        return df, 0, {}
    
    semantic_tag = meta.get("semantic_tag", "unknown")
    
    # For currency, use domain-specific bounds
    if semantic_tag == "currency":
        # Currency rarely goes to infinity; use 99th percentile
        lower = non_null.quantile(0.01)
        upper = non_null.quantile(0.99)
    
    # For percentage, hard bounds
    elif semantic_tag == "percentage":
        # Percentages should be 0-100 (or -100 to 100 for changes)
        lower = -150
        upper = 150
        df[col] = series.clip(lower, upper)
        clipped = ((series < lower) | (series > upper)).sum()
        return df, int(clipped), {"lower": lower, "upper": upper}
    
    # For counts, can't be negative
    elif meta.get("is_count_field"):
        lower = 0
        upper = non_null.quantile(0.99)
        df[col] = series.clip(lower, upper)
        clipped = (series < lower).sum()
        return df, int(clipped), {"lower": lower, "upper": upper}
    
    # Default IQR method
    else:
        q1 = non_null.quantile(0.25)
        q3 = non_null.quantile(0.75)
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
    
    clipped_count = ((series < lower) | (series > upper)).sum()
    df[col] = series.clip(lower, upper)
    
    return df, int(clipped_count), {"lower": float(lower), "upper": float(upper), "method": "iqr"}
```

#### 3. **Enhanced Quality Score with Granular Breakdown**
```python
def _compute_enhanced_quality_score(
    df_raw: pd.DataFrame,
    df_clean: pd.DataFrame,
    validation_summary: dict,
    config: dict,
    preprocessing_log: list
) -> dict:
    """More nuanced quality scoring with component breakdown."""
    
    # Component 1: Completeness (before & after)
    raw_null_pct = (df_raw.isna().sum().sum() / (df_raw.shape[0] * df_raw.shape[1])) * 100
    clean_null_pct = (df_clean.isna().sum().sum() / (df_clean.shape[0] * df_clean.shape[1])) * 100
    
    completeness_score = max(0, min(100, 100 - clean_null_pct))
    completeness_improvement = raw_null_pct - clean_null_pct
    
    # Component 2: Consistency (validation pass rate)
    total_checks = max(validation_summary.get("checks", 1), 1)
    passed_checks = total_checks - validation_summary.get("failed_rows", 0)
    consistency_score = (passed_checks / total_checks) * 100
    
    # Component 3: Deduplication
    dup_rate = (df_raw.duplicated().sum() / max(len(df_raw), 1)) * 100
    dedup_score = max(0, min(100, 100 - dup_rate))
    
    # Component 4: Structure preservation (row survival rate)
    row_survival_rate = (len(df_clean) / max(len(df_raw), 1)) * 100
    if row_survival_rate < 50:
        structure_score = 30  # risky
    elif row_survival_rate < 80:
        structure_score = 70
    else:
        structure_score = 100
    
    # Weighted composite (adjustable)
    weights = config.get("quality_weights", {
        "completeness": 0.35,
        "consistency": 0.35,
        "dedup": 0.15,
        "structure": 0.15
    })
    
    overall_score = (
        weights.get("completeness", 0.35) * completeness_score +
        weights.get("consistency", 0.35) * consistency_score +
        weights.get("dedup", 0.15) * dedup_score +
        weights.get("structure", 0.15) * structure_score
    )
    
    return {
        "overall_quality_score": round(overall_score, 2),
        "component_scores": {
            "completeness": round(completeness_score, 2),
            "consistency": round(consistency_score, 2),
            "dedup": round(dedup_score, 2),
            "structure": round(structure_score, 2)
        },
        "metrics": {
            "raw_null_pct": round(raw_null_pct, 2),
            "clean_null_pct": round(clean_null_pct, 2),
            "completeness_improvement": round(completeness_improvement, 2),
            "duplicate_rate_pct": round(dup_rate, 2),
            "row_survival_rate": round(row_survival_rate, 2),
            "validation_pass_rate": round((passed_checks / total_checks) * 100, 2)
        }
    }
```

#### 4. **Intelligent Categorical Encoding Selection**
```python
def _select_encoding_method(profile: dict, meta: dict, df_sample: pd.Series) -> dict:
    """Choose encoding based on cardinality, distribution, and business context."""
    unique_count = int(profile.get("unique_count", 0))
    
    # If < 5 unique values: use ordinal if there's natural order, else one-hot
    if unique_count < 5:
        # Check if values suggest order (small, medium, large) or ranking
        sample_values = df_sample.dropna().unique()
        value_str = " ".join([str(v).lower() for v in sample_values[:5]])
        
        order_keywords = {"small", "medium", "large", "low", "medium", "high", "junior", "senior", "entry", "level"}
        if any(kw in value_str for kw in order_keywords):
            return {
                "method": "ordinal",
                "reason": f"apparent order detected in {unique_count} categories"
            }
        return {
            "method": "one_hot",
            "reason": f"low cardinality ({unique_count}) without apparent order"
        }
    
    # If 5-20: one-hot encoding works well
    elif unique_count <= 20:
        return {
            "method": "one_hot",
            "reason": f"moderate cardinality ({unique_count}) suitable for one-hot"
        }
    
    # If 20-100: target encoding or leave encoded
    elif unique_count <= 100:
        return {
            "method": "none",
            "reason": f"high cardinality ({unique_count}) - consider target encoding or leave as-is"
        }
    
    # If > 100: don't encode
    else:
        return {
            "method": "none",
            "reason": f"very high cardinality ({unique_count}) - encoding would create sparse features"
        }
```

#### 5. **Add Validation Confidence Reporting**
```python
def _calculate_validation_confidence(validation_summary: dict) -> dict:
    """Assess confidence in validation results."""
    total_checks = validation_summary.get("checks", 0)
    if total_checks == 0:
        return {"confidence": "unknown", "reason": "no validations run"}
    
    coverage_pct = (total_checks / 1000) * 100  # normalize to 1000 samples
    pass_rate = ((total_checks - validation_summary.get("failed_rows", 0)) / total_checks) * 100
    
    if pass_rate > 95:
        confidence = "high"
    elif pass_rate > 80:
        confidence = "medium"
    else:
        confidence = "low"
    
    return {
        "confidence_level": confidence,
        "validation_coverage_pct": round(min(100, coverage_pct), 2),
        "pass_rate_pct": round(pass_rate, 2),
        "recommendation": "data is reliable" if confidence in ["high", "medium"] else "review before use"
    }
```

### Integration Points in agent3_preprocessor():

**After imputation step:**
```python
# Replace rigid imputation with adaptive
for col, meta in schema_blueprint.items():
    if col not in df.columns:
        continue
    
    adaptive_strategy = _choose_adaptive_imputation_strategy(df[col], meta, raw_profile.get("columns", {}).get(col, {}))
    meta["adaptive_imputation_strategy"] = adaptive_strategy
    # Then use this strategy for imputation
```

**After outlier clipping:**
```python
# Use context-aware clipping
for col, meta in schema_blueprint.items():
    if col not in df.columns:
        continue
    
    df, clipped_count, bounds = _adaptive_outlier_clipping(df, meta, col)
    if clipped_count > 0:
        ledger.record_range_failure(col, (clipped_count/len(df))*100, clipped_count)
```

**Replace quality score computation:**
```python
data_quality = _compute_enhanced_quality_score(
    df_raw,
    df,
    validation_summary,
    preprocessing_config,
    preprocessing_log
)
```

---

## 📋 Summary of Changes by Priority

### HIGH PRIORITY (Biggest Impact)
1. **Agent 1**: Add distribution analysis and outlier pre-detection
2. **Agent 2**: Add confidence scoring and data quality signals
3. **Agent 3**: Implement adaptive imputation based on data patterns
4. **Agent 3**: Enhanced quality scoring with component breakdown

### MEDIUM PRIORITY (Good Impact)
5. **Agent 1**: Detect implicit missing values and column relationships
6. **Agent 2**: Contextual semantic inference
7. **Agent 3**: Context-aware outlier handling

### NICE TO HAVE
8. **Agent 2**: Domain-specific vocabulary support
9. **Agent 3**: Intelligent categorical encoding selection
10. **Agent 3**: Validation confidence reporting

---

## 🚀 Implementation Strategy

1. **Start with Agent 1**: Add distribution analysis and outlier detection (adds ~50 lines)
2. **Then Agent 2**: Add confidence scoring (adds ~80 lines)
3. **Then Agent 3**: Replace quality scoring function and add adaptive strategies (refactors existing code)
4. **Test incrementally**: Validate each change improves metrics

---

## ✅ Expected Improvements

| Metric | Before | After |
|--------|--------|-------|
| Outlier Detection Accuracy | Single method | Triple validation |
| Imputation Quality | Fixed strategy | Adaptive per-column |
| Quality Score Accuracy | Aggregate | Component breakdown |
| Semantic Confidence | N/A | 0-100 score per column |
| Data Quality Signals | None | Multiple indicators |
| False Positives in Validation | Moderate | Reduced with confidence |

