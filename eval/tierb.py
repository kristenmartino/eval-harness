"""
Tier-B judged scoring (spec §6) — the pointwise-judge dimensions the key-free
Tier-A gate cannot compute: answer-correctness (vital nugget recall + precision)
and citation faithfulness. A CLI accepts a live judge; CI uses a keyword-based
smoke adapter. No scheduled nightly workflow is configured here.

`run_tierb` replays the SAME committed golden cassettes as Tier A (so the agent
trajectory is deterministic and never re-invokes a live model — spec §3
invariant), then drives ONLY the judge with a live (or key-free KeywordJudge)
adapter over authored nuggets and the generated answer's sentence/clause units.
Faithfulness uses retrieved source spans named by the actual citations.
The committed responses are scripted fixtures, not live model measurements.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from adapters.replay import ReplayAdapter
from agent.loop import run_agent
from eval.adversarial import build_scenario_registry
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
    registry = build_scenario_registry(sc)
    trh = registry.registry_hash()
    cassette = json.loads((golden_dir / sc["cassette"]).read_text())
    adapter = ReplayAdapter(cassette, sc["model_id"], tool_registry_hash=trh)
    return run_agent(adapter, registry, sc["question"],
                     system_prompt=sc.get("system_prompt", ""), clock=_clock)


def score_run(run, rubric, judge):
    """Judge an answer against gold context and its cited, retrieved text.

    A citation resolves only when its exact id#span has nonempty text in the
    evidence captured by the agent. Gold reference text cannot fill that gap.
    """
    answer = run.final_answer or ""
    ac = answer_correctness(judge, answer, rubric["nuggets"],
                            reference_context=rubric.get("reference_context"))
    sources = {f"{e['id']}#{e['span']}": e["text"] for e in run.evidence
               if e.get("text", "").strip()}
    invalid = sorted(set(run.citations) - sources.keys())
    citations_valid = bool(run.citations) and not invalid
    context = "\n".join(sources[c] for c in dict.fromkeys(run.citations) if c in sources)
    faith = citation_faithfulness(judge, ac["claims"], context)
    if not citations_valid:
        faith["faithfulness"] = 0.0
    return {
        "recall": ac["recall"],
        "vital_recall": ac["vital_recall"],
        "precision": ac["precision"],
        "f1": ac["f1"],
        "correct": bool(ac["correct"] and citations_valid and ac["claims"]
                        and faith["supported"] == len(ac["claims"])),
        "faithfulness": faith["faithfulness"],
        "claims": ac["claims"],
        "citations_valid": citations_valid,
        "invalid_citations": invalid,
        "precision_detail": ac["precision_detail"],
        "faithfulness_detail": faith,
    }


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
        per_scenario.append({"scenario_id": sc["scenario_id"],
                             **score_run(run, rubric, judge)})

    scorecard = _aggregate(per_scenario)
    failures = _check(scorecard, thresholds)
    if not per_scenario:
        failures.append(("n_scenarios", 0, 1))
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
        # Descriptive interval over fixtures; not model-performance evidence.
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
    lines = ["Tier-B judged scorecard (replayed agent fixtures)"]
    for dim in ("mean_recall", "mean_f1", "mean_faithfulness", "correct_rate"):
        if dim in result.scorecard:
            lines.append(f"  {dim:20s} {result.scorecard[dim]}")
    ci = result.scorecard.get("recall_ci")
    if ci:
        lines.append(f"  recall_ci            [{ci['lo']}, {ci['hi']}] (n={ci['n']}; fixture interval)")
    lines.append(f"  → {'PASS' if result.passed else 'FAIL'} "
                 f"({result.scorecard.get('n_scenarios', 0)} judged scenarios)")
    return "\n".join(lines)
