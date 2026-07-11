"""
Tests for the trajectory run-unit writer + deterministic scorers
(eval/trajectory.py): §3 field shape, and each layered/mechanical scorer.

Run: python -m unittest tests.test_trajectory
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters.scripted import ScriptedAdapter
from agent.loop import run_agent
from agent.tools import build_mock_registry
from eval import trajectory

FIXED_CLOCK = lambda: "2026-07-10T00:00:00Z"  # noqa: E731

GOOD_SCRIPT = [
    "ROUTE: retrieve\nQUERY: vogtle capacity",
    'TOOL: vector_search\nARGS: {"query": "vogtle capacity", "k": 2}',
    'TOOL: fetch_article\nARGS: {"id": "sift://energy/vogtle-capacity"}',
    "TOOL: none",
    "ANSWER: 2200 MW.\nCITATIONS: sift://energy/vogtle-capacity#0",
    "VERDICT: pass",
]

RUBRIC = {
    "scenario_id": "set5-vogtle-001",
    "allowed_tools": ["vector_search", "fetch_article", "list_by_category"],
    "required_tools": ["vector_search"],
    "precedence": [["vector_search", "fetch_article"], ["fetch_article", "synthesize"]],
    "step_budget": 8,
    "gold_article_ids": ["sift://energy/vogtle-capacity"],
}


def _good_unit():
    reg = build_mock_registry()
    run = run_agent(ScriptedAdapter(GOOD_SCRIPT), reg, "q", clock=FIXED_CLOCK)
    return trajectory.run_unit(
        run, scenario_id="set5-vogtle-001", sample=0, model_id="scripted-v1",
        tool_registry_hash=reg.registry_hash(), agent_version="agent@test")


class TestWriter(unittest.TestCase):

    def test_run_unit_has_header_and_outcome(self):
        unit = _good_unit()
        for key in ("agent_version", "tool_registry_hash", "model_id",
                    "scenario_id", "trajectory", "final_answer", "citations",
                    "terminated", "parse_status", "n_samples", "trial_temperature"):
            self.assertIn(key, unit)
        self.assertEqual(unit["terminated"], "answered")

    def test_roundtrip_jsonl(self):
        unit = _good_unit()
        out = Path(__file__).parent / "_tmp_traj.jsonl"
        try:
            header = trajectory.trajectory_header(
                agent_version="agent@test", tool_registry_hash="h",
                model_id="scripted-v1")
            trajectory.write_runs(out, header, [unit])
            import json
            rows = [json.loads(x) for x in out.read_text().splitlines() if x.strip()]
            self.assertTrue(rows[0]["_meta"])
            self.assertEqual(rows[1]["scenario_id"], "set5-vogtle-001")
        finally:
            out.unlink(missing_ok=True)


class TestScorers(unittest.TestCase):

    def test_good_trajectory_scores_perfect(self):
        card = trajectory.score_trajectory(_good_unit(), RUBRIC)
        self.assertEqual(card["tool_selection"]["process"], 1.0)
        self.assertEqual(card["arg_validity"]["arg_validity"], 1.0)
        self.assertTrue(card["citation_ids"]["gold_covered"])
        self.assertTrue(card["error_recovery"]["recovered"])
        self.assertTrue(card["step_efficiency"]["report_only"])

    def test_illegal_tool_zeroes_legality(self):
        traj = [
            {"role": "executor", "action": "delete_everything", "arg_valid": True},
        ]
        s = trajectory.score_tool_selection(traj, RUBRIC)
        self.assertEqual(s["legality"], 0.0)
        self.assertEqual(s["process"], 0.0)
        self.assertEqual(s["illegal_tools"], ["delete_everything"])

    def test_precedence_violation_penalized(self):
        """fetch_article before any vector_search violates a precedence edge."""
        traj = [
            {"role": "executor", "action": "fetch_article", "arg_valid": True},
            {"role": "executor", "action": "vector_search", "arg_valid": True},
            {"role": "executor", "action": "synthesize"},
        ]
        s = trajectory.score_tool_selection(traj, RUBRIC)
        self.assertLess(s["precedence"], 1.0)
        # state-legality also dings fetch before retrieval
        self.assertLess(s["state_legality"], 1.0)

    def test_arg_validity_counts_invalid(self):
        traj = [
            {"role": "executor", "action": "vector_search", "arg_valid": True},
            {"role": "executor", "action": "fetch_article", "arg_valid": False},
        ]
        s = trajectory.score_arg_validity(traj)
        self.assertEqual(s["n_calls"], 2)
        self.assertEqual(s["n_invalid"], 1)
        self.assertEqual(s["arg_validity"], 0.5)

    def test_error_recovery_flags_unrecovered(self):
        traj = [
            {"role": "executor", "action": "vector_search",
             "faults": ["ToolError: x", "ToolError: x"], "recovery": "fallback"},
        ]
        rec = trajectory.score_error_recovery(traj, terminated="max_steps")
        self.assertFalse(rec["recovered"])  # faulted but never produced an answer
        rec_ok = trajectory.score_error_recovery(traj, terminated="answered")
        self.assertTrue(rec_ok["recovered"])

    def test_citation_ids_missing_gold(self):
        s = trajectory.score_citation_ids(
            ["sift://tech/rlhf-approaches#0"], ["sift://energy/vogtle-capacity"])
        self.assertFalse(s["gold_covered"])
        self.assertEqual(s["missing_gold"], ["sift://energy/vogtle-capacity"])

    def test_efficiency_report_only_discloses_denominator(self):
        traj = [{"role": "router", "action": "route"}] * 12
        s = trajectory.score_step_efficiency(traj, {"step_budget": 6})
        self.assertTrue(s["report_only"])
        self.assertIn("over 12 steps", s["disclosure"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
