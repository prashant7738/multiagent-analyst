import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from pipeline import _write_run_diagnostics, should_continue_after_agent3


class TestShouldContinueAfterAgent3(unittest.TestCase):
    """Agent 3 appends non-fatal 'Agent3: ...' warnings (e.g. derived-metric
    divergence) to state["errors"] without touching cleaned_df - these must not
    abort the pipeline before Agent 4/5/6 run."""

    def test_continues_to_agent4_despite_non_fatal_agent3_warning(self):
        state = {
            "cleaned_df": pd.DataFrame({"a": [1, 2, 3]}),
            "errors": [
                "Agent3: DERIVED METRIC DIVERGENCE - [derived_profit] vs [Total Profit] "
                "(r=0.882, MAPE=239.05%) - review the derivation formula/source columns."
            ],
        }

        self.assertEqual(should_continue_after_agent3(state), "agent4")

    def test_ends_when_cleaned_df_is_none(self):
        state = {"cleaned_df": None, "errors": ["Agent3: No DataFrame in state. Agent 1 or 2 failed."]}

        self.assertEqual(should_continue_after_agent3(state), "end")


class TestPipelineDiagnostics(unittest.TestCase):
    def test_diagnostics_contains_agent_metadata_and_replaces_previous_run(self):
        state = {
            "raw_profile": {"shape": {"rows": 3, "cols": 2}, "columns": {"id": {"dtype": "int64"}}},
            "schema_blueprint": {"id": {"semantic_tag": "identifier", "is_identifier": True}},
            "preprocessing_config": {"profile": "balanced"},
            "preprocessing_profile": "balanced",
            "dataset_domain": "sales",
            "scaling_params": {"amount": {"min": 1, "max": 9}},
            "preprocessing_log": [{"step": "deduplicate"}],
            "data_quality": {"overall_quality_score": 98},
            "column_ledger": {"id": {"status": "ok"}},
            "stats": {"descriptive": {"amount": {"mean": 5}}},
            "chart_paths": ["outputs/charts/chart.png"],
            "errors": [],
            "reliability": {"overall_confidence": 0.95},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "agent_run_diagnostics.json"
            output_path.write_text('{"stale": true}', encoding="utf-8")

            written_path = _write_run_diagnostics(state, output_path)

            self.assertEqual(written_path, str(output_path))
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertNotIn("stale", payload)
            self.assertEqual(payload["agent_1"]["columns"]["id"]["dtype"], "int64")
            self.assertEqual(payload["agent_2"]["columns"]["id"]["semantic_tag"], "identifier")
            self.assertEqual(payload["agent_3"]["data_quality"]["overall_quality_score"], 98)
            self.assertEqual(payload["agent_4"]["stats"]["descriptive"]["amount"]["mean"], 5)
            self.assertEqual(payload["pipeline"]["reliability"]["overall_confidence"], 0.95)


if __name__ == "__main__":
    unittest.main()