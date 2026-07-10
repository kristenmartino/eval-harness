"""
Tests for the agent loop (agent/loop.py): routing, the plan→execute cycle,
arg-validity recording, and fault recovery (retry → fallback vs unrecovered).

Run: python -m unittest tests.test_agent_loop
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters.scripted import ScriptExhausted, ScriptedAdapter
from agent.loop import run_agent
from agent.tools import Tool, ToolError, ToolRegistry, ToolResult, build_mock_registry

FIXED_CLOCK = lambda: "2026-07-10T00:00:00Z"  # noqa: E731


def _run(script, registry=None, **kw):
    registry = registry or build_mock_registry()
    adapter = ScriptedAdapter(script)
    return run_agent(adapter, registry, "test question", clock=FIXED_CLOCK, **kw)


class TestHappyPath(unittest.TestCase):

    def test_retrieve_then_answer(self):
        run = _run([
            "ROUTE: retrieve\nQUERY: vogtle capacity",
            'TOOL: vector_search\nARGS: {"query": "vogtle capacity", "k": 2}',
            'TOOL: fetch_article\nARGS: {"id": "sift://energy/vogtle-capacity"}',
            "TOOL: none",
            "ANSWER: 2200 MW.\nCITATIONS: sift://energy/vogtle-capacity#0",
            "VERDICT: pass",
        ])
        self.assertEqual(run.terminated, "answered")
        self.assertEqual(run.citations, ["sift://energy/vogtle-capacity#0"])
        roles = [s["role"] for s in run.trajectory]
        self.assertEqual(roles[0], "router")
        self.assertEqual(roles[-1], "critic")

    def test_direct_route_skips_retrieval(self):
        run = _run([
            "ROUTE: direct",
            "ANSWER: 4.\nCITATIONS: ",
            "VERDICT: pass",
        ])
        self.assertEqual(run.terminated, "answered")
        # No executor tool calls on the direct path.
        tool_steps = [s for s in run.trajectory
                      if s["role"] == "executor" and s["action"] != "synthesize"]
        self.assertEqual(tool_steps, [])

    def test_critic_revise_triggers_one_retry(self):
        run = _run([
            "ROUTE: retrieve\nQUERY: q",
            "TOOL: none",
            "ANSWER: draft one\nCITATIONS: ",
            "VERDICT: revise\nREASONS: ungrounded",
            "TOOL: none",
            "ANSWER: draft two\nCITATIONS: ",
            "VERDICT: pass",
        ], k_retries=1)
        self.assertEqual(run.terminated, "answered")
        self.assertEqual(run.final_answer, "draft two")
        verdicts = [s.get("verdict") for s in run.trajectory if s["role"] == "critic"]
        self.assertEqual(verdicts, ["revise", "pass"])


class TestArgValidity(unittest.TestCase):

    def test_invalid_args_recorded_not_crash(self):
        run = _run([
            "ROUTE: retrieve\nQUERY: q",
            'TOOL: vector_search\nARGS: {"k": 3}',   # missing required 'query'
            "TOOL: none",
            "ANSWER: x\nCITATIONS: ",
            "VERDICT: pass",
        ])
        exec_steps = [s for s in run.trajectory
                      if s["role"] == "executor" and s["action"] == "vector_search"]
        self.assertEqual(len(exec_steps), 1)
        self.assertFalse(exec_steps[0]["arg_valid"])
        self.assertEqual(run.terminated, "answered")  # bad args don't crash the run


class TestFaultRecovery(unittest.TestCase):

    def _faulting_registry(self):
        def boom(args):
            raise ToolError("simulated 503")
        return ToolRegistry([
            Tool("vector_search", "d",
                 {"type": "object", "properties": {"query": {"type": "string"}},
                  "required": ["query"]},
                 handler=boom),
        ])

    def test_fault_then_fallback_recovers(self):
        run = _run([
            "ROUTE: retrieve\nQUERY: q",
            'TOOL: vector_search\nARGS: {"query": "q"}',
            "TOOL: none",
            "ANSWER: abstaining, retrieval failed\nCITATIONS: ",
            "VERDICT: pass",
        ], registry=self._faulting_registry())
        self.assertEqual(run.terminated, "answered")
        faulted = [s for s in run.trajectory if s.get("faults")]
        self.assertEqual(len(faulted), 1)
        self.assertEqual(faulted[0]["recovery"], "fallback")
        self.assertGreaterEqual(len(faulted[0]["faults"]), 2)  # original + one retry

    def test_persistent_fault_unrecovered_when_no_answer(self):
        run = _run([
            "ROUTE: retrieve\nQUERY: q",
            'TOOL: vector_search\nARGS: {"query": "q"}',
            'TOOL: vector_search\nARGS: {"query": "q"}',
            'TOOL: vector_search\nARGS: {"query": "q"}',
        ], registry=self._faulting_registry(), max_steps=5)
        self.assertEqual(run.terminated, "max_steps")
        self.assertIsNone(run.final_answer)

    def test_faulted_tool_not_recalled(self):
        """After a tool faults twice it's skipped, not re-invoked, to bound the loop."""
        run = _run([
            "ROUTE: retrieve\nQUERY: q",
            'TOOL: vector_search\nARGS: {"query": "q"}',
            'TOOL: vector_search\nARGS: {"query": "q"}',
            "TOOL: none",
            "ANSWER: abstain\nCITATIONS: ",
            "VERDICT: pass",
        ], registry=self._faulting_registry())
        skipped = [s for s in run.trajectory
                   if s.get("result_summary", "").startswith("skipped")]
        self.assertEqual(len(skipped), 1)


class TestScriptGuard(unittest.TestCase):

    def test_exhausted_script_raises(self):
        with self.assertRaises(ScriptExhausted):
            _run(["ROUTE: retrieve\nQUERY: q", "TOOL: none"])  # no synth/critic


if __name__ == "__main__":
    unittest.main(verbosity=2)
