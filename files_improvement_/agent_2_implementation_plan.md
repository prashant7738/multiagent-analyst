# Agent 2 Implementation Plan

## Scope
Extend semantic tagging in [backend/agents/agent_2.py](../backend/agents/agent_2.py) with confidence scoring and a data-quality metadata block for Agent 3.

## Exact Change Points
- Confidence helper starts at line 50 in [backend/agents/agent_2.py](../backend/agents/agent_2.py).
- Data-quality helper starts at line 151 in [backend/agents/agent_2.py](../backend/agents/agent_2.py).
- Confidence is attached in `_apply_missingness_policy()` around line 683.
- Metadata injection happens in `agent2_semantic_tagger()` around lines 743, 760, and 774.

## Added Functions
- `_confidence_level_from_score(score)`
- `_calculate_semantic_confidence(...)`
- `_assess_data_quality_signals(df, raw_profile)`

## What Changed
Each column now gets a `confidence` object with:
- `confidence_score`
- `confidence_level`
- `evidence`
- `signal_breakdown`

The schema blueprint also gets a `__metadata__` entry containing:
- `data_quality_assessment`
- `preprocessing_recommendation`
- `risk_assessment`

## Exact Integration Snippet
```python
meta["confidence"] = _calculate_semantic_confidence(
    col,
    profile,
    str(inferred_types.get(col, meta.get("intended_type", "unknown"))),
    str(meta.get("semantic_tag", "unknown")),
    profile.get("format_hints", {}) if isinstance(profile.get("format_hints"), dict) else {},
)
```

## Validation
Run from `backend/`:
```bash
python -m unittest discover -s tests -p "test_preprocessing_improvements.py" -v
```

## Rollback
Remove the confidence assignment in `_apply_missingness_policy()` and remove the `__metadata__` block from the three schema-building branches in `agent2_semantic_tagger()`.
