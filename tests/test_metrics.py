"""
Tests for eval/metrics.py — the JSONL -> leaderboard headline aggregation.

This computes the published scoreboard's Task A number, so the tests target the
specific ways a categorization score gets silently inflated:
  - parse failures must count as wrong, not be skipped
  - error rows must drop coverage below 1.0, not vanish from the denominator
  - macro-F1's label space must be honored (gold-inferred vs official taxonomy)
  - the bootstrap CI must be reproducible under a fixed seed
  - --require-full-coverage must actually refuse an incomplete run
"""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.metrics import _bootstrap_ci, _split_rows, aggregate, main  # noqa: E402


HEADER = {
    "_meta": True,
    "model_id": "test-model:abc1234",
    "task": "A_categorization",
    "dataset_path": "data/sample.jsonl",
    "dataset_sha256_prefix": "deadbeefdeadbeef",
    "harness_git_sha": "f" * 40,
    "held_out": False,
    "started_at": "2026-06-01T00:00:00Z",
}


def _scored(item_id, predicted, gold):
    return {
        "model_id": HEADER["model_id"],
        "task": HEADER["task"],
        "item_id": item_id,
        "sample_idx": 0,
        "raw_output": predicted if predicted is not None else "???",
        "score": {
            "predicted": predicted,
            "gold": gold,
            "correct": predicted == gold and predicted is not None,
            "parse_failed": predicted is None,
        },
    }


def _error(item_id, classification="transient"):
    return {
        "model_id": HEADER["model_id"],
        "task": HEADER["task"],
        "item_id": item_id,
        "sample_idx": 0,
        "error": "URLError: connection refused",
        "attempts": 3,
        "error_classification": classification,
    }


# A reusable mixed set: 2 correct, 1 parse failure, 1 wrong.
#   accuracy = 2/4 = 0.5
#   macro-F1 over gold labels [Energy, Health, Politics, Tech]:
#     Energy 1.0, Health 0.0, Politics 0.0, Tech 0.6667  -> mean 0.4167
MIXED = [
    HEADER,
    _scored("a", "Tech", "Tech"),
    _scored("b", "Energy", "Energy"),
    _scored("c", None, "Politics"),    # parse failure -> predicted None
    _scored("d", "Tech", "Health"),    # wrong: predicted Tech, gold Health
]


class TestSplitRows(unittest.TestCase):

    def test_partition(self):
        header, scored, error = _split_rows(
            [HEADER, _scored("a", "Tech", "Tech"), _error("b")])
        self.assertTrue(header.get("_meta"))
        self.assertEqual(len(scored), 1)
        self.assertEqual(len(error), 1)

    def test_unknown_row_ignored(self):
        header, scored, error = _split_rows([{"weird": 1}])
        self.assertEqual(header, {})
        self.assertEqual(scored, [])
        self.assertEqual(error, [])


class TestAggregateBasics(unittest.TestCase):

    def test_all_correct_point(self):
        rows = [HEADER, _scored("a", "Tech", "Tech"), _scored("b", "Energy", "Energy")]
        s = aggregate(rows, n_boot=0)  # n_boot=0 -> CI collapses to the point
        self.assertEqual(s["accuracy"], 1.0)
        self.assertEqual(s["macro_f1"], 1.0)
        self.assertEqual(s["coverage"], 1.0)
        self.assertEqual(s["n_error"], 0)
        self.assertEqual(s["n_parse_failed"], 0)
        self.assertEqual((s["macro_f1_ci_low"], s["macro_f1_ci_high"]), (1.0, 1.0))

    def test_parse_failure_counts_as_wrong(self):
        s = aggregate(MIXED, n_boot=0)
        self.assertEqual(s["n_parse_failed"], 1)
        self.assertEqual(s["accuracy"], 0.5)
        self.assertAlmostEqual(s["macro_f1"], 0.4167, places=4)

    def test_default_labels_are_gold_inferred(self):
        s = aggregate(MIXED, n_boot=0)
        self.assertEqual(s["labels"], ["Energy", "Health", "Politics", "Tech"])

    def test_explicit_taxonomy_changes_macro_f1(self):
        # The official taxonomy includes classes absent from this small slice;
        # macro-F1 is taken over the full label space, so the number drops.
        full = ["Business", "Energy", "Health", "Politics", "Sports", "Tech"]
        s = aggregate(MIXED, labels=full, n_boot=0)
        self.assertEqual(s["labels"], full)
        self.assertAlmostEqual(s["macro_f1"], 0.2778, places=4)
        self.assertLess(s["macro_f1"], aggregate(MIXED, n_boot=0)["macro_f1"])

    def test_provenance_passthrough(self):
        s = aggregate(MIXED, n_boot=0)
        self.assertEqual(s["model_id"], HEADER["model_id"])
        self.assertEqual(s["dataset_sha256_prefix"], HEADER["dataset_sha256_prefix"])
        self.assertEqual(s["harness_git_sha"], HEADER["harness_git_sha"])
        self.assertEqual(s["held_out"], False)

    def test_empty_is_safe(self):
        s = aggregate([HEADER], n_boot=0)
        self.assertEqual(s["n_scored"], 0)
        self.assertEqual(s["coverage"], 0.0)
        self.assertEqual(s["macro_f1"], 0.0)
        self.assertEqual(s["accuracy"], 0.0)


class TestCoverage(unittest.TestCase):

    def test_error_rows_lower_coverage_not_dropped(self):
        rows = [HEADER, _scored("a", "Tech", "Tech"), _error("b"), _error("c")]
        s = aggregate(rows, n_boot=0)
        self.assertEqual(s["n_scored"], 1)
        self.assertEqual(s["n_error"], 2)
        self.assertAlmostEqual(s["coverage"], 1 / 3, places=6)
        self.assertEqual(s["accuracy"], 1.0)  # the scored item is still scored


class TestBootstrap(unittest.TestCase):

    def test_reproducible_under_seed(self):
        a = aggregate(MIXED, n_boot=500, seed=7)
        b = aggregate(MIXED, n_boot=500, seed=7)
        self.assertEqual(a["macro_f1_ci_low"], b["macro_f1_ci_low"])
        self.assertEqual(a["macro_f1_ci_high"], b["macro_f1_ci_high"])

    def test_ci_well_formed(self):
        s = aggregate(MIXED, n_boot=500, seed=7)
        self.assertLessEqual(s["macro_f1_ci_low"], s["macro_f1_ci_high"])
        self.assertGreaterEqual(s["macro_f1_ci_low"], 0.0)
        self.assertLessEqual(s["macro_f1_ci_high"], 1.0)

    def test_ci_brackets_point_on_stable_set(self):
        # 20 items (MIXED proportions x5) — enough resampling variety that the
        # percentile interval reliably contains the full-sample point estimate.
        rows = [HEADER] + [r for r in MIXED if not r.get("_meta")] * 5
        s = aggregate(rows, n_boot=1000, seed=0)
        self.assertLessEqual(s["macro_f1_ci_low"], s["macro_f1"])
        self.assertLessEqual(s["macro_f1"], s["macro_f1_ci_high"])

    def test_zero_boot_is_point(self):
        lo, hi = _bootstrap_ci(["Tech", "Energy"], ["Tech", "Energy"],
                               ["Energy", "Tech"], n_boot=0, seed=0, alpha=0.05)
        self.assertEqual((lo, hi), (1.0, 1.0))

    def test_single_item_is_point(self):
        lo, hi = _bootstrap_ci(["Tech"], ["Tech"], ["Tech"],
                               n_boot=1000, seed=0, alpha=0.05)
        self.assertEqual((lo, hi), (1.0, 1.0))


class TestCLI(unittest.TestCase):

    def _write(self, rows):
        f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
        for r in rows:
            f.write(json.dumps(r) + "\n")
        f.close()
        return f.name

    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_clean_run_exit_0_and_json(self):
        path = self._write([HEADER, _scored("a", "Tech", "Tech")])
        code, out, _ = self._run(["--results", path, "--bootstrap", "0"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["macro_f1"], 1.0)
        self.assertEqual(payload["coverage"], 1.0)

    def test_require_full_coverage_refuses_on_error(self):
        path = self._write([HEADER, _scored("a", "Tech", "Tech"), _error("b")])
        code, _, err = self._run(
            ["--results", path, "--bootstrap", "0", "--require-full-coverage"])
        self.assertEqual(code, 3)
        self.assertIn("coverage", err.lower())

    def test_coverage_gap_ok_without_flag(self):
        path = self._write([HEADER, _scored("a", "Tech", "Tech"), _error("b")])
        code, _, _ = self._run(["--results", path, "--bootstrap", "0"])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
