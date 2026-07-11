"""
Tests for the cassette replay adapter (adapters/replay.py): request-key
canonicalization, replay hit/miss, and the record→replay roundtrip.

Run: python -m unittest tests.test_replay
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters.base import SamplingParams
from adapters.replay import (
    RecordingAdapter,
    ReplayAdapter,
    ReplayMiss,
    canonical_request_key,
)
from adapters.scripted import ScriptedAdapter
from agent.loop import run_agent
from agent.tools import build_mock_registry

P = SamplingParams(temperature=0.0, max_tokens=512)


class TestRequestKey(unittest.TestCase):

    def test_same_inputs_same_key(self):
        a = canonical_request_key("m", "prompt", P, "h")
        b = canonical_request_key("m", "prompt", P, "h")
        self.assertEqual(a, b)

    def test_prompt_change_moves_key(self):
        """The whole point: an edited prompt → different key → replay miss."""
        a = canonical_request_key("m", "prompt v1", P, "h")
        b = canonical_request_key("m", "prompt v2", P, "h")
        self.assertNotEqual(a, b)

    def test_registry_hash_moves_key(self):
        """A tool-schema change (moves tool_registry_hash) invalidates cassettes."""
        a = canonical_request_key("m", "p", P, "hash_v1")
        b = canonical_request_key("m", "p", P, "hash_v2")
        self.assertNotEqual(a, b)

    def test_temperature_moves_key(self):
        a = canonical_request_key("m", "p", SamplingParams(temperature=0.0), "h")
        b = canonical_request_key("m", "p", SamplingParams(temperature=0.7), "h")
        self.assertNotEqual(a, b)


class TestReplayAdapter(unittest.TestCase):

    def test_hit_returns_recorded_text(self):
        key = canonical_request_key("m", "hello", P, "")
        adapter = ReplayAdapter({key: "world"}, "m")
        self.assertEqual(adapter.complete("hello", P).text, "world")

    def test_miss_raises(self):
        adapter = ReplayAdapter({}, "m")
        with self.assertRaises(ReplayMiss):
            adapter.complete("anything", P)
        self.assertEqual(len(adapter.misses), 1)


class TestRoundtrip(unittest.TestCase):

    def test_record_then_replay_reproduces_run(self):
        """Record a full agent run, then replay the cassette → identical run,
        with zero misses (proves the keys the loop generates are stable)."""
        script = [
            "ROUTE: retrieve\nQUERY: vogtle",
            'TOOL: vector_search\nARGS: {"query": "vogtle capacity"}',
            "TOOL: none",
            "ANSWER: 2200 MW\nCITATIONS: sift://energy/vogtle-capacity#0",
            "VERDICT: pass",
        ]
        reg = build_mock_registry()
        trh = reg.registry_hash()
        recorder = RecordingAdapter(ScriptedAdapter(script, "golden-v1"),
                                    tool_registry_hash=trh)
        run1 = run_agent(recorder, reg, "q", clock=lambda: "t")

        replay = ReplayAdapter(recorder.cassette, "golden-v1", tool_registry_hash=trh)
        run2 = run_agent(replay, build_mock_registry(), "q", clock=lambda: "t")

        self.assertEqual(replay.misses, [])
        self.assertEqual(run1.final_answer, run2.final_answer)
        self.assertEqual(run1.citations, run2.citations)


if __name__ == "__main__":
    unittest.main(verbosity=2)
