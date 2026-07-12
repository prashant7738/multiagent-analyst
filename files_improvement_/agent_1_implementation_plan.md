# Agent 1 Implementation Plan

## Scope
Enhance structural profiling in [backend/agents/agent_1.py](../backend/agents/agent_1.py) so the raw profile includes distribution analysis, implicit missing values, outlier pre-detection, and column relationships.

## Exact Change Points
- New helper functions start at line 129 in [backend/agents/agent_1.py](../backend/agents/agent_1.py).
- The integration block starts at line 375 in [backend/agents/agent_1.py](../backend/agents/agent_1.py).

## Added Functions
- `_analyze_column_distribution(series)` at line 129.
- `_detect_implicit_missingness(df)` at line 180.
- `_detect_potential_outliers(series)` at line 222.
- `_detect_column_relationships(df, column_profiles)` at line 272.

## What Changed
The profiler now builds these new `raw_profile` fields:
- `distribution_analysis`
- `implicit_missing_values`
- `column_relationships`

Numeric columns also receive `outlier_analysis` inside `raw_profile["columns"][col]`.

## Exact Snippet Added to the Integration Path
```python
distribution_analysis = {}
implicit_missing = _detect_implicit_missingness(df)
relationships = _detect_column_relationships(df, column_profiles)

for col in df.columns:
    distribution_analysis[col] = _analyze_column_distribution(df[col])
    if pd.api.types.is_numeric_dtype(df[col]):
        column_profiles[col]["outlier_analysis"] = _detect_potential_outliers(df[col])
```

## Validation
Run from `backend/`:
```bash
python -m unittest discover -s tests -p "test_preprocessing_improvements.py" -v
```

## Rollback
If anything breaks, remove the four helper functions and delete the three new `raw_profile` keys from the integration block. The rest of Agent 1 remains unchanged.
