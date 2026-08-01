import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from agents import agent_2


class _FakeGroqCompletions:
    def __init__(self):
        self.calls = []

    def create(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})
        messages = kwargs["messages"]
        user_content = messages[1]["content"]
        payload = user_content.split("Produce schema blueprint for these columns:\n", 1)[1]
        columns = json.loads(payload)

        blueprint = {}
        for column in columns:
            name = column["name"]
            inferred_type = column["inferred_type"]
            blueprint[name] = {
                "intended_type": "float" if inferred_type == "numeric" else inferred_type,
                "semantic_tag": "categorical_label",
                "is_identifier": False,
                "scaling_allowed": inferred_type == "numeric",
                "imputation_strategy": "median" if inferred_type == "numeric" else "mode",
                "null_policy": {
                    "action": "impute_median" if inferred_type == "numeric" else "impute_mode",
                    "threshold_pct": 20.0,
                    "reason": "fake LLM response for batching test",
                },
                "notes": "fake LLM response for batching test",
            }

        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps(blueprint))
                )
            ]
        )


class _FailingGroqCompletions:
    def create(self, *args, **kwargs):
        raise RuntimeError("simulated Groq outage")


class _FakeGroqClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=_FakeGroqCompletions())


class _FakeGeminiModels:
    def __init__(self):
        self.calls = []

    def generate_content(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})
        return SimpleNamespace(
            text=json.dumps({
                "customer_id": {
                    "intended_type": "string",
                    "semantic_tag": "identifier",
                    "is_identifier": True,
                    "scaling_allowed": False,
                    "imputation_strategy": "drop",
                    "notes": "Gemini fallback response",
                }
            })
        )


class _FakeGeminiClient:
    def __init__(self):
        self.models = _FakeGeminiModels()


class _QuotaThenSuccessGeminiModels:
    def __init__(self, should_fail=False):
        self.calls = []
        self.should_fail = should_fail

    def generate_content(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})
        if self.should_fail:
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return SimpleNamespace(
            text=json.dumps({
                "customer_id": {
                    "intended_type": "string",
                    "semantic_tag": "identifier",
                    "is_identifier": True,
                    "scaling_allowed": False,
                    "imputation_strategy": "drop",
                    "notes": "Gemini second key response",
                }
            })
        )


class _QuotaThenSuccessGeminiClient:
    def __init__(self, should_fail=False):
        self.models = _QuotaThenSuccessGeminiModels(should_fail=should_fail)


class TestAgent2Chunking(unittest.TestCase):
    def test_gemini_key_diagnostics_detects_distinct_and_duplicate_keys(self):
        with patch.dict(agent_2.os.environ, {"GEMINI_API_KEYS": "alpha,beta"}, clear=False):
            distinct = agent_2._describe_configured_gemini_keys()
        with patch.dict(agent_2.os.environ, {"GEMINI_API_KEYS": "alpha,alpha"}, clear=False):
            duplicate = agent_2._describe_configured_gemini_keys()

        self.assertEqual(distinct["raw_key_count"], 2)
        self.assertEqual(distinct["configured_key_count"], 2)
        self.assertEqual(distinct["distinct_key_count"], 2)
        self.assertFalse(distinct["has_duplicate_sources"])
        self.assertEqual(len(distinct["fingerprints"]), 2)
        self.assertEqual(len(set(distinct["fingerprints"])), 2)
        self.assertEqual(duplicate["raw_key_count"], 2)
        self.assertEqual(duplicate["configured_key_count"], 1)
        self.assertEqual(duplicate["distinct_key_count"], 1)
        self.assertTrue(duplicate["has_duplicate_sources"])

    def test_agent2_chunks_large_column_sets_across_multiple_llm_calls(self):
        columns = {f"column_{index}": [f"value_{index}", f"value_{index + 1}"] for index in range(53)}
        df = pd.DataFrame(columns)

        raw_profile = {
            "shape": {"rows": 2, "cols": 53},
            "columns": {
                name: {
                    "dtype": "object",
                    "missing_rate_pct": 0.0,
                    "unique_count": 2,
                    "sample_values": [f"value_{index}", f"value_{index + 1}"],
                }
                for index, name in enumerate(df.columns)
            },
            "duplicate_rows": 0,
            "total_missing": 0,
            "overall_missing_rate_pct": 0.0,
        }

        state = {
            "_df_cache": df,
            "raw_profile": raw_profile,
            "errors": [],
        }

        original_client = agent_2.client
        fake_client = _FakeGroqClient()
        agent_2.client = fake_client
        try:
            result = agent_2.agent2_semantic_tagger(state)
        finally:
            agent_2.client = original_client

        self.assertGreater(len(fake_client.chat.completions.calls), 1)
        self.assertEqual(len(result["schema_blueprint"]), 53)
        self.assertEqual(result["errors"], [])

    def test_agent2_uses_gemini_when_groq_fails(self):
        df = pd.DataFrame({"customer_id": ["c-1", "c-2"]})
        raw_profile = {
            "shape": {"rows": 2, "cols": 1},
            "columns": {
                "customer_id": {
                    "dtype": "object",
                    "missing_rate_pct": 0.0,
                    "unique_count": 2,
                    "sample_values": ["c-1", "c-2"],
                }
            },
            "duplicate_rows": 0,
            "total_missing": 0,
            "overall_missing_rate_pct": 0.0,
        }
        state = {"_df_cache": df, "raw_profile": raw_profile, "errors": []}

        original_groq = agent_2.client
        original_gemini = agent_2.gemini_client
        fake_gemini = _FakeGeminiClient()
        agent_2.client = SimpleNamespace(chat=SimpleNamespace(completions=_FailingGroqCompletions()))
        agent_2.gemini_client = fake_gemini
        try:
            result = agent_2.agent2_semantic_tagger(state)
        finally:
            agent_2.client = original_groq
            agent_2.gemini_client = original_gemini

        self.assertEqual(len(fake_gemini.models.calls), 1)
        self.assertEqual(result["schema_blueprint"]["customer_id"]["notes"], "Gemini fallback response")
        self.assertEqual(result["errors"], [])

    def test_agent2_fails_over_to_second_gemini_key(self):
        df = pd.DataFrame({"customer_id": ["c-1", "c-2"]})
        raw_profile = {
            "shape": {"rows": 2, "cols": 1},
            "columns": {
                "customer_id": {
                    "dtype": "object",
                    "missing_rate_pct": 0.0,
                    "unique_count": 2,
                    "sample_values": ["c-1", "c-2"],
                }
            },
            "duplicate_rows": 0,
            "total_missing": 0,
            "overall_missing_rate_pct": 0.0,
        }
        state = {"_df_cache": df, "raw_profile": raw_profile, "errors": []}

        first_client = _QuotaThenSuccessGeminiClient(should_fail=True)
        second_client = _QuotaThenSuccessGeminiClient(should_fail=False)
        original_cache = dict(agent_2._gemini_client_cache)
        original_rotation = agent_2._gemini_rotation_index

        with patch.dict(agent_2.os.environ, {"GEMINI_API_KEYS": "key-1,key-2"}, clear=False), \
             patch.object(agent_2, "_get_gemini_client_for_key", side_effect=lambda api_key: first_client if api_key == "key-1" else second_client):
            try:
                agent_2._gemini_client_cache.clear()
                agent_2._gemini_rotation_index = 0
                result = agent_2._call_gemini_json_with_failover(
                    contents="{}",
                    system_instruction="system",
                    temperature=0.1,
                    max_output_tokens=100,
                )
            finally:
                agent_2._gemini_client_cache.clear()
                agent_2._gemini_client_cache.update(original_cache)
                agent_2._gemini_rotation_index = original_rotation

        self.assertEqual(len(first_client.models.calls), 1)
        self.assertEqual(len(second_client.models.calls), 1)
        self.assertEqual(result["customer_id"]["notes"], "Gemini second key response")


if __name__ == "__main__":
    unittest.main()
