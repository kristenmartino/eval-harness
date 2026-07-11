"""
Tier-A regression gate (spec §6) — the key-free per-dimension gate.

Runs the REAL agent loop over the committed golden cassettes (ReplayAdapter),
scores the DETERMINISTIC dimensions + the injection guardrail, and gates
per-dimension over a committed thresholds.json — a CONJUNCTION, never a blended
average. step-efficiency is report-only and never gates.

A prompt / tool-schema edit changes the request keys → ReplayMiss → the gate
fails with a 're-record' instruction, so a prompt regression cannot silently
pass. (The judged dimensions — nugget recall, citation faithfulness — need a
live judge and belong to the deferred Tier-B nightly, not this gate.)
"""

import json
from dataclasses import dataclass
from pathlib import Path

from adapters.replay import ReplayAdapter, ReplayMiss
from agent.loop import run_agent
from agent.tools import build_mock_registry
from eval.adversarial import score_injection, with_injected_fault
from eval.trajectory import run_unit, score_trajectory


def _clock():
    return "2026-07-10T00:00:00Z"


@dataclass
class GateResult:
    passed: bool
    scorecard: dict          # dimension → aggregate value
    thresholds: dict         # dimension → committed threshold
    failures: list           # [(dimension, value, threshold, kind)]
    per_scenario: list       # one scorecard dict per scenario
    replay_misses: list      # scenario_ids that hit a ReplayMiss


def _load_scenarios(golden_dir):
    rows = []
    with (golden_dir / "scenarios.jsonl").open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def run_gate(golden_dir) -> GateResult:
    golden_dir = Path(golden_dir)
    thresholds = json.loads((golden_dir / "thresholds.json").read_text())
    scenarios = _load_scenarios(golden_dir)

    per_scenario = []
    injection_scores = []
    replay_misses = []

    for sc in scenarios:
        registry = build_mock_registry()
        trh = registry.registry_hash()
        if "fault" in sc:
            fspec = sc["fault"]
            registry = with_injected_fault(registry, fspec["tool"], fspec["fault"],
                                           fspec.get("fail_times"))
        cassette = json.loads((golden_dir / sc["cassette"]).read_text())
        adapter = ReplayAdapter(cassette, sc["model_id"], tool_registry_hash=trh)

        try:
            run = run_agent(adapter, registry, sc["question"],
                            system_prompt=sc.get("system_prompt", ""), clock=_clock)
        except ReplayMiss:
            replay_misses.append(sc["scenario_id"])
            continue

        unit = run_unit(run, scenario_id=sc["scenario_id"], sample=0,
                        model_id=sc["model_id"], tool_registry_hash=trh,
                        agent_version="agent@gate")
        card = score_trajectory(unit, sc["rubric"])
        if sc["kind"] == "adversarial":
            iv = score_injection(run, sc["attacker_goal"])
            card["injection"] = iv
            injection_scores.append(iv)
        per_scenario.append(card)

    scorecard = _aggregate(per_scenario, injection_scores)
    failures = _check(scorecard, thresholds, replay_misses)
    return GateResult(
        passed=(not failures and not replay_misses),
        scorecard=scorecard,
        thresholds=thresholds,
        failures=failures,
        per_scenario=per_scenario,
        replay_misses=replay_misses,
    )


def _aggregate(cards, injection_scores):
    """Aggregate per-dimension across scenarios. Binary dims → the *minimum*
    (any failing scenario drops the whole dimension); graded dims → the mean."""
    if not cards:
        return {}
    arg = min(c["arg_validity"]["arg_validity"] for c in cards)
    recovered = [c["error_recovery"]["recovered"] for c in cards]
    error_recovery = sum(1 for r in recovered if r) / len(recovered)
    process = sum(c["tool_selection"]["process"] for c in cards) / len(cards)
    gold_cards = [c for c in cards if c["citation_ids"]["cited_ids"] is not None
                  and c["citation_ids"]["missing_gold"] is not None]
    covered = [c["citation_ids"]["gold_covered"] for c in gold_cards]
    gold_covered = (sum(1 for x in covered if x) / len(covered)) if covered else 1.0
    if injection_scores:
        held = sum(1 for s in injection_scores if s["held"]) / len(injection_scores)
    else:
        held = 1.0
    return {
        "arg_validity": round(arg, 4),
        "error_recovery": round(error_recovery, 4),
        "injection_held": round(held, 4),
        "citation_gold_covered": round(gold_covered, 4),
        "tool_selection_process": round(process, 4),
        "n_scenarios": len(cards),
    }


def _check(scorecard, thresholds, replay_misses):
    failures = []
    for dim, thr in thresholds.get("must_pass", {}).items():
        val = scorecard.get(dim, 0.0)
        if val < thr:
            failures.append((dim, val, thr, "must_pass"))
    for dim, thr in thresholds.get("graded", {}).items():
        val = scorecard.get(dim, 0.0)
        if val < thr:
            failures.append((dim, val, thr, "graded"))
    return failures


def format_report(result: GateResult) -> str:
    """A scorecard-style report — 'eval as a dashboard, not a number' (§6)."""
    lines = ["Tier-A trajectory gate — scorecard"]
    for dim, val in result.scorecard.items():
        if dim == "n_scenarios":
            continue
        thr = {**result.thresholds.get("must_pass", {}),
               **result.thresholds.get("graded", {})}.get(dim)
        mark = ""
        if thr is not None:
            mark = "  PASS" if val >= thr else f"  FAIL (< {thr})"
        lines.append(f"  {dim:26s} {val}{mark}")
    if result.replay_misses:
        lines.append(f"  REPLAY MISS on: {result.replay_misses} — re-record "
                     f"(python scripts/build_golden.py)")
    lines.append(f"  → {'PASS' if result.passed else 'FAIL'} "
                 f"({result.scorecard.get('n_scenarios', 0)} scenarios)")
    return "\n".join(lines)
