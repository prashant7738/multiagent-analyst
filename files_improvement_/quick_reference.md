# Quick Reference - Preprocessing Improvements

## What Changed
- [Agent 1](../backend/agents/agent_1.py): adds distribution analysis, implicit missing detection, outlier pre-detection, and column relationships.
- [Agent 2](../backend/agents/agent_2.py): adds semantic confidence scoring and a `__metadata__` data-quality block.
- [Agent 3](../backend/agents/agent_3.py): adds adaptive outlier clipping and component-based quality scoring.

## New Fields to Expect
- `raw_profile["distribution_analysis"]`
- `raw_profile["implicit_missing_values"]`
- `raw_profile["column_relationships"]`
- `schema_blueprint[col]["confidence"]`
- `schema_blueprint["__metadata__"]`
- `data_quality["component_scores"]`
- `data_quality["risk_assessment"]`
- `data_quality["preprocessing_recommendation"]`

## How to Verify
Run from `backend/`:
```bash
python -m unittest discover -s tests -p "test_preprocessing_improvements.py" -v
```

## Practical Use
- Use Agent 1 outputs to detect skewed columns, sentinel-based missingness, and strong correlations early.
- Use Agent 2 confidence scores to decide whether a semantic tag is trustworthy enough for downstream preprocessing.
- Use Agent 3 component scores to explain whether quality loss came from missingness, validation failures, or duplication.

## Rollback at a Glance
- Restore the previous versions of `backend/agents/agent_1.py`, `backend/agents/agent_2.py`, and `backend/agents/agent_3.py`.
- Remove `backend/tests/test_preprocessing_improvements.py` if you want to drop the new coverage.

## Short FAQ
- Q: Is the pipeline still backward compatible?
  - A: Yes. Agent 3 keeps `_compute_quality_score()` as a wrapper around the enhanced scorer.
- Q: What if Groq is unavailable?
  - A: Agent 2 falls back to heuristic tagging and still emits confidence and metadata.
- Q: What is the fastest validation step?
  - A: Run the unittest command above.
