"""
Tests for Bradley-Terry ranking — the methodologically load-bearing scorer
for Task B. Numerical correctness here is non-negotiable.

Run: python -m pytest tests/test_bradley_terry.py
Or:  python tests/test_bradley_terry.py  (uses unittest fallback)
"""

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.bradley_terry import fit_bradley_terry, rank_models


class TestBradleyTerry(unittest.TestCase):

    def test_single_model(self):
        """One model alone: strength = 1.0 by convention."""
        strengths = fit_bradley_terry([])
        self.assertEqual(strengths, {})

    def test_two_models_a_dominates(self):
        """A wins every match → A has higher strength."""
        verdicts = [{"model_a": "A", "model_b": "B", "winner": "A"} for _ in range(10)]
        strengths = fit_bradley_terry(verdicts)
        self.assertGreater(strengths["A"], strengths["B"])

    def test_two_models_tied(self):
        """A and B split 50/50 → equal strengths."""
        verdicts = (
            [{"model_a": "A", "model_b": "B", "winner": "A"} for _ in range(5)]
            + [{"model_a": "A", "model_b": "B", "winner": "B"} for _ in range(5)]
        )
        strengths = fit_bradley_terry(verdicts)
        self.assertAlmostEqual(strengths["A"], strengths["B"], places=4)

    def test_ties_count_as_half(self):
        """A pure TIE outcome → equal strengths (same as 50/50 wins)."""
        verdicts = [{"model_a": "A", "model_b": "B", "winner": "TIE"} for _ in range(10)]
        strengths = fit_bradley_terry(verdicts)
        self.assertAlmostEqual(strengths["A"], strengths["B"], places=4)

    def test_transitive_ranking(self):
        """A beats B beats C → BT recovers A > B > C."""
        verdicts = (
            [{"model_a": "A", "model_b": "B", "winner": "A"} for _ in range(8)]
            + [{"model_a": "A", "model_b": "B", "winner": "B"} for _ in range(2)]
            + [{"model_a": "B", "model_b": "C", "winner": "A"} for _ in range(8)]
            + [{"model_a": "B", "model_b": "C", "winner": "B"} for _ in range(2)]
            + [{"model_a": "A", "model_b": "C", "winner": "A"} for _ in range(9)]
            + [{"model_a": "A", "model_b": "C", "winner": "B"} for _ in range(1)]
        )
        strengths = fit_bradley_terry(verdicts)
        ranking = rank_models(strengths)
        self.assertEqual([m for m, _ in ranking], ["A", "B", "C"])

    def test_geometric_mean_normalized(self):
        """Output strengths normalized so geometric mean = 1."""
        verdicts = [
            {"model_a": "A", "model_b": "B", "winner": "A"},
            {"model_a": "B", "model_b": "C", "winner": "A"},
            {"model_a": "A", "model_b": "C", "winner": "A"},
        ]
        strengths = fit_bradley_terry(verdicts)
        valid = [s for s in strengths.values() if s > 0]
        geomean = math.exp(sum(math.log(s) for s in valid) / len(valid))
        self.assertAlmostEqual(geomean, 1.0, places=3)

    def test_rank_models_descending(self):
        """rank_models returns descending by strength."""
        strengths = {"A": 0.5, "B": 2.0, "C": 1.0}
        ranking = rank_models(strengths)
        self.assertEqual([m for m, _ in ranking], ["B", "C", "A"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
