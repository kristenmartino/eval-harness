"""
Tests for eval/runner.py — the reproducibility and held-out-discipline guarantees.

These cover the parts a skeptical reviewer would poke at:
  - fallback item IDs are stable (SHA-256, not salted builtin hash())
  - a held-out set cannot be run without explicit opt-in
  - a held-out set is verified against its committed lock manifest
  - resuming into a mismatched output file is refused
"""

import json
import socket
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters.base import Completion  # noqa: E402
from adapters.mock import MockAdapter  # noqa: E402
from tasks import categorization  # noqa: E402
from eval import runner  # noqa: E402
from eval.runner import (  # noqa: E402
    HeldOutAccessError,
    HoldoutLockError,
    ResumeHeaderMismatch,
    _holdout_aggregate,
    _is_holdout,
    _is_transient,
    _stable_item_id,
)

ADAPTER = MockAdapter(response_map={"Apple": "Tech"}, model_id="mock-v1")
TASK = categorization.task


def _http_error(code: int) -> urllib.error.HTTPError:
    """Build an HTTPError with a given status (fp=None skips the body wiring)."""
    return urllib.error.HTTPError("http://x", code, f"status {code}", None, None)


class _FlakyAdapter:
    """Mock adapter that raises `exc` on the first `fail_times` calls, then
    returns a clean Completion. `.calls` records how many times the runner
    actually invoked complete() — the basis for asserting retry behavior."""

    def __init__(self, exc, fail_times, response="Tech", model_id="flaky-v1"):
        self.exc = exc
        self.fail_times = fail_times
        self.response = response
        self.model_id = model_id
        self.calls = 0

    def complete(self, prompt, params):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc
        return Completion(
            text=self.response, input_tokens=1, output_tokens=1,
            latency_ms=1.0, model_id=self.model_id, raw_metadata={},
        )


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


class TestIsTransient(unittest.TestCase):
    """Unit tests for the retry classifier — the load-bearing policy decision."""

    def test_connection_level_failures_are_transient(self):
        cases = [
            urllib.error.URLError("name resolution failed"),
            TimeoutError("timed out"),
            socket.timeout("timed out"),
            ConnectionError("connection reset"),
            ConnectionResetError("peer reset"),  # subclass of ConnectionError
        ]
        for exc in cases:
            with self.subTest(exc=type(exc).__name__):
                self.assertTrue(_is_transient(exc))

    def test_retryable_http_statuses_are_transient(self):
        for code in (408, 409, 425, 429, 500, 502, 503, 504):
            with self.subTest(code=code):
                self.assertTrue(_is_transient(_http_error(code)))

    def test_non_retryable_http_statuses_are_permanent(self):
        # HTTPError subclasses URLError, so these MUST be filtered by status —
        # otherwise a 404 would be wrongly retried as a generic URLError.
        for code in (400, 401, 403, 404, 410, 422, 451):
            with self.subTest(code=code):
                err = _http_error(code)
                self.assertIsInstance(err, urllib.error.URLError)  # the gotcha
                self.assertFalse(_is_transient(err))

    def test_non_network_exceptions_are_permanent(self):
        for exc in (ValueError("bad parse"), KeyError("category"), RuntimeError("x")):
            with self.subTest(exc=type(exc).__name__):
                self.assertFalse(_is_transient(exc))


class TestRetry(unittest.TestCase):
    """Integration tests through run() with a flaky adapter. backoff_base=0 keeps
    them instant (no real sleeping) except where the schedule itself is asserted."""

    def _dataset(self, d: Path) -> Path:
        ds = d / "dev.jsonl"
        _write_jsonl(ds, [{"id": "a", "text": "Apple", "category": "Tech"}])
        return ds

    def _last_row(self, out: Path) -> dict:
        # line 0 is the _meta header; the single prediction/error row is last.
        return json.loads(out.read_text().splitlines()[-1])

    def test_transient_then_success_writes_no_error_row(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            ds = self._dataset(d)
            out = d / "out.jsonl"
            adapter = _FlakyAdapter(urllib.error.URLError("blip"), fail_times=2)
            summary = runner.run(adapter, TASK, ds, out, repo_root=d,
                                 max_attempts=3, backoff_base=0)
            self.assertEqual(adapter.calls, 3)          # 2 failures + 1 success
            self.assertEqual(summary["completed"], 1)
            self.assertEqual(summary["errors"], 0)
            self.assertEqual(summary["transient_retries"], 2)
            row = self._last_row(out)
            self.assertNotIn("error", row)
            self.assertTrue(row["score"]["correct"])

    def test_transient_exhausts_attempts_and_annotates_row(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            ds = self._dataset(d)
            out = d / "out.jsonl"
            adapter = _FlakyAdapter(_http_error(503), fail_times=99)  # never recovers
            summary = runner.run(adapter, TASK, ds, out, repo_root=d,
                                 max_attempts=3, backoff_base=0)
            self.assertEqual(adapter.calls, 3)          # capped at max_attempts
            self.assertEqual(summary["completed"], 0)
            self.assertEqual(summary["errors"], 1)
            self.assertEqual(summary["transient_retries"], 2)
            row = self._last_row(out)
            self.assertEqual(row["attempts"], 3)
            self.assertEqual(row["error_classification"], "transient")
            self.assertIn("HTTPError", row["error"])

    def test_permanent_error_is_not_retried(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            ds = self._dataset(d)
            out = d / "out.jsonl"
            adapter = _FlakyAdapter(_http_error(404), fail_times=99)
            summary = runner.run(adapter, TASK, ds, out, repo_root=d,
                                 max_attempts=3, backoff_base=0)
            self.assertEqual(adapter.calls, 1)          # no retry on a permanent error
            self.assertEqual(summary["errors"], 1)
            self.assertEqual(summary["transient_retries"], 0)
            row = self._last_row(out)
            self.assertEqual(row["attempts"], 1)
            self.assertEqual(row["error_classification"], "permanent")

    def test_max_attempts_one_disables_retry(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            ds = self._dataset(d)
            out = d / "out.jsonl"
            adapter = _FlakyAdapter(urllib.error.URLError("blip"), fail_times=99)
            summary = runner.run(adapter, TASK, ds, out, repo_root=d,
                                 max_attempts=1, backoff_base=0)
            self.assertEqual(adapter.calls, 1)
            self.assertEqual(summary["errors"], 1)
            row = self._last_row(out)
            self.assertEqual(row["attempts"], 1)
            # still classified transient — there was just no attempt budget to use it
            self.assertEqual(row["error_classification"], "transient")

    def test_backoff_schedule_is_exponential(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            ds = self._dataset(d)
            out = d / "out.jsonl"
            adapter = _FlakyAdapter(urllib.error.URLError("blip"), fail_times=99)
            with mock.patch.object(runner.time, "sleep") as msleep:
                runner.run(adapter, TASK, ds, out, repo_root=d,
                           max_attempts=3, backoff_base=0.5)
            delays = [c.args[0] for c in msleep.call_args_list]
            # base*2**0, base*2**1; the 3rd attempt is the last, so no trailing sleep
            self.assertEqual(delays, [0.5, 1.0])

    def test_invalid_max_attempts_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            ds = self._dataset(d)
            with self.assertRaises(ValueError):
                runner.run(ADAPTER, TASK, ds, d / "out.jsonl", repo_root=d, max_attempts=0)

    def test_exhausted_error_is_reattempted_on_resume(self):
        # A retry-exhausted transient failure is left un-`done`; a later resume
        # (adapter recovered) completes it — in-process retry and resume compose.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            ds = self._dataset(d)
            out = d / "out.jsonl"
            flaky = _FlakyAdapter(urllib.error.URLError("blip"), fail_times=99,
                                  model_id="mock-v1")  # match ADAPTER for resume identity
            s1 = runner.run(flaky, TASK, ds, out, repo_root=d, max_attempts=2, backoff_base=0)
            self.assertEqual(s1["errors"], 1)
            self.assertEqual(s1["completed"], 0)
            s2 = runner.run(ADAPTER, TASK, ds, out, repo_root=d, max_attempts=2, backoff_base=0)
            self.assertEqual(s2["completed"], 1)
            self.assertEqual(s2["skipped_resume"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
