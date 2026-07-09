import json
import unittest
from types import SimpleNamespace

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


class _FakeGroqClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=_FakeGroqCompletions())


class TestAgent2Chunking(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
