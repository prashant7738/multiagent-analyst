import json
import tempfile
import unittest
from pathlib import Path

from pipeline import _write_run_diagnostics


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