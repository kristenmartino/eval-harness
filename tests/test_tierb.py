"""
Tests for the Tier-B judged path (eval/tierb.py) + the key-free KeywordJudge.

Run: python -m unittest tests.test_tierb
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from adapters.keyword_judge import KeywordJudge
from eval import tierb
from eval.stats import pointwise_label

GOLDEN = ROOT / "data" / "set5"


class TestKeywordJudge(unittest.TestCase):

    def test_support_when_covered(self):
        label = pointwise_label(KeywordJudge(),
                                "planned capacity 2200 MW",
                                "the plant's planned capacity is 2200 MW")
        self.assertEqual(label, "support")

    def test_not_support_when_uncovered(self):
        label = pointwise_label(KeywordJudge(),
                                "bananas are yellow fruit",
                                "the planned capacity is 2200 MW")
        self.assertEqual(label, "not_support")

    def test_partial_band(self):
        # 1 of 2 content words covered → 0.5 overlap → partial (>=0.3, <0.6)
        label = pointwise_label(KeywordJudge(),
                                "capacity gigawatts", "the capacity is high")
        self.assertEqual(label, "partial")

    def test_deterministic(self):
        j = KeywordJudge()
        a = pointwise_label(j, "capacity 2200", "capacity is 2200 MW")
        b = pointwise_label(j, "capacity 2200", "capacity is 2200 MW")
        self.assertEqual(a, b)


class TestRunTierBOnGolden(unittest.TestCase):

    def test_golden_passes_with_keyword_judge(self):
        result = tierb.run_tierb(GOLDEN, KeywordJudge())
        self.assertTrue(result.passed, result.failures)
        self.assertEqual(result.scorecard["correct_rate"], 1.0)
        self.assertEqual(result.scorecard["mean_recall"], 1.0)
        self.assertGreaterEqual(result.scorecard["n_scenarios"], 3)

    def test_path_discriminates_a_bad_judge_fails(self):
        """A judge that can never reach 'support' → recall 0, correct_rate 0,
        gate fails — proves the judged path isn't vacuously green."""
        strict = KeywordJudge(support_at=1.5, partial_at=1.5)
        result = tierb.run_tierb(GOLDEN, strict)
        self.assertEqual(result.scorecard["correct_rate"], 0.0)
        self.assertLess(result.scorecard["mean_recall"], 0.8)
        self.assertFalse(result.passed)

    def test_reports_ci_on_recall(self):
        ci = tierb.run_tierb(GOLDEN, KeywordJudge()).scorecard["recall_ci"]
        self.assertIn("lo", ci)
        self.assertIn("hi", ci)
        self.assertEqual(ci["n"], 3)


class TestAggregate(unittest.TestCase):

    def test_aggregate_means_and_rates(self):
        per = [
            {"scenario_id": "a", "recall": 1.0, "vital_recall": 1.0,
             "precision": 1.0, "f1": 1.0, "correct": True, "faithfulness": 1.0},
            {"scenario_id": "b", "recall": 0.5, "vital_recall": 0.0,
             "precision": 1.0, "f1": 0.66, "correct": False, "faithfulness": 0.5},
        ]
        agg = tierb._aggregate(per)
        self.assertEqual(agg["mean_recall"], 0.75)
        self.assertEqual(agg["correct_rate"], 0.5)
        self.assertEqual(agg["mean_faithfulness"], 0.75)

    def test_empty(self):
        self.assertEqual(tierb._aggregate([])["n_scenarios"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
