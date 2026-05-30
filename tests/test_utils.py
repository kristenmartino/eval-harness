"""
Tests for utils.py — load_jsonl, percentile, macro_f1, accuracy.

These are the helpers the leaderboard's headline numbers will depend on. A
silent regression here corrupts the published scoreboard, so unit-test them.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import accuracy, load_jsonl, macro_f1, percentile


class TestPercentile(unittest.TestCase):

    def test_empty(self):
        self.assertEqual(percentile([], 50), 0.0)

    def test_single_value(self):
        self.assertEqual(percentile([42.0], 50), 42.0)
        self.assertEqual(percentile([42.0], 95), 42.0)

    def test_median_odd_length(self):
        self.assertEqual(percentile([1, 2, 3, 4, 5], 50), 3.0)

    def test_median_even_length(self):
        self.assertEqual(percentile([1, 2, 3, 4], 50), 2.5)

    def test_p100(self):
        self.assertEqual(percentile([1, 2, 3, 4, 5], 100), 5.0)

    def test_p0(self):
        self.assertEqual(percentile([1, 2, 3, 4, 5], 0), 1.0)

    def test_unsorted_input(self):
        """Input doesn't need to be pre-sorted."""
        self.assertEqual(percentile([5, 3, 1, 4, 2], 50), 3.0)


class TestMacroF1(unittest.TestCase):

    def test_perfect_prediction(self):
        preds = ["A", "B", "A", "B"]
        golds = ["A", "B", "A", "B"]
        self.assertEqual(macro_f1(preds, golds, ["A", "B"]), 1.0)

    def test_zero_prediction(self):
        preds = ["A", "A", "A", "A"]
        golds = ["B", "B", "B", "B"]
        self.assertEqual(macro_f1(preds, golds, ["A", "B"]), 0.0)

    def test_imbalanced_handled_correctly(self):
        """Macro F1 weights labels equally regardless of frequency."""
        # 9 A's all correct, 1 B all wrong → micro-F1 high, macro-F1 = (1.0 + 0.0) / 2 = 0.5
        preds = ["A"] * 9 + ["A"]
        golds = ["A"] * 9 + ["B"]
        # A: tp=9, fp=1, fn=0 → P=0.9, R=1.0, F1=0.947
        # B: tp=0, fp=0, fn=1 → F1=0
        result = macro_f1(preds, golds, ["A", "B"])
        self.assertAlmostEqual(result, (2 * 0.9 * 1.0 / 1.9) / 2, places=3)

    def test_missing_label_yields_zero(self):
        """A label with no support and no prediction → F1=0 for that label."""
        preds = ["A", "A"]
        golds = ["A", "A"]
        # Sports has no predictions and no gold → F1=0; macro-mean drops
        result = macro_f1(preds, golds, ["A", "Sports"])
        self.assertAlmostEqual(result, 0.5, places=3)


class TestAccuracy(unittest.TestCase):

    def test_perfect(self):
        self.assertEqual(accuracy(["A", "B", "A"], ["A", "B", "A"]), 1.0)

    def test_zero(self):
        self.assertEqual(accuracy(["A", "A", "A"], ["B", "B", "B"]), 0.0)

    def test_half(self):
        self.assertEqual(accuracy(["A", "B", "A", "B"], ["A", "A", "A", "A"]), 0.5)

    def test_none_predictions_are_wrong(self):
        """None predictions (parse failures) count as incorrect."""
        self.assertEqual(accuracy([None, "A", "A"], ["A", "A", "A"]), 2 / 3)

    def test_length_mismatch_raises(self):
        """Unequal lists must raise, not silently zip-truncate the scoreboard."""
        with self.assertRaises(ValueError):
            accuracy(["A", "B", "A"], ["A", "B"])
        with self.assertRaises(ValueError):
            accuracy(["A"], ["A", "B"])


class TestMetricLengthGuards(unittest.TestCase):

    def test_macro_f1_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            macro_f1(["A", "B", "A"], ["A", "B"], ["A", "B"])


class TestLoadJsonl(unittest.TestCase):

    def test_loads_valid_jsonl(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"id": 1, "x": "a"}\n')
            f.write('{"id": 2, "x": "b"}\n')
            tmp = Path(f.name)
        try:
            rows = load_jsonl(tmp)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["id"], 1)
        finally:
            tmp.unlink()

    def test_skips_blank_lines(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"id": 1}\n\n   \n{"id": 2}\n')
            tmp = Path(f.name)
        try:
            rows = load_jsonl(tmp)
            self.assertEqual(len(rows), 2)
        finally:
            tmp.unlink()

    def test_bad_json_raises_with_line(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"id": 1}\n')
            f.write('not json\n')
            tmp = Path(f.name)
        try:
            with self.assertRaises(ValueError) as cm:
                load_jsonl(tmp)
            self.assertIn("line 2", str(cm.exception))
        finally:
            tmp.unlink()


if __name__ == "__main__":
    unittest.main(verbosity=2)
