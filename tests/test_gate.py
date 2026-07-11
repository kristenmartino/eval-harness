"""
Tests for the Tier-A trajectory gate (eval/gate.py): it passes on the committed
golden, fails on a replay miss (drift), and fails on a threshold breach.

Run: python -m unittest tests.test_gate
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from eval.gate import _aggregate, _check, run_gate

GOLDEN = ROOT / "data" / "set5"


class TestGateOnGolden(unittest.TestCase):

    def test_committed_golden_passes(self):
        result = run_gate(GOLDEN)
        self.assertTrue(result.passed, result.failures)
        self.assertEqual(result.replay_misses, [])
        self.assertGreaterEqual(result.scorecard["n_scenarios"], 3)

    def test_all_must_pass_dims_at_ceiling(self):
        card = run_gate(GOLDEN).scorecard
        for dim in ("arg_validity", "error_recovery", "injection_held",
                    "citation_gold_covered"):
            self.assertEqual(card[dim], 1.0, dim)


class TestReplayMissFailsGate(unittest.TestCase):

    def test_stale_cassette_trips_the_gate(self):
        """Blanking a cassette models an un-re-recorded prompt edit → miss → fail."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "set5"
            shutil.copytree(GOLDEN, tmp)
            (tmp / "cassettes" / "set5-vogtle-001.json").write_text("{}")
            result = run_gate(tmp)
            self.assertIn("set5-vogtle-001", result.replay_misses)
            self.assertFalse(result.passed)


class TestThresholdChecks(unittest.TestCase):

    def test_must_pass_breach_is_a_failure(self):
        failures = _check({"arg_validity": 0.8},
                          {"must_pass": {"arg_validity": 1.0}, "graded": {}}, [])
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0][3], "must_pass")

    def test_graded_breach_is_a_failure(self):
        failures = _check({"tool_selection_process": 0.5},
                          {"must_pass": {}, "graded": {"tool_selection_process": 0.9}}, [])
        self.assertEqual(failures[0][3], "graded")

    def test_at_threshold_passes(self):
        failures = _check({"arg_validity": 1.0},
                          {"must_pass": {"arg_validity": 1.0}, "graded": {}}, [])
        self.assertEqual(failures, [])


class TestAggregate(unittest.TestCase):

    def test_binary_dim_takes_minimum(self):
        cards = [
            {"arg_validity": {"arg_validity": 1.0},
             "error_recovery": {"recovered": True},
             "tool_selection": {"process": 1.0},
             "citation_ids": {"gold_covered": True, "cited_ids": [], "missing_gold": []}},
            {"arg_validity": {"arg_validity": 0.5},   # one bad scenario
             "error_recovery": {"recovered": True},
             "tool_selection": {"process": 0.8},
             "citation_ids": {"gold_covered": True, "cited_ids": [], "missing_gold": []}},
        ]
        agg = _aggregate(cards, [])
        self.assertEqual(agg["arg_validity"], 0.5)          # min, not mean
        self.assertEqual(agg["tool_selection_process"], 0.9)  # mean of 1.0 and 0.8


if __name__ == "__main__":
    unittest.main(verbosity=2)
