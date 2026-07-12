# Ready-to-Use Code Snippets for Agents 1, 2, and 3

---

## 🔧 AGENT 1: Enhanced Structural Profiling

### 📌 Add at Top of agent_1.py
```python
# Add these imports
from scipy.stats import skew, kurtosis, shapiro
import warnings
warnings.filterwarnings('ignore', category=UserWarning)
```

### 📌 New Function: Distribution Analysis
```python
def _analyze_column_distribution(series: pd.Series) -> dict:
    """Analyze distribution shape, skewness, and normality."""
    non_null = series.dropna()
    
    if len(non_null) < 10:
        return {
            "skewness": 0.0,
            "kurtosis": 0.0,
            "is_normal": False,
            "distribution_type": "insufficient_data"
        }
    
    # Try numeric conversion
    try:
        numeric = pd.to_numeric(non_null, errors="coerce").dropna()
    except:
        numeric = pd.Series([])
    
    if len(numeric) < 3:
        return {
            "skewness": 0.0,
            "kurtosis": 0.0,
            "is_normal": False,
            "distribution_type": "non_numeric"
        }
    
    skewness = float(skew(numeric))
    kurt = float(kurtosis(numeric))
    
    # Shapiro-Wilk test for normality (max 5000 samples)
    is_normal = False
    if len(numeric) <= 5000:
        try:
            _, p_value = shapiro(numeric.iloc[:5000])
            is_normal = p_value > 0.05
        except:
            is_normal = abs(skewness) < 0.5 and abs(kurt) < 1
    else:
        is_normal = abs(skewness) < 0.5 and abs(kurt) < 1
    
    return {
        "skewness": round(skewness, 3),
        "kurtosis": round(kurt, 3),
        "is_normal": is_normal,
        "distribution_type": "normal" if is_normal else ("right_skewed" if skewness > 0.5 else "left_skewed" if skewness < -0.5 else "symmetric")
    }
```

### 📌 New Function: Implicit Missing Value Detection
```python
def _detect_implicit_missingness(df: pd.DataFrame) -> dict:
    """Identify sentinel values and implicit nulls."""
    implicit_patterns = {}
    
    for col in df.columns:
        series = df[col]
        implicit_flags = []
        
        # Numeric sentinels
        if pd.api.types.is_numeric_dtype(series):
            numeric = pd.to_numeric(series, errors="coerce")
            sentinels = [-1, -999, 9999, 0, 99999, 999999]
            for sentinel in sentinels:
                count = (numeric == sentinel).sum()
                if count > 0 and (count / len(numeric)) > 0.005:  # >0.5% of data
                    implicit_flags.append({
                        "sentinel": sentinel,
                        "count": int(count),
                        "pct": round((count / len(numeric)) * 100, 2),
                        "recommendation": "verify if truly missing or valid data"
                    })
        
        # String patterns
        if pd.api.types.is_object_dtype(series):
            str_series = series.astype("string").str.strip()
            patterns = ["0000-00-00", "1900-01-01", "n/a", "none", "null", "na", ""]
            for pattern in patterns:
                count = (str_series == pattern).sum()
                if count > 0 and (count / len(series)) > 0.005:
                    implicit_flags.append({
                        "pattern": pattern,
                        "count": int(count),
                        "pct": round((count / len(series)) * 100, 2),
                        "recommendation": "treat as missing value"
                    })
        
        if implicit_flags:
            implicit_patterns[col] = implicit_flags
    
    return implicit_patterns
```

### 📌 New Function: Outlier Detection
```python
def _detect_potential_outliers(series: pd.Series) -> dict:
    """Detect outliers using IQR and Z-score methods."""
    non_null = series.dropna()
    
    if len(non_null) < 10:
        return {"outlier_count": 0, "method": "insufficient_data"}
    
    try:
        numeric = pd.to_numeric(non_null, errors="coerce").dropna()
    except:
        return {"outlier_count": 0, "method": "non_numeric"}
    
    if len(numeric) < 4:
        return {"outlier_count": 0, "method": "insufficient_data"}
    
    # IQR method
    q1 = numeric.quantile(0.25)
    q3 = numeric.quantile(0.75)
    iqr = q3 - q1
    
    if iqr == 0:
        return {
            "outlier_count": 0,
            "method": "iqr",
            "note": "zero IQR - likely constant column"
        }
    
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    iqr_mask = (numeric < lower) | (numeric > upper)
    iqr_count = iqr_mask.sum()
    
    # Z-score method
    from scipy import stats
    try:
        z_scores = np.abs(stats.zscore(numeric, nan_policy='omit'))
        z_mask = z_scores > 3
        z_count = z_mask.sum()
    except:
        z_count = 0
    
    return {
        "iqr_outlier_count": int(iqr_count),
        "iqr_outlier_pct": round((iqr_count / len(numeric)) * 100, 2),
        "iqr_bounds": {"lower": round(float(lower), 4), "upper": round(float(upper), 4)},
        "z_score_outlier_count": int(z_count),
        "z_score_outlier_pct": round((z_count / len(numeric)) * 100, 2),
        "has_significant_outliers": iqr_count > max(5, len(numeric) * 0.05),  # >5% or min 5 values
        "method": "iqr_and_zscore"
    }
```

### 📌 New Function: Column Relationships
```python
def _detect_column_relationships(df: pd.DataFrame, raw_profile: dict) -> dict:
    """Find potential keys, duplicates, and correlations."""
    relationships = {
        "potential_keys": [],
        "high_cardinality_text": [],
        "numeric_correlations": [],
        "duplicate_sets": []
    }
    
    # Find potential keys
    for col in df.columns:
        profile = raw_profile.get("columns", {}).get(col, {})
        unique_ratio = profile.get("cardinality_ratio", 0)
        missing_count = profile.get("missing_count", 0)
        
        if unique_ratio > 0.98 and missing_count == 0:
            relationships["potential_keys"].append(col)
    
    # Find high-cardinality text (likely IDs, codes)
    for col in df.columns:
        if df[col].dtype == "object":
            unique_count = df[col].nunique()
            if unique_count > len(df) * 0.9:
                relationships["high_cardinality_text"].append({
                    "column": col,
                    "unique_count": unique_count,
                    "uniqueness_pct": round((unique_count / len(df)) * 100, 1),
                    "likely_identifier": True
                })
    
    # Find numeric correlations
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if len(numeric_cols) >= 2:
        corr_matrix = df[numeric_cols].corr()
        for i, col1 in enumerate(numeric_cols):
            for col2 in numeric_cols[i+1:]:
                corr_val = abs(corr_matrix.loc[col1, col2])
                if corr_val > 0.95 and not np.isnan(corr_val):
                    relationships["numeric_correlations"].append({
                        "col1": col1,
                        "col2": col2,
                        "correlation": round(float(corr_val), 3),
                        "concern": "potential multicollinearity or redundancy"
                    })
    
    return relationships
```

### 📌 Integration: Modify agent1_structural_profiler()

**Find this section:**
```python
    duplicate_rows = int(df.duplicated().sum())

    raw_profile = {
        "shape": {"rows": df.shape[0], "cols": df.shape[1]},
```

**Replace with:**
```python
    duplicate_rows = int(df.duplicated().sum())
    
    # Add new analyses
    distribution_analysis = {}
    implicit_missing = _detect_implicit_missingness(df)
    relationships = _detect_column_relationships(df, column_profiles)
    
    for col in df.columns:
        distribution_analysis[col] = _analyze_column_distribution(df[col])
        
        # Add outlier detection for numeric columns
        if pd.api.types.is_numeric_dtype(df[col]):
            column_profiles[col]["outlier_analysis"] = _detect_potential_outliers(df[col])

    raw_profile = {
        "shape": {"rows": df.shape[0], "cols": df.shape[1]},
        "distribution_analysis": distribution_analysis,
        "implicit_missing_values": implicit_missing,
        "column_relationships": relationships,
```

---

## 🏷️ AGENT 2: Advanced Semantic Inference

### 📌 Add at Top of agent_2.py
```python
# Add to imports section
from scipy import stats
```

### 📌 New Function: Confidence Scoring
```python
def _calculate_semantic_confidence(
    column_name: str,
    profile: dict,
    inferred_type: str,
    semantic_tag: str,
    format_hints: dict
) -> dict:
    """Calculate confidence score (0-100) for semantic tag inference."""
    score = 50  # baseline
    evidence = []
    
    # Name-based signals (±20)
    name_tokens = _name_tokens(column_name)
    tag_keywords = {
        "identifier": {"id", "identifier", "uuid", "key", "code", "pk"},
        "currency": {"sales", "revenue", "cost", "price", "amount", "budget", "tax", "discount", "total", "profit"},
        "datetime": {"date", "time", "timestamp", "created", "updated", "modified", "datetime"},
        "percentage": {"percent", "pct", "rate", "margin", "ratio", "share"},
        "count": {"count", "qty", "quantity", "units", "num", "number", "volume"}
    }
    
    if semantic_tag in tag_keywords:
        if name_tokens & tag_keywords[semantic_tag]:
            score += 20
            evidence.append(f"name_match: '{semantic_tag}' keyword in column name")
    
    # Type alignment (±15)
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
        evidence.append(f"type_alignment: {inferred_type} ✓ {semantic_tag}")
    elif semantic_tag in type_alignment and inferred_type not in type_alignment[semantic_tag]:
        score -= 10
        evidence.append(f"type_mismatch: {inferred_type} ✗ {semantic_tag}")
    
    # Format hints (±15)
    if semantic_tag == "currency" and format_hints.get("currency_like"):
        score += 15
        evidence.append("format_hint: currency symbols detected")
    
    if semantic_tag == "datetime" and format_hints.get("date_like"):
        score += 15
        evidence.append("format_hint: date patterns detected")
    
    if semantic_tag == "identifier" and format_hints.get("identifier_like"):
        score += 10
        evidence.append("format_hint: identifier patterns detected")
    
    # Cardinality signals (±10)
    unique_count = int(profile.get("unique_count", 0))
    missing_rate = float(profile.get("missing_rate_pct", 0))
    
    if semantic_tag == "identifier":
        if missing_rate == 0:
            score += 10
            evidence.append("quality: zero nulls in identifier")
        if unique_count > len(profile.get("sample_values", [])) * 0.95:
            score += 5
            evidence.append("cardinality: high uniqueness ✓ identifier")
    
    if semantic_tag == "categorical_label":
        if 1 < unique_count < 20:
            score += 10
            evidence.append(f"cardinality: {unique_count} values ✓ categorical")
        elif unique_count >= 100:
            score -= 15
            evidence.append(f"cardinality: {unique_count} values ✗ categorical (too high)")
    
    # Penalize high missing rates (−20 if >50%, −10 if >30%)
    if missing_rate > 50:
        score -= 20
        evidence.append(f"data_quality: very high missingness ({missing_rate:.1f}%)")
    elif missing_rate > 30:
        score -= 10
        evidence.append(f"data_quality: high missingness ({missing_rate:.1f}%)")
    
    final_score = min(100, max(0, score))
    
    return {
        "confidence_score": final_score,
        "confidence_level": "high" if final_score >= 70 else "medium" if final_score >= 50 else "low",
        "evidence": evidence
    }
```

### 📌 New Function: Data Quality Assessment
```python
def _assess_data_quality_signals(df: pd.DataFrame, raw_profile: dict) -> dict:
    """Extract data quality signals that guide preprocessing."""
    signals = {
        "quality_issues": [],
        "preprocessing_recommendation": "balanced",
        "risk_assessment": "low"
    }
    
    total_cells = df.shape[0] * df.shape[1]
    total_missing = raw_profile.get("total_missing", 0)
    missing_pct = (total_missing / max(total_cells, 1)) * 100
    
    duplicate_rows = raw_profile.get("duplicate_rows", 0)
    duplicate_pct = (duplicate_rows / max(len(df), 1)) * 100
    
    implicit_missing = raw_profile.get("implicit_missing_values", {})
    outlier_cols_count = sum(
        1 for col in raw_profile.get("columns", {}).values()
        if col.get("outlier_analysis", {}).get("has_significant_outliers")
    )
    
    # Assess missingness
    if missing_pct > 40:
        signals["quality_issues"].append(f"critical_missingness: {missing_pct:.1f}%")
        signals["preprocessing_recommendation"] = "strict"
        signals["risk_assessment"] = "critical"
    elif missing_pct > 20:
        signals["quality_issues"].append(f"high_missingness: {missing_pct:.1f}%")
        signals["preprocessing_recommendation"] = "strict"
        signals["risk_assessment"] = "high"
    elif missing_pct > 10:
        signals["quality_issues"].append(f"moderate_missingness: {missing_pct:.1f}%")
    
    # Assess duplication
    if duplicate_pct > 20:
        signals["quality_issues"].append(f"critical_duplication: {duplicate_pct:.1f}%")
        signals["risk_assessment"] = "critical"
    elif duplicate_pct > 10:
        signals["quality_issues"].append(f"high_duplication: {duplicate_pct:.1f}%")
        if signals["risk_assessment"] != "critical":
            signals["risk_assessment"] = "high"
    
    # Implicit values
    if len(implicit_missing) > 3:
        signals["quality_issues"].append(f"multiple_implicit_nulls: {len(implicit_missing)} columns affected")
    
    # Outliers
    if outlier_cols_count > len(df.columns) * 0.3:  # >30% of columns
        signals["quality_issues"].append(f"widespread_outliers: {outlier_cols_count}/{len(df.columns)} columns")
        if signals["risk_assessment"] != "critical":
            signals["risk_assessment"] = "high"
    
    # Overall assessment
    issue_count = len(signals["quality_issues"])
    if issue_count >= 3:
        signals["risk_assessment"] = "critical"
        signals["preprocessing_recommendation"] = "strict"
    
    signals["issue_count"] = issue_count
    signals["missing_pct"] = round(missing_pct, 2)
    signals["duplicate_pct"] = round(duplicate_pct, 2)
    
    return signals
```

### 📌 Integration: Modify agent2_semantic_tagger()

**Find this section in the try block:**
```python
        schema_blueprint, excluded = _apply_missingness_policy(df, raw_profile, schema_blueprint, inferred_types)

        print(f"[Agent 2] Blueprint built for {len(schema_blueprint)} columns")
```

**Add after it:**
```python
        # Add confidence scoring and quality assessment
        data_quality_signals = _assess_data_quality_signals(df, raw_profile)
        
        for col in schema_blueprint:
            meta = schema_blueprint[col]
            confidence = _calculate_semantic_confidence(
                col,
                raw_profile.get("columns", {}).get(col, {}),
                inferred_types.get(col, "unknown"),
                meta.get("semantic_tag", "unknown"),
                raw_profile.get("columns", {}).get(col, {}).get("format_hints", {})
            )
            meta["confidence"] = confidence
            
            # Include warnings if confidence is low
            if confidence["confidence_level"] == "low":
                meta["notes"] = meta.get("notes", "") + f" [LOW CONFIDENCE: {', '.join(confidence['evidence'][:2])}]"
        
        # Store quality signals in metadata
        schema_blueprint["__metadata__"] = {
            "data_quality_assessment": data_quality_signals,
            "preprocessing_rigor": data_quality_signals["preprocessing_recommendation"],
            "risk_level": data_quality_signals["risk_assessment"]
        }

        print(f"[Agent 2] Data quality: {data_quality_signals['risk_assessment'].upper()}")
        if data_quality_signals["quality_issues"]:
            for issue in data_quality_signals["quality_issues"][:3]:
                print(f"  ⚠ {issue}")
```

---

## 🧹 AGENT 3: Smarter Preprocessing

### 📌 New Function: Adaptive Imputation
```python
def _choose_adaptive_imputation_strategy(
    series: pd.Series,
    meta: dict,
    profile: dict
) -> str:
    """Select imputation strategy based on data patterns."""
    missing_count = series.isna().sum()
    if missing_count == 0:
        return "none"
    
    missing_rate = missing_count / len(series)
    semantic_tag = meta.get("semantic_tag", "unknown")
    intended_type = meta.get("intended_type", "string")
    
    # Very sparse columns - flag only
    if missing_rate > 0.5:
        return "flag_only"
    
    # Numeric columns - check distribution skewness
    if intended_type in ("float", "int"):
        non_null = pd.to_numeric(series.dropna(), errors="coerce")
        if len(non_null) > 0:
            try:
                skewness = float(non_null.skew())
                # Right-skewed data (income, prices) -> use median
                if abs(skewness) > 1.0:
                    return "median"
                else:
                    return "mean"
            except:
                return "median"
    
    # Categorical - use mode if low cardinality
    if semantic_tag == "categorical_label":
        unique_count = profile.get("unique_count", 0)
        if unique_count > 0 and unique_count < 20:
            return "mode"
        else:
            return "flag_only"
    
    # Currency - use median (robust to outliers)
    if semantic_tag == "currency":
        return "median"
    
    # Datetime - don't impute (preserve time semantics)
    if semantic_tag == "datetime" or intended_type == "datetime":
        return "flag_only"
    
    # Fallback
    return "median" if intended_type in ("float", "int") else "mode"
```

### 📌 New Function: Context-Aware Outlier Clipping
```python
def _adaptive_outlier_clipping(
    df: pd.DataFrame,
    meta: dict,
    col: str,
    config: dict
) -> tuple:
    """Clip outliers using domain-aware bounds."""
    if col not in df.columns:
        return df, 0, {}
    
    series = pd.to_numeric(df[col], errors="coerce")
    non_null = series.dropna()
    
    if len(non_null) < 10:
        return df, 0, {}
    
    semantic_tag = meta.get("semantic_tag", "unknown")
    
    # Currency: use 1st-99th percentile (domain-specific)
    if semantic_tag == "currency":
        lower = non_null.quantile(0.01)
        upper = non_null.quantile(0.99)
        clipped = ((series < lower) | (series > upper)).sum()
        df[col] = series.clip(lower, upper)
        return df, int(clipped), {
            "method": "percentile_99",
            "lower": round(float(lower), 2),
            "upper": round(float(upper), 2)
        }
    
    # Percentage: hard bounds (-150 to 150)
    if semantic_tag == "percentage":
        lower, upper = -150, 150
        clipped = ((series < lower) | (series > upper)).sum()
        df[col] = series.clip(lower, upper)
        return df, int(clipped), {
            "method": "domain_bounds",
            "lower": lower,
            "upper": upper
        }
    
    # Count: can't be negative
    if meta.get("is_identifier") is False and _is_count_field(col, meta):
        lower = 0
        upper = non_null.quantile(0.99)
        clipped = (series < lower).sum()
        df[col] = series.clip(lower, upper)
        return df, int(clipped), {
            "method": "count_bounds",
            "lower": lower,
            "upper": round(float(upper), 2)
        }
    
    # Default IQR
    q1 = non_null.quantile(0.25)
    q3 = non_null.quantile(0.75)
    iqr = q3 - q1
    
    if iqr == 0:
        return df, 0, {"method": "iqr", "note": "zero_iqr"}
    
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    clipped = ((series < lower) | (series > upper)).sum()
    df[col] = series.clip(lower, upper)
    
    return df, int(clipped), {
        "method": "iqr",
        "lower": round(float(lower), 4),
        "upper": round(float(upper), 4),
        "iqr": round(float(iqr), 4)
    }
```

### 📌 New Function: Enhanced Quality Score
```python
def _compute_enhanced_quality_score(
    df_raw: pd.DataFrame,
    df_clean: pd.DataFrame,
    validation_summary: dict,
    config: dict
) -> dict:
    """Compute quality score with detailed component breakdown."""
    
    # Component 1: Completeness
    raw_null_pct = (df_raw.isna().sum().sum() / (df_raw.shape[0] * df_raw.shape[1])) * 100
    clean_null_pct = (df_clean.isna().sum().sum() / (df_clean.shape[0] * df_clean.shape[1])) * 100
    completeness_score = max(0, min(100, 100 - clean_null_pct))
    completeness_improvement = raw_null_pct - clean_null_pct
    
    # Component 2: Consistency (validation)
    total_checks = max(validation_summary.get("checks", 1), 1)
    passed_checks = total_checks - validation_summary.get("failed_rows", 0)
    consistency_score = (passed_checks / total_checks) * 100
    
    # Component 3: Deduplication
    dup_rate = (df_raw.duplicated().sum() / max(len(df_raw), 1)) * 100
    dedup_score = max(0, min(100, 100 - dup_rate))
    
    # Component 4: Structure preservation
    row_survival_rate = (len(df_clean) / max(len(df_raw), 1)) * 100
    if row_survival_rate < 50:
        structure_score = 30  # risky - too many rows dropped
    elif row_survival_rate < 80:
        structure_score = 70  # moderate - acceptable
    else:
        structure_score = 100  # good - most rows preserved
    
    # Weighted composite
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
            "deduplication": round(dedup_score, 2),
            "structure_preservation": round(structure_score, 2)
        },
        "metrics": {
            "raw_null_pct": round(raw_null_pct, 2),
            "clean_null_pct": round(clean_null_pct, 2),
            "completeness_improvement": round(completeness_improvement, 2),
            "duplicate_rate_pct": round(dup_rate, 2),
            "row_survival_rate": round(row_survival_rate, 2),
            "validation_pass_rate": round((passed_checks / total_checks) * 100, 2),
            "rows_before": int(df_raw.shape[0]),
            "rows_after": int(df_clean.shape[0]),
            "cols_before": int(df_raw.shape[1]),
            "cols_after": int(df_clean.shape[1])
        },
        "quality_assessment": "excellent" if overall_score >= 85 else "good" if overall_score >= 70 else "fair" if overall_score >= 50 else "poor"
    }
```

### 📌 Integration: Replace _clip_outliers() call

**Find in agent3_preprocessor():**
```python
    before_step = df.copy()
    df, notes, critical_errors = _clip_outliers(df, schema_blueprint, ledger)
    preprocessing_log.extend(notes)
```

**Replace with:**
```python
    before_step = df.copy()
    outlier_notes = []
    critical_errors = []
    
    for col, meta in schema_blueprint.items():
        if col not in df.columns:
            continue
        if not meta.get("scaling_allowed", False) or meta.get("is_identifier", False):
            continue
        if meta.get("intended_type") not in ("float", "int"):
            continue
        
        df, clipped_count, bounds = _adaptive_outlier_clipping(df, meta, col, preprocessing_config)
        if clipped_count > 0:
            method = bounds.get("method", "unknown")
            outlier_notes.append(f"{col}: {clipped_count} values clipped ({method})")
            if ledger:
                ledger.record_range_failure(col, (clipped_count / len(df)) * 100, clipped_count)
    
    preprocessing_log.extend(outlier_notes)
    preprocessing_log.extend(_log_null_diff(before_step, df, "Step 6 - Adaptive Clipping"))
```

### 📌 Integration: Replace quality score computation

**Find:**
```python
    data_quality = _compute_quality_score(df_raw, df, validation_summary, preprocessing_config)
```

**Replace with:**
```python
    data_quality = _compute_enhanced_quality_score(df_raw, df, validation_summary, preprocessing_config)
```

---

## ✅ Testing the Improvements

After implementing, test with:

```python
# Test Agent 1 enhancements
from agents.agent_1 import agent1_structural_profiler

state = {"csv_path": "sample_sales.csv", "errors": []}
state = agent1_structural_profiler(state)

# Check new fields
print("Distribution Analysis:", state["raw_profile"].get("distribution_analysis"))
print("Implicit Missing:", state["raw_profile"].get("implicit_missing_values"))
print("Column Relationships:", state["raw_profile"].get("column_relationships"))

# Test Agent 2 enhancements
from agents.agent_2 import agent2_semantic_tagger
state = agent2_semantic_tagger(state)

# Check confidence scores
for col, meta in state["schema_blueprint"].items():
    if col != "__metadata__":
        print(f"{col}: confidence={meta.get('confidence', {}).get('confidence_score')}")

# Check data quality assessment
metadata = state["schema_blueprint"].get("__metadata__", {})
print("Data Quality Assessment:", metadata.get("data_quality_assessment"))
```

---

## 🚀 Implementation Order

1. **Day 1**: Agent 1 enhancements (distribution + outliers + relationships)
2. **Day 2**: Agent 2 enhancements (confidence scoring + quality signals)
3. **Day 3**: Agent 3 enhancements (adaptive imputation + smart clipping + quality score)
4. **Day 4**: Testing and validation

Each step is backward compatible—existing code continues to work.
