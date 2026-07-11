#!/usr/bin/env python3
"""
Demonstrates the v0.3 agent trajectory pipeline end-to-end with a
ScriptedAdapter + MockToolRegistry — no Ollama or API keys required
(spec §9 steps 1-3, the shippable mock/CI core). Validates:
  1. The loop (router → planner → executor → critic) produces a trajectory
  2. The §3 run-unit + reproducibility header serialize to JSONL
  3. The deterministic scorers grade it downstream FROM the JSONL
     (proving scoring never re-invokes the model)
  4. A per-dimension scorecard, not a blended number

For a real run, swap ScriptedAdapter → OllamaAdapter and MockToolRegistry →
a real vector store; the loop and scorers are unchanged.

Usage:
    python scripts/example_agent_run.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from adapters.scripted import ScriptedAdapter  # noqa: E402
from agent.loop import run_agent  # noqa: E402
from agent.tools import build_mock_registry  # noqa: E402
from eval import trajectory  # noqa: E402

# A scripted "good" trajectory answering the Vogtle capacity question.
SCRIPT = [
    "ROUTE: retrieve\nQUERY: Vogtle nuclear plant planned capacity",
    'TOOL: vector_search\nARGS: {"query": "Vogtle planned capacity", "k": 3}',
    'TOOL: fetch_article\nARGS: {"id": "sift://energy/vogtle-capacity"}',
    "TOOL: none",
    "ANSWER: The Vogtle plant's planned capacity is 2200 MW across two reactors.\n"
    "CITATIONS: sift://energy/vogtle-capacity#0",
    "VERDICT: pass\nREASONS: answer is grounded in the fetched article",
]

RUBRIC = {
    "scenario_id": "set5-vogtle-001",
    "allowed_tools": ["vector_search", "fetch_article", "list_by_category"],
    "required_tools": ["vector_search"],
    "precedence": [["vector_search", "fetch_article"], ["fetch_article", "synthesize"]],
    "step_budget": 8,
    "gold_article_ids": ["sift://energy/vogtle-capacity"],
}


def main() -> int:
    registry = build_mock_registry()
    adapter = ScriptedAdapter(SCRIPT, model_id="scripted-v1")

    print("=== Run the agent ===")
    run = run_agent(adapter, registry, "What is the planned capacity of Vogtle?",
                    clock=lambda: "2026-07-10T00:00:00Z")
    print(f"  terminated: {run.terminated}")
    print(f"  final_answer: {run.final_answer!r}")
    print(f"  citations: {run.citations}")
    print(f"  trajectory: {len(run.trajectory)} steps "
          f"({[s['role'] for s in run.trajectory]})")
    assert run.terminated == "answered"
    assert run.citations == ["sift://energy/vogtle-capacity#0"]

    # Serialize the §3 run-unit + header to JSONL.
    unit = trajectory.run_unit(
        run, scenario_id=RUBRIC["scenario_id"], sample=0,
        model_id=adapter.model_id, tool_registry_hash=registry.registry_hash(),
        agent_version="agent@demo", n_samples=1,
    )
    out = ROOT / "results" / "demo_trajectory_mock.jsonl"
    header = trajectory.trajectory_header(
        agent_version="agent@demo", tool_registry_hash=registry.registry_hash(),
        model_id=adapter.model_id, repo_root=ROOT,
    )
    trajectory.write_runs(out, header, [unit])
    print(f"\n=== Wrote {out} ===")

    # Re-score DOWNSTREAM from the JSONL — proves scoring is decoupled from the run.
    rows = [json.loads(line) for line in out.read_text().splitlines() if line.strip()]
    reloaded = rows[1]  # rows[0] is the header
    card = trajectory.score_trajectory(reloaded, RUBRIC)
    print("\n=== Scorecard (from JSONL, no model re-run) ===")
    for dim, val in card.items():
        if dim in ("scenario_id", "sample"):
            continue
        print(f"  {dim}: {val}")

    assert card["tool_selection"]["process"] == 1.0, card["tool_selection"]
    assert card["tool_selection"]["legality"] == 1.0
    assert card["arg_validity"]["arg_validity"] == 1.0
    assert card["citation_ids"]["gold_covered"] is True
    assert card["error_recovery"]["recovered"] is True
    assert card["step_efficiency"]["report_only"] is True

    print(f"\nEnd-to-end agent demo OK. Output at {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
