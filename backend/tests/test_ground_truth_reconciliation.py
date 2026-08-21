"""Reconciles the pipeline's headline report numbers against an independent,
from-scratch calculation on the RAW source CSV - not against the pipeline's own
cleaned/derived intermediate data (cleaned_df, stats). See docs/known_issues.md
items #1 and #10, which this harness exists to make concrete and reproducible.

Ground truth here is deliberately minimal and separately written: load the raw
CSV with plain pandas, do basic type coercion (to_numeric / to_datetime), and
sum/groupby directly - no shared code with agents/agent_3.py or agents/agent_4.py
other than `_normalize_category_label`, which is reused ONLY to align category
keys between the two sides (see note in `_group_revenue_by_category`) so this
harness measures value reconciliation, not the separate categorization/typo
bug already tracked as known_issues.md #2.

This test module is intentionally allowed to fail — per the task, no pipeline
bugs are fixed here. Run with:
    PYTHONPATH=$PWD uv run pytest -q tests/test_ground_truth_reconciliation.py -v
"""

import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from agents import agent_2
from agents.agent_1 import agent1_structural_profiler
from agents.agent_2 import agent2_semantic_tagger
from agents.agent_3 import agent3_preprocessor, _normalize_category_label
from agents.agent_4 import agent4_analysis

# Fixture: one of the sales datasets that actually has Order_Status /
# Payment_Status / Returned / Region / Product_Category / Customer_Segment /
# Sales_Representative / Gross_Sales / Net_Sales columns (several identical
# copies exist under uploads/; this is just one of them).
CSV_PATH = Path(__file__).resolve().parents[1] / "uploads" / "6b8a19c8e6ae40dba9058bbd121280bd.csv"

REVENUE_TOLERANCE_PCT = 2.0     # headline currency totals: relative % tolerance
GROWTH_TOLERANCE_PP = 2.0       # MoM/QoQ growth: absolute percentage-point tolerance
CATEGORY_COLUMNS = ["Order_Status", "Payment_Status", "Returned"]


def _pct_diff(actual: float, expected: float) -> float:
    if expected == 0:
        return 0.0 if actual == 0 else float("inf")
    return abs(actual - expected) / abs(expected) * 100


def _load_raw_ground_truth(csv_path: Path, rev_col: str) -> pd.DataFrame:
    """Independent load of the source file: no pipeline code, minimal coercion only."""
    raw = pd.read_csv(csv_path)
    raw["_revenue"] = pd.to_numeric(raw[rev_col], errors="coerce")
    raw["_order_date"] = pd.to_datetime(raw["Order_Date"], format="mixed", errors="coerce")
    raw["_year"] = raw["_order_date"].dt.year
    raw["_month"] = raw["_order_date"].dt.month
    raw["_quarter"] = raw["_order_date"].dt.quarter
    return raw


def _group_revenue_by_category(df: pd.DataFrame, col: str, rev_col: str, revenue_field: str) -> pd.Series:
    """Sum `revenue_field` grouped by `col`, canonicalizing category labels first.

    Uses agent_3._normalize_category_label (case/separator folding only) on BOTH
    the pipeline's cleaned column and the raw column so that Agent 3's cosmetic
    Title-Case canonicalization doesn't produce a spurious key mismatch here.
    This intentionally does NOT fix the deeper typo/abbreviation fragmentation
    ("C" vs "Central") - that is a separate, already-tracked issue (#2).
    """
    if pd.api.types.is_bool_dtype(df[col]):
        key = df[col]
    else:
        key = df[col].map(_normalize_category_label)
    return df.groupby(key)[revenue_field].sum()


class GroundTruthReconciliationTestCase(unittest.TestCase):
    """Compares report-facing pipeline numbers to an independently computed
    ground truth from the raw source CSV. No pipeline bugs are fixed here."""

    @classmethod
    def setUpClass(cls):
        if not CSV_PATH.exists():
            raise unittest.SkipTest(f"fixture not found: {CSV_PATH}")

        state = {"csv_path": str(CSV_PATH), "errors": []}
        state = agent1_structural_profiler(state)
        # Reconciliation only needs deterministic type/financial-role tagging (both
        # covered by the metadata-only fallback) - force it so this test never makes
        # a real Groq/Gemini call and can't hang on live rate limits.
        _no_llm_keys = {
            "GROQ_API_KEY": "", "GEMINI_API_KEY": "", "Gemini_API_Key": "", "GOOGLE_API_KEY": "",
            "GEMINI_API_KEYS": "", "GEMINI_API_KEY_1": "", "GEMINI_API_KEY_2": "",
            "GEMINI_API_KEY_3": "", "GEMINI_API_KEY_4": "", "GEMINI_API_KEY_5": "",
        }
        with patch.object(agent_2, "client", None), patch.object(agent_2, "gemini_client", None), \
                patch.dict(agent_2.os.environ, _no_llm_keys, clear=False):
            state = agent2_semantic_tagger(state)
        state = agent3_preprocessor(state)
        state = agent4_analysis(state)

        if state.get("errors"):
            raise unittest.SkipTest(f"pipeline reported errors, cannot reconcile: {state['errors']}")

        cls.state = state
        cls.cleaned_df = state["cleaned_df"]
        cls.stats = state["stats"]
        cls.rev_col = cls.stats["chart_plan"]["revenue_column"]
        if not cls.rev_col:
            raise unittest.SkipTest("pipeline resolved no revenue column; nothing to reconcile")

        cls.raw = _load_raw_ground_truth(CSV_PATH, cls.rev_col)

    # ── total revenue ────────────────────────────────────────────────────────

    def test_total_revenue_matches_raw_csv(self):
        pipeline_total = float(self.cleaned_df[self.rev_col].sum())
        raw_total = float(self.raw["_revenue"].sum())
        diff_pct = _pct_diff(pipeline_total, raw_total)
        self.assertLessEqual(
            diff_pct, REVENUE_TOLERANCE_PCT,
            f"Total {self.rev_col}: pipeline={pipeline_total:,.2f} vs raw CSV="
            f"{raw_total:,.2f} ({diff_pct:.2f}% off, tolerance {REVENUE_TOLERANCE_PCT}%)",
        )

    # ── revenue by Order_Status / Payment_Status / Returned ────────────────────

    def test_revenue_by_category_matches_raw_csv(self):
        for col in CATEGORY_COLUMNS:
            with self.subTest(column=col):
                pipeline_groups = _group_revenue_by_category(self.cleaned_df, col, self.rev_col, self.rev_col)
                raw_groups = _group_revenue_by_category(self.raw, col, self.rev_col, "_revenue")

                common_keys = sorted(set(pipeline_groups.index) & set(raw_groups.index), key=str)
                self.assertTrue(common_keys, f"{col}: no overlapping category keys between pipeline and raw")

                for key in common_keys:
                    with self.subTest(column=col, category=key):
                        pipeline_val = float(pipeline_groups[key])
                        raw_val = float(raw_groups[key])
                        diff_pct = _pct_diff(pipeline_val, raw_val)
                        self.assertLessEqual(
                            diff_pct, REVENUE_TOLERANCE_PCT,
                            f"{col}={key!r}: pipeline={pipeline_val:,.2f} vs raw={raw_val:,.2f} "
                            f"({diff_pct:.2f}% off, tolerance {REVENUE_TOLERANCE_PCT}%)",
                        )

    # ── month-over-month growth ─────────────────────────────────────────────

    def test_month_over_month_growth_matches_raw_csv(self):
        raw_monthly = (
            self.raw.dropna(subset=["_year", "_month"])
            .groupby(["_year", "_month"])["_revenue"].sum()
            .reset_index()
            .sort_values(["_year", "_month"])
        )
        raw_monthly["mom_growth_pct"] = raw_monthly["_revenue"].pct_change() * 100
        raw_monthly["label"] = (
            raw_monthly["_year"].astype(int).astype(str) + "-M"
            + raw_monthly["_month"].astype(int).astype(str).str.zfill(2)
        )
        raw_by_label = raw_monthly.set_index("label")["mom_growth_pct"].dropna().to_dict()

        pipeline_monthly = self.stats.get("growth_rates", {}).get("monthly", [])
        self.assertTrue(pipeline_monthly, "pipeline reported no monthly growth rows")

        for row in pipeline_monthly:
            year = int(row["Order_Date_year"])
            month = int(row["Order_Date_month"])
            label = f"{year}-M{month:02d}"
            if label not in raw_by_label:
                continue
            pipeline_pct = float(row["mom_growth_pct"])
            raw_pct = float(raw_by_label[label])
            # Sign and magnitude are checked as independent subTests so a sign flip is
            # always reported even when the magnitude assertion below also fails.
            with self.subTest(month=label, check="sign"):
                self.assertEqual(
                    np.sign(pipeline_pct), np.sign(raw_pct),
                    f"MoM growth {label}: SIGN MISMATCH - pipeline={pipeline_pct:.2f}% vs raw={raw_pct:.2f}%",
                )
            with self.subTest(month=label, check="magnitude"):
                self.assertLessEqual(
                    abs(pipeline_pct - raw_pct), GROWTH_TOLERANCE_PP,
                    f"MoM growth {label}: pipeline={pipeline_pct:.2f}% vs raw={raw_pct:.2f}% "
                    f"(diff {abs(pipeline_pct - raw_pct):.2f}pp, tolerance {GROWTH_TOLERANCE_PP}pp)",
                )

    # ── quarter-over-quarter growth ─────────────────────────────────────────

    def test_quarter_over_quarter_growth_matches_raw_csv(self):
        raw_quarterly = (
            self.raw.dropna(subset=["_year", "_quarter"])
            .groupby(["_year", "_quarter"])["_revenue"].sum()
            .reset_index()
            .sort_values(["_year", "_quarter"])
        )
        raw_quarterly["qoq_growth_pct"] = raw_quarterly["_revenue"].pct_change() * 100
        raw_quarterly["label"] = (
            raw_quarterly["_year"].astype(int).astype(str) + "-Q"
            + raw_quarterly["_quarter"].astype(int).astype(str)
        )
        raw_by_label = raw_quarterly.set_index("label")["qoq_growth_pct"].dropna().to_dict()

        pipeline_quarterly = self.stats.get("growth_rates", {}).get("quarterly", [])
        self.assertTrue(pipeline_quarterly, "pipeline reported no quarterly growth rows")

        for row in pipeline_quarterly:
            year = int(row["Order_Date_year"])
            quarter = int(row["Order_Date_quarter"])
            label = f"{year}-Q{quarter}"
            if label not in raw_by_label:
                continue
            pipeline_pct = float(row["qoq_growth_pct"])
            raw_pct = float(raw_by_label[label])
            with self.subTest(quarter=label, check="sign"):
                self.assertEqual(
                    np.sign(pipeline_pct), np.sign(raw_pct),
                    f"QoQ growth {label}: SIGN MISMATCH - pipeline={pipeline_pct:.2f}% vs raw={raw_pct:.2f}%",
                )
            with self.subTest(quarter=label, check="magnitude"):
                self.assertLessEqual(
                    abs(pipeline_pct - raw_pct), GROWTH_TOLERANCE_PP,
                    f"QoQ growth {label}: pipeline={pipeline_pct:.2f}% vs raw={raw_pct:.2f}% "
                    f"(diff {abs(pipeline_pct - raw_pct):.2f}pp, tolerance {GROWTH_TOLERANCE_PP}pp)",
                )

    # ── top/bottom N rankings ────────────────────────────────────────────────

    def test_top_bottom_rankings_match_raw_csv(self):
        top_bottom = self.stats.get("top_bottom", {}) or {}
        self.assertTrue(top_bottom, "pipeline reported no top/bottom rankings")

        for cat_col, data in top_bottom.items():
            raw_groups = _group_revenue_by_category(self.raw, cat_col, self.rev_col, "_revenue")
            rows = (data.get("top") or []) + (data.get("bottom") or [])
            for row in rows:
                category_value = row[cat_col]
                normalized_key = (
                    category_value if isinstance(category_value, (bool, np.bool_))
                    else _normalize_category_label(category_value)
                )
                if normalized_key not in raw_groups.index:
                    continue
                with self.subTest(column=cat_col, category=category_value):
                    pipeline_val = float(row["total_revenue"])
                    raw_val = float(raw_groups[normalized_key])
                    diff_pct = _pct_diff(pipeline_val, raw_val)
                    self.assertLessEqual(
                        diff_pct, REVENUE_TOLERANCE_PCT,
                        f"{cat_col}={category_value!r} ranking: pipeline={pipeline_val:,.2f} vs "
                        f"raw={raw_val:,.2f} ({diff_pct:.2f}% off, tolerance {REVENUE_TOLERANCE_PCT}%)",
                    )


if __name__ == "__main__":
    unittest.main()
