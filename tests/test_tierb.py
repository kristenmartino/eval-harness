"""
Tests for the Tier-B judged path (eval/tierb.py) + the key-free KeywordJudge.

Run: python -m unittest tests.test_tierb
"""

import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from adapters.keyword_judge import KeywordJudge
from adapters.scripted import ScriptedAdapter
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

    def test_fabrication_and_removed_citations_fail_full_tierb_path(self):
        replay = tierb._replay_run

        def corrupt(scenario, golden_dir):
            run = replay(scenario, golden_dir)
            return replace(run, final_answer=run.final_answer + " The moon is made of cheese.",
                           citations=[])

        with patch("eval.tierb._replay_run", side_effect=corrupt):
            result = tierb.run_tierb(GOLDEN, KeywordJudge())
        self.assertFalse(result.passed)
        self.assertEqual(result.scorecard["correct_rate"], 0.0)
        self.assertLess(result.scorecard["mean_f1"], 1.0)
        self.assertEqual(result.scorecard["mean_faithfulness"], 0.0)

    def test_empty_judged_set_fails_without_thresholds(self):
        with patch("eval.tierb._load_scenarios", return_value=[]):
            result = tierb.run_tierb(GOLDEN, KeywordJudge())
        self.assertFalse(result.passed)


class TestAnswerAndCitationScoring(unittest.TestCase):

    def setUp(self):
        self.scenario = tierb._load_scenarios(GOLDEN)[0]
        self.run = tierb._replay_run(self.scenario, GOLDEN)
        self.rubric = self.scenario["rubric"]

    def test_fabricated_sentence_fails_with_correct_citations(self):
        bad = replace(self.run, final_answer=self.run.final_answer + " The moon is made of cheese.")
        result = tierb.score_run(bad, self.rubric, KeywordJudge())
        self.assertEqual(result["recall"], 1.0)
        self.assertLess(result["precision"], 1.0)
        self.assertLess(result["faithfulness"], 1.0)
        self.assertFalse(result["correct"])

    def test_missing_unknown_and_invented_span_citations_fail(self):
        for citations in ([], ["sift://nonexistent#0"], ["sift://energy/vogtle-capacity#999"],
                          self.run.citations + ["sift://nonexistent#0"]):
            with self.subTest(citations=citations):
                result = tierb.score_run(replace(self.run, citations=citations),
                                        self.rubric, KeywordJudge())
                self.assertFalse(result["correct"])
                self.assertFalse(result["citations_valid"])
                self.assertEqual(result["faithfulness"], 0.0)

    def test_gold_reference_does_not_substitute_for_retrieved_cited_text(self):
        # The answer matches the gold, but the observed source contradicts it.
        evidence = [dict(e, text="The facility closed permanently.") for e in self.run.evidence]
        result = tierb.score_run(replace(self.run, evidence=evidence), self.rubric, KeywordJudge())
        self.assertEqual(result["precision"], 1.0)
        self.assertLess(result["faithfulness"], 1.0)
        self.assertFalse(result["correct"])

    def test_titles_without_retrieved_text_cannot_validate_citations(self):
        evidence = [dict(e, text="") for e in self.run.evidence]
        result = tierb.score_run(replace(self.run, evidence=evidence), self.rubric, KeywordJudge())
        self.assertFalse(result["citations_valid"])
        self.assertFalse(result["correct"])

    def test_rubric_claims_cannot_hide_a_generated_fabrication(self):
        rubric = dict(self.rubric, claims=["the plant has 2200 MW capacity"])
        bad = replace(self.run, final_answer=self.run.final_answer + " The moon is made of cheese.")
        result = tierb.score_run(bad, rubric, KeywordJudge())
        self.assertIn("The moon is made of cheese.", result["claims"])
        self.assertFalse(result["correct"])

    def test_partially_supported_answer_fails_strict_gate(self):
        # Two supported nuggets, then partial precision and partial faithfulness.
        result = tierb.score_run(self.run, self.rubric, ScriptedAdapter([
            "LABEL: support", "LABEL: support", "LABEL: partial", "LABEL: partial",
        ]))
        self.assertEqual(result["faithfulness"], 0.5)
        self.assertFalse(result["correct"])


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
