"""
Tests for eval/stats.py: the generic bootstrap, paired delta, McNemar exact,
Cohen's kappa, and the pointwise-judge scorers (nugget recall, faithfulness).

Run: python -m unittest tests.test_stats
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters.scripted import ScriptedAdapter
from eval import stats


class TestBootstrap(unittest.TestCase):

    def test_seeded_is_reproducible(self):
        vals = [0.1 * i for i in range(20)]
        a = stats.seeded_bootstrap_ci(vals, seed=7)
        b = stats.seeded_bootstrap_ci(vals, seed=7)
        self.assertEqual(a, b)

    def test_ci_brackets_point_on_supported_data(self):
        vals = [1.0] * 30
        ci = stats.seeded_bootstrap_ci(vals)
        self.assertEqual(ci["point"], 1.0)
        self.assertLessEqual(ci["lo"], ci["point"])
        self.assertGreaterEqual(ci["hi"], ci["point"])

    def test_empty_is_safe(self):
        self.assertEqual(stats.seeded_bootstrap_ci([])["n"], 0)

    def test_arbitrary_statistic(self):
        ci = stats.seeded_bootstrap_ci([1, 2, 3, 4], statistic=max)
        self.assertEqual(ci["point"], 4)


class TestPairedDelta(unittest.TestCase):

    def test_positive_delta_excludes_zero(self):
        before = [0.0] * 20
        after = [1.0] * 20
        d = stats.paired_delta_ci(before, after)
        self.assertAlmostEqual(d["delta"], 1.0)
        self.assertTrue(d["excludes_zero"])

    def test_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            stats.paired_delta_ci([1], [1, 2])


class TestMcNemar(unittest.TestCase):

    def test_symmetric_is_nonsignificant(self):
        r = stats.mcnemar_exact(5, 5)
        self.assertEqual(r["p_value"], 1.0)
        self.assertEqual((r["b"], r["c"]), (5, 5))

    def test_lopsided_is_significant(self):
        r = stats.mcnemar_exact(10, 0)
        self.assertLess(r["p_value"], 0.01)

    def test_no_discordant_pairs(self):
        self.assertEqual(stats.mcnemar_exact(0, 0)["p_value"], 1.0)


class TestKappa(unittest.TestCase):

    def test_perfect_agreement(self):
        self.assertEqual(stats.cohens_kappa(["a", "b", "a"], ["a", "b", "a"]), 1.0)

    def test_known_value(self):
        # 2x2 classic: po=0.7, pe=0.5 → kappa=0.4
        a = ["y"] * 5 + ["n"] * 5
        b = ["y"] * 4 + ["n"] * 1 + ["y"] * 2 + ["n"] * 3
        self.assertAlmostEqual(stats.cohens_kappa(a, b), 0.4, places=2)

    def test_chance_agreement_is_zero(self):
        self.assertEqual(stats.cohens_kappa(["a", "a"], ["a", "a"]), 1.0)


class TestPointwiseParse(unittest.TestCase):

    def test_labels(self):
        self.assertEqual(stats.parse_pointwise("LABEL: support"), "support")
        self.assertEqual(stats.parse_pointwise("**LABEL:** partial"), "partial")
        self.assertEqual(stats.parse_pointwise("LABEL: not_support"), "not_support")

    def test_malformed_is_not_support(self):
        """Conservative abstain — an unparseable judgment must not score support."""
        self.assertEqual(stats.parse_pointwise("I think it's fine"), "not_support")


class TestJudgeScorers(unittest.TestCase):

    def test_nugget_recall_vital_weighting(self):
        # 2 nuggets: vital supported, okay not_support.
        judge = ScriptedAdapter(["LABEL: support", "LABEL: not_support"])
        nuggets = [{"text": "capacity is 2200 MW", "weight": "vital"},
                   {"text": "built recently", "weight": "okay"}]
        r = stats.nugget_recall(judge, "answer", nuggets)
        # got = 1.0*1.0 + 0.5*0.0 = 1.0; total = 1.5 → recall = 0.6667
        self.assertAlmostEqual(r["recall"], round(1.0 / 1.5, 4))
        self.assertEqual(r["vital_recall"], 1.0)

    def test_citation_faithfulness(self):
        judge = ScriptedAdapter(["LABEL: support", "LABEL: not_support",
                                 "LABEL: support"])
        r = stats.citation_faithfulness(judge, ["c1", "c2", "c3"], "context")
        # 2 supported, 1 not → 2/3
        self.assertEqual(r["supported"], 2)
        self.assertEqual(r["not_supported"], 1)
        self.assertAlmostEqual(r["faithfulness"], round(2 / 3, 4))

    def test_answer_correctness_gate(self):
        """vital-recall == 1.0 AND no unsupported claim → correct."""
        judge = ScriptedAdapter(["LABEL: support",   # nugget (vital)
                                 "LABEL: support"])   # claim precision
        out = stats.answer_correctness(
            judge, "2200 MW", [{"text": "2200 MW", "weight": "vital"}],
            claims=["the capacity is 2200 MW"], reference_context="2200 MW")
        self.assertTrue(out["correct"])
        self.assertEqual(out["precision"], 1.0)

    def test_answer_correctness_recall_only_when_no_claims(self):
        judge = ScriptedAdapter(["LABEL: support"])
        out = stats.answer_correctness(judge, "x",
                                       [{"text": "y", "weight": "vital"}])
        self.assertIsNone(out["precision"])
        self.assertEqual(out["f1"], out["recall"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
