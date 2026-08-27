"""Agent 2 schema-blueprint JSON parsing + Groq-bad-JSON / Gemini-down failover."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from agents import agent_2


class TestLenientBlueprintParse(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(agent_2._parse_schema_blueprint_response('{"a": 1}'), {"a": 1})

    def test_trailing_comma_in_object_is_repaired(self):
        raw = '{"a": {"x": 1,}, "b": 2,}'
        self.assertEqual(agent_2._parse_schema_blueprint_response(raw), {"a": {"x": 1}, "b": 2})

    def test_trailing_comma_inside_fenced_block(self):
        raw = '```json\n{"a": [1, 2,],}\n```'
        self.assertEqual(agent_2._parse_schema_blueprint_response(raw), {"a": [1, 2]})

    def test_prose_wrapped_json_with_trailing_comma(self):
        raw = 'Here is the blueprint:\n{"col": {"intended_type": "float",}}\nDone.'
        self.assertEqual(
            agent_2._parse_schema_blueprint_response(raw), {"col": {"intended_type": "float"}}
        )

    def test_genuinely_broken_json_still_raises(self):
        with self.assertRaises(json.JSONDecodeError):
            agent_2._parse_schema_blueprint_response('{"a": 1 "b": 2}')  # missing comma, not trailing


class TestGeminiFallbackModelList(unittest.TestCase):
    def test_dead_gemini_2_5_flash_removed(self):
        self.assertNotIn("gemini-2.5-flash", agent_2.GEMINI_MODEL_FALLBACKS)
        self.assertNotIn("gemini-2.5-flash", agent_2._gemini_model_candidates())


class TestGroqBadJsonGeminiDown(unittest.TestCase):
    """When Groq emits unparseable JSON and Gemini is unavailable, the error must
    stay a JSONDecodeError so the caller's batch-halving retry still fires."""

    def _bad_json_groq_client(self):
        completions = SimpleNamespace(
            create=lambda *a, **k: SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"a": 1 "b": 2}'))]
            )
        )
        return SimpleNamespace(chat=SimpleNamespace(completions=completions))

    def _raw_profile(self, cols):
        return {"columns": {c: {"dtype": "int64", "missing_rate_pct": 0.0,
                                "unique_count": 1, "sample_values": [1]} for c in cols}}

    def test_reraised_as_jsondecodeerror_not_runtimeerror(self):
        df = pd.DataFrame({"c1": [1], "c2": [2]})
        with patch.object(agent_2, "_get_groq_client", return_value=self._bad_json_groq_client()), \
             patch.object(agent_2, "_call_gemini_json_with_failover",
                          side_effect=RuntimeError("Gemini calls failed across 4 attempt(s): 404")):
            with self.assertRaises(json.JSONDecodeError):
                agent_2._call_llm_for_schema_blueprint(df, {"c1": "numeric", "c2": "numeric"},
                                                       self._raw_profile(["c1", "c2"]), ["c1", "c2"])

    def test_halving_retry_recovers_when_smaller_batches_parse(self):
        df = pd.DataFrame({"c1": [1], "c2": [2]})
        calls = {"n": 0}

        def fake_single_call(_df, _types, _profile, columns):
            calls["n"] += 1
            if len(columns) > 1:
                raise json.JSONDecodeError("Expecting ',' delimiter", "{}", 5)
            return {columns[0]: {"intended_type": "float", "semantic_tag": "categorical_label"}}

        with patch.object(agent_2, "_call_llm_for_schema_blueprint", side_effect=fake_single_call):
            merged = agent_2._call_llm_for_schema_blueprint_with_retry(
                df, {"c1": "numeric", "c2": "numeric"}, {"columns": {}}, ["c1", "c2"]
            )

        self.assertEqual(set(merged), {"c1", "c2"})
        self.assertGreaterEqual(calls["n"], 3)  # 1 failed full batch + 2 single-column retries


if __name__ == "__main__":
    unittest.main()
