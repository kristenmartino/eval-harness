"""
Tests for eval/runner.py — the reproducibility and held-out-discipline guarantees.

These cover the parts a skeptical reviewer would poke at:
  - fallback item IDs are stable (SHA-256, not salted builtin hash())
  - a held-out set cannot be run without explicit opt-in
  - a held-out set is verified against its committed lock manifest
  - resuming into a mismatched output file is refused
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters.mock import MockAdapter  # noqa: E402
from tasks import categorization  # noqa: E402
from eval import runner  # noqa: E402
from eval.runner import (  # noqa: E402
    HeldOutAccessError,
    HoldoutLockError,
    ResumeHeaderMismatch,
    _holdout_aggregate,
    _is_holdout,
    _stable_item_id,
)

ADAPTER = MockAdapter(response_map={"Apple": "Tech"}, model_id="mock-v1")
TASK = categorization.task


def _write_jsonl(path: Path, items: list) -> None:
    path.write_text("".join(json.dumps(it) + "\n" for it in items))


class TestStableItemId(unittest.TestCase):

    def test_key_order_independent_and_deterministic(self):
        a = _stable_item_id({"text": "x", "category": "Tech"})
        b = _stable_item_id({"category": "Tech", "text": "x"})
        self.assertEqual(a, b)
        self.assertEqual(len(a), 16)
        self.assertTrue(all(c in "0123456789abcdef" for c in a))

    def test_distinct_items_distinct_ids(self):
        self.assertNotEqual(_stable_item_id({"text": "a"}), _stable_item_id({"text": "b"}))

    def test_runner_uses_stable_fallback_when_no_id(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            item = {"text": "Apple thing", "category": "Tech"}  # no id / article_id
            ds = d / "dev_set.jsonl"
            _write_jsonl(ds, [item])
            out = d / "out.jsonl"
            runner.run(ADAPTER, TASK, ds, out, repo_root=d)
            pred = json.loads(out.read_text().splitlines()[1])
            self.assertEqual(pred["item_id"], _stable_item_id(item))


class TestIsHoldout(unittest.TestCase):

    def test_detection(self):
        self.assertTrue(_is_holdout(Path("data/holdout/set1.jsonl")))
        self.assertTrue(_is_holdout(Path("data/sample_holdout.jsonl")))
        self.assertFalse(_is_holdout(Path("data/dev/set1.jsonl")))
        self.assertFalse(_is_holdout(Path("data/sample_categorization.jsonl")))


class TestHeldOutGate(unittest.TestCase):

    def _setup(self, d: Path):
        items = [
            {"id": "h1", "text": "Apple", "category": "Tech"},
            {"id": "h2", "text": "Senate", "category": "Politics"},
        ]
        ds = d / "set1_holdout.jsonl"
        _write_jsonl(ds, items)
        manifest = d / "data" / "holdout.sha256"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps({
            "schema": "holdout-lock/v1",
            "dataset_file": str(ds),
            "n_items": len(items),
            "aggregate_sha256": _holdout_aggregate(items),
        }))
        return ds, items, manifest

    def test_refuses_without_flag(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            ds, _, _ = self._setup(d)
            with self.assertRaises(HeldOutAccessError):
                runner.run(ADAPTER, TASK, ds, d / "out.jsonl", repo_root=d)

    def test_allows_with_flag_and_records_verified_hash(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            ds, items, _ = self._setup(d)
            out = d / "out.jsonl"
            summary = runner.run(ADAPTER, TASK, ds, out, repo_root=d, include_held_out=True)
            self.assertTrue(summary["held_out"])
            header = json.loads(out.read_text().splitlines()[0])
            self.assertEqual(header["held_out"], True)
            self.assertEqual(header["holdout_aggregate_sha256"], _holdout_aggregate(items))

    def test_hash_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            ds, _, manifest = self._setup(d)
            m = json.loads(manifest.read_text())
            m["aggregate_sha256"] = "0" * 64
            manifest.write_text(json.dumps(m))
            with self.assertRaises(HoldoutLockError):
                runner.run(ADAPTER, TASK, ds, d / "out.jsonl", repo_root=d, include_held_out=True)

    def test_missing_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            ds = d / "set1_holdout.jsonl"
            _write_jsonl(ds, [{"id": "h1", "text": "x", "category": "Tech"}])
            with self.assertRaises(HoldoutLockError):
                runner.run(ADAPTER, TASK, ds, d / "out.jsonl", repo_root=d, include_held_out=True)

    def test_split_override_forces_holdout_on_plain_name(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            ds = d / "plain.jsonl"
            _write_jsonl(ds, [{"id": "h1", "text": "x", "category": "Tech"}])
            with self.assertRaises(HeldOutAccessError):
                runner.run(ADAPTER, TASK, ds, d / "out.jsonl", repo_root=d, split="holdout")


class TestResume(unittest.TestCase):

    def test_resume_skips_completed(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            ds = d / "dev.jsonl"
            _write_jsonl(ds, [{"id": "a", "text": "Apple", "category": "Tech"}])
            out = d / "out.jsonl"
            s1 = runner.run(ADAPTER, TASK, ds, out, repo_root=d)
            s2 = runner.run(ADAPTER, TASK, ds, out, repo_root=d)
            self.assertEqual(s1["completed"], 1)
            self.assertEqual(s2["completed"], 0)
            self.assertEqual(s2["skipped_resume"], 1)

    def test_resume_refuses_on_model_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            ds = d / "dev.jsonl"
            _write_jsonl(ds, [{"id": "a", "text": "Apple", "category": "Tech"}])
            out = d / "out.jsonl"
            runner.run(ADAPTER, TASK, ds, out, repo_root=d)
            other = MockAdapter(response_map={}, model_id="a-different-model")
            with self.assertRaises(ResumeHeaderMismatch):
                runner.run(other, TASK, ds, out, repo_root=d)


if __name__ == "__main__":
    unittest.main(verbosity=2)
