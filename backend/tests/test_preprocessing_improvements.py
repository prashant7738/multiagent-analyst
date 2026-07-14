import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from agents import agent_1, agent_2, agent_3


class TestAgent1Improvements(unittest.TestCase):
    def test_distribution_analysis_detects_skewness(self):
        series = pd.Series([1] * 12 + [2] * 4 + [100] * 4)

        analysis = agent_1._analyze_column_distribution(series)

        self.assertGreater(analysis["skewness"], 0)
        self.assertIn(analysis["distribution_type"], {"right_skewed", "normal", "symmetric"})
        self.assertIn("is_normal_distribution", analysis)

    def test_implicit_missing_values_are_detected(self):
        df = pd.DataFrame(
            {
                "age": [25, -999, 30, -999, 35],
                "status": ["ok", "n/a", "ok", "none", "ok"],
            }
        )

        implicit_missing = agent_1._detect_implicit_missingness(df)

        self.assertIn("age", implicit_missing)
        self.assertIn("status", implicit_missing)
        self.assertTrue(any(flag.get("sentinel") == -999 for flag in implicit_missing["age"]))
        self.assertTrue(any(flag.get("pattern") in {"n/a", "none"} for flag in implicit_missing["status"]))

    def test_column_relationships_identify_duplicates_and_correlations(self):
        df = pd.DataFrame(
            {
                "customer_id": [1, 2, 3, 4, 5],
                "mirror_id": [1, 2, 3, 4, 5],
                "sales": [10, 20, 30, 40, 50],
                "revenue": [20, 40, 60, 80, 100],
            }
        )
        profiles = {
            col: {
                "cardinality_ratio": 1.0,
                "missing_count": 0,
                "unique_count": int(df[col].nunique(dropna=False)),
            }
            for col in df.columns
        }

        relationships = agent_1._detect_column_relationships(df, profiles)

        self.assertIn("customer_id", relationships["potential_keys"])
        self.assertTrue(any(pair["col1"] == "customer_id" and pair["col2"] == "mirror_id" for pair in relationships["suspicious_duplicates"]))
        self.assertTrue(relationships["numeric_correlations"])

    def test_agent1_profile_contains_new_fields(self):
        csv_text = """id,age,salary,notes\n1,25,100,ok\n2,-999,250,n/a\n3,30,1000,none\n4,35,120,ok\n"""

        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as handle:
            handle.write(csv_text)
            temp_path = Path(handle.name)

        try:
            state = agent_1.agent1_structural_profiler({"csv_path": str(temp_path), "errors": []})
            raw_profile = state["raw_profile"]

            self.assertIn("distribution_analysis", raw_profile)
            self.assertIn("implicit_missing_values", raw_profile)
            self.assertIn("column_relationships", raw_profile)
            self.assertIn("outlier_analysis", raw_profile["columns"]["salary"])
        finally:
            temp_path.unlink(missing_ok=True)


class TestAgent2Improvements(unittest.TestCase):
    def test_semantic_confidence_varies_by_signal_quality(self):
        strong_profile = {
            "missing_rate_pct": 0.0,
            "unique_count": 100,
            "candidate_key_hint": True,
            "has_significant_outliers": False,
            "format_hints": {"identifier_like": True},
        }
        weak_profile = {
            "missing_rate_pct": 60.0,
            "unique_count": 3,
            "candidate_key_hint": False,
            "has_significant_outliers": True,
            "format_hints": {},
        }

        strong = agent_2._calculate_semantic_confidence(
            "customer_id",
            strong_profile,
            "string",
            "identifier",
            strong_profile["format_hints"],
        )
        weak = agent_2._calculate_semantic_confidence(
            "misc_column",
            weak_profile,
            "string",
            "categorical_label",
            weak_profile["format_hints"],
        )

        self.assertGreater(strong["confidence_score"], weak["confidence_score"])
        self.assertEqual(strong["confidence_level"], "high")
        self.assertIn("evidence", strong)

    def test_data_quality_assessment_identifies_problems(self):
        df = pd.DataFrame(
            {
                "age": [25, None, None, None],
                "salary": [100, 200, -999, 400],
                "status": ["ok", "n/a", "ok", "none"],
            }
        )
        raw_profile = {
            "overall_missing_rate_pct": 35.0,
            "duplicate_rate_pct": 10.0,
            "implicit_missing_values": {"salary": [{"sentinel": -999, "count": 1, "pct": 25.0}]},
            "distribution_analysis": {"salary": {"has_significant_outliers": True}},
        }

        assessment = agent_2._assess_data_quality_signals(df, raw_profile)

        self.assertEqual(assessment["risk_assessment"], "critical")
        self.assertEqual(assessment["preprocessing_recommendation"], "strict")
        self.assertTrue(any(issue.startswith("critical_missingness") for issue in assessment["quality_issues"]))
        self.assertIn("component_scores", assessment)

    def test_agent2_integration_attaches_confidence_and_metadata(self):
        csv_text = """customer_id,order_date,amount\nA100,2024-01-05,$10.50\nA101,2024-02-01,$20.25\n"""

        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as handle:
            handle.write(csv_text)
            temp_path = Path(handle.name)

        original_client = agent_2.client
        try:
            state = agent_1.agent1_structural_profiler({"csv_path": str(temp_path), "errors": []})
            agent_2.client = None
            result = agent_2.agent2_semantic_tagger(state)

            self.assertIn("__metadata__", result["schema_blueprint"])
            self.assertIn("data_quality_assessment", result["schema_blueprint"]["__metadata__"])
            self.assertIn("confidence", result["schema_blueprint"]["customer_id"])
            self.assertGreaterEqual(result["schema_blueprint"]["customer_id"]["confidence"]["confidence_score"], 0)
        finally:
            agent_2.client = original_client
            temp_path.unlink(missing_ok=True)


class TestAgent3Improvements(unittest.TestCase):
    def test_adaptive_outlier_clipping_uses_distribution_signals(self):
        series = pd.Series([10] * 20 + [1000])
        meta = {"semantic_tag": "currency", "intended_type": "float", "scaling_allowed": True}
        profile = {"distribution_analysis": {"distribution_type": "right_skewed", "has_significant_outliers": True}}
        context = {"risk_assessment": "critical"}

        clipped, clipped_count, bounds = agent_3._adaptive_outlier_clipping(series, meta, {}, profile=profile, data_quality_context=context)

        self.assertGreater(clipped_count, 0)
        self.assertTrue(bounds["method"].startswith("percentile"))
        self.assertLessEqual(float(clipped.max()), bounds["upper"])

    def test_enhanced_quality_score_returns_component_scores(self):
        df_raw = pd.DataFrame({"a": [1, None, 3], "b": [1, 2, 3]})
        df_clean = pd.DataFrame({"a": [1, 2, 3], "b": [1, 2, 3]})

        quality = agent_3._compute_enhanced_quality_score(
            df_raw,
            df_clean,
            {"checks": 10, "failed_rows": 2},
            {"quality_weights": {"remaining_null_pct": 0.5, "validation_fail_pct": 0.4, "duplicate_rate_pct": 0.1}},
            {"risk_assessment": "critical", "preprocessing_recommendation": "strict"},
        )

        self.assertIn("component_scores", quality)
        self.assertEqual(quality["risk_assessment"], "critical")
        self.assertIn("completeness", quality["component_scores"])

    def test_full_pipeline_preserves_component_scores(self):
        csv_text = """customer_id,age,salary,status\n1,25,100,ok\n2,-999,200,n/a\n3,30,1000,ok\n4,35,120,none\n"""

        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as handle:
            handle.write(csv_text)
            temp_path = Path(handle.name)

        original_client = agent_2.client
        try:
            state = agent_1.agent1_structural_profiler({"csv_path": str(temp_path), "errors": []})
            agent_2.client = None
            state = agent_2.agent2_semantic_tagger(state)

            with patch.object(agent_3, "_export_cleaned_dataset", return_value=(str(temp_path.with_suffix(".cleaned.csv")), None)):
                result = agent_3.agent3_preprocessor(state)

            self.assertIn("data_quality", result)
            self.assertIn("component_scores", result["data_quality"])
            self.assertIn("cleaned_df", result)
            self.assertIsNotNone(result["cleaned_df"])
        finally:
            agent_2.client = original_client
            temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()