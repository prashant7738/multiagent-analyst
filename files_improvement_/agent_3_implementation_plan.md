# Agent 3 Implementation Plan

## Scope
Make preprocessing in [backend/agents/agent_3.py](../backend/agents/agent_3.py) distribution-aware, risk-aware, and more transparent about quality scoring.

## Exact Change Points
- `_adaptive_outlier_clipping(...)` starts at line 619.
- `_compute_enhanced_quality_score(...)` starts at line 979.
- Agent 3 reads Agent 2 metadata at line 1087.
- Adaptive clipping is called at line 1201.
- Enhanced quality scoring is called at line 1247.

## Added / Updated Functions
- `_adaptive_outlier_clipping(series, meta, config, profile=None, data_quality_context=None)`
- `_clip_outliers(...)` now delegates to the adaptive helper.
- `_compute_enhanced_quality_score(...)`
- `_compute_quality_score(...)` remains as a backward-compatible wrapper.

## What Changed
Agent 3 now uses Agent 2’s `__metadata__["data_quality_assessment"]` to decide when to use percentile-based clipping instead of fixed IQR bounds.

The quality output now includes:
- `component_scores`
- `risk_assessment`
- `preprocessing_recommendation`

## Exact Integration Snippet
```python
data_quality_context = {}
if isinstance(schema_blueprint.get("__metadata__"), dict):
    data_quality_context = schema_blueprint["__metadata__"].get("data_quality_assessment", {}) or {}
```

## Validation
Run from `backend/`:
```bash
python -m unittest discover -s tests -p "test_preprocessing_improvements.py" -v
```

## Rollback
Revert `_clip_outliers()` to the prior IQR-only logic and point `agent3_preprocessor()` back to `_compute_quality_score()` if you need to drop the new risk-aware behavior.
