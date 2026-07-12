# Deployment Guide

## Prerequisites
- Python 3.14 in the backend environment.
- `pandas`, `numpy`, `scipy`, and `pytest` or `unittest` available in the runtime.

## Step-by-Step
1. Back up the current files:
   - `backend/agents/agent_1.py`
   - `backend/agents/agent_2.py`
   - `backend/agents/agent_3.py`
2. Keep the current workspace changes in place. The improved logic is already in the three agent files.
3. Run the validation suite from `backend/`:
   ```bash
   python -m unittest discover -s tests -p "test_preprocessing_improvements.py" -v
   ```
4. Inspect the output for the new structural, semantic, and preprocessing metadata.
5. Confirm `outputs/cleaned_data.csv` is still produced by Agent 3.

## Rollback Procedure
1. Restore the backup copies of the three agent files.
2. Remove the test file `backend/tests/test_preprocessing_improvements.py` if you no longer want the new coverage.
3. Rerun the baseline pipeline test you use in your environment.

## Notes
- Agent 2 is written to fall back to heuristics when the Groq client is unavailable.
- The code paths remain backward-compatible through the `_compute_quality_score()` wrapper in Agent 3.
