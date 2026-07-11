"""
Tier-B judged scoring (spec §6) — the pointwise-judge dimensions the key-free
Tier-A gate cannot compute: answer-correctness (vital nugget recall + precision)
and citation faithfulness. These need a live model, so they run in the deferred
keyed nightly, NOT per-PR.

`run_tierb` replays the SAME committed golden cassettes as Tier A (so the agent
trajectory is deterministic and never re-invokes a live model — spec §3
invariant), then drives ONLY the judge with a live (or key-free KeywordJudge)
adapter over the scenario's authored nuggets/claims. Report per-scenario scores,
an aggregate, and a seeded bootstrap CI (wide at this n by design).
"""

import json
from dataclasses import dataclass
from pathlib import Path

from adapters.replay import ReplayAdapter
from agent.loop import run_agent
from agent.tools import build_mock_registry
from eval.adversarial import with_injected_fault
from eval.stats import answer_correctness, citation_faithfulness, seeded_bootstrap_ci


def _clock():
    return "2026-07-10T00:00:00Z"


@dataclass
class TierBResult:
    passed: bool
    scorecard: dict          # aggregate judged dimensions (+ CIs)
    thresholds: dict
    failures: list
    per_scenario: list


def _load_scenarios(golden_dir):
    rows = []
    with (golden_dir / "scenarios.jsonl").open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _replay_run(sc, golden_dir):
    """Reproduce the scenario's agent run from its committed cassette (Tier A's
    trajectory), so Tier B judges the exact same final answer."""
    registry = build_mock_registry()
    trh = registry.registry_hash()
    if "fault" in sc:
        f = sc["fault"]
        registry = with_injected_fault(registry, f["tool"], f["fault"], f.get("fail_times"))
    cassette = json.loads((golden_dir / sc["cassette"]).read_text())
    adapter = ReplayAdapter(cassette, sc["model_id"], tool_registry_hash=trh)
    return run_agent(adapter, registry, sc["question"],
                     system_prompt=sc.get("system_prompt", ""), clock=_clock)


def run_tierb(golden_dir, judge) -> TierBResult:
    """Score the judged dimensions over the golden with `judge` (any
    ModelAdapter — a live LLM for the real nightly, or KeywordJudge key-free)."""
    golden_dir = Path(golden_dir)
    thresholds = {}
    tpath = golden_dir / "tierb_thresholds.json"
    if tpath.exists():
        thresholds = json.loads(tpath.read_text())

    per_scenario = []
    for sc in _load_scenarios(golden_dir):
        rubric = sc.get("rubric", {})
        nuggets = rubric.get("nuggets")
        if not nuggets:
            continue  # only scenarios with authored nuggets are judged
        run = _replay_run(sc, golden_dir)
        answer = run.final_answer or ""
        claims = rubric.get("claims")
        reference = rubric.get("reference_context")

        ac = answer_correctness(judge, answer, nuggets, claims=claims,
                                reference_context=reference)
        faith = None
        if claims and reference is not None:
            faith = citation_faithfulness(judge, claims, reference)
        per_scenario.append({
            "scenario_id": sc["scenario_id"],
            "recall": ac["recall"],
            "vital_recall": ac["vital_recall"],
            "precision": ac["precision"],
            "f1": ac["f1"],
            "correct": ac["correct"],
            "faithfulness": faith["faithfulness"] if faith else None,
        })

    scorecard = _aggregate(per_scenario)
    failures = _check(scorecard, thresholds)
    return TierBResult(
        passed=(not failures),
        scorecard=scorecard,
        thresholds=thresholds,
        failures=failures,
        per_scenario=per_scenario,
    )


def _aggregate(per_scenario):
    if not per_scenario:
        return {"n_scenarios": 0}
    recalls = [p["recall"] for p in per_scenario]
    f1s = [p["f1"] for p in per_scenario]
    faiths = [p["faithfulness"] for p in per_scenario if p["faithfulness"] is not None]
    correct = [1.0 if p["correct"] else 0.0 for p in per_scenario]
    out = {
        "n_scenarios": len(per_scenario),
        "mean_recall": round(sum(recalls) / len(recalls), 4),
        "mean_f1": round(sum(f1s) / len(f1s), 4),
        "correct_rate": round(sum(correct) / len(correct), 4),
        # Seeded bootstrap CI on mean recall — wide at this n; report honestly.
        "recall_ci": seeded_bootstrap_ci(recalls),
    }
    if faiths:
        out["mean_faithfulness"] = round(sum(faiths) / len(faiths), 4)
    return out


def _check(scorecard, thresholds):
    failures = []
    for dim, thr in thresholds.get("must_pass", {}).items():
        val = scorecard.get(dim, 0.0)
        if val < thr:
            failures.append((dim, val, thr))
    return failures


def format_report(result: TierBResult) -> str:
    lines = ["Tier-B judged scorecard (keyed nightly)"]
    for dim in ("mean_recall", "mean_f1", "mean_faithfulness", "correct_rate"):
        if dim in result.scorecard:
            lines.append(f"  {dim:20s} {result.scorecard[dim]}")
    ci = result.scorecard.get("recall_ci")
    if ci:
        lines.append(f"  recall_ci            [{ci['lo']}, {ci['hi']}] (n={ci['n']}, wide by design)")
    lines.append(f"  → {'PASS' if result.passed else 'FAIL'} "
                 f"({result.scorecard.get('n_scenarios', 0)} judged scenarios)")
    return "\n".join(lines)
