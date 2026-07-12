# Testing and Validation Plan

## Primary Validation Command
Run from `backend/`:
```bash
python -m unittest discover -s tests -p "test_preprocessing_improvements.py" -v
```

## What This Verifies
- Agent 1 detects skewness, implicit missingness, outliers, and relationships.
- Agent 2 produces semantic confidence scores and quality metadata.
- Agent 3 performs adaptive clipping and emits component scores.
- The end-to-end pipeline still returns a cleaned DataFrame.

## Expected Signals
- `raw_profile` includes `distribution_analysis`, `implicit_missing_values`, and `column_relationships`.
- `schema_blueprint` includes per-column `confidence` and a `__metadata__` block.
- `data_quality` includes `component_scores`, `risk_assessment`, and `preprocessing_recommendation`.

## Additional Manual Check
If you want a quick smoke test, run the same unittest file and watch for the final `OK` summary.

## Common Failure Modes
- Missing scientific stack in the interpreter.
- Agent 2 Groq client unavailable, causing fallback mode.
- Extremely tiny numeric columns may skip distribution or outlier analysis by design.
