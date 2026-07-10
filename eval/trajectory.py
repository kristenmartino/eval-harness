"""
Trajectory run-unit writer + the deterministic trajectory scorers (spec §3, §4).

The writer emits one §3 JSONL run-unit per (agent_version, scenario, sample),
extending the v0.2 reproducibility header — same "compute metrics downstream,
never re-run the agent" invariant (eval/runner.py). Re-scoring reads spans from
the JSONL; it never re-invokes the model.

The scorers here are the DETERMINISTIC half of §4: pure functions of the
trajectory + author-frozen rubric data (rubrics/set5), so runtime scoring is
reproducible. The pointwise-judge scorers (answer-correctness recall, citation
faithfulness) live in eval/stats.py + eval/judge.py; this module implements only
the mechanical dimensions and the free deterministic `citations ⊇ gold-id` check.
"""

import json
from pathlib import Path

from eval.runner import _git_sha

# Actions that are not tool calls (router decision, planning, synthesis, critique).
_NON_TOOL_ACTIONS = frozenset({"route", "plan", "synthesize", "verify"})


# --------------------------------------------------------------------------- #
# Run-unit writer
# --------------------------------------------------------------------------- #

def run_unit(agent_run, *, scenario_id, sample, model_id, tool_registry_hash,
             agent_version, n_samples=1, seed=None, trial_temperature=0.0,
             dataset_sha256_prefix=None, parse_status="ok"):
    """Build one §3 run-unit dict from an AgentRun. All reproducibility-header
    fields use the v0.2 names (model_id, dataset_sha256_prefix, harness_git_sha)
    so the trajectory unit is a strict extension of the task run-unit."""
    return {
        # reproducibility header (extends v0.2's)
        "agent_version": agent_version,
        "tool_registry_hash": tool_registry_hash,
        "model_id": model_id,
        "dataset_sha256_prefix": dataset_sha256_prefix,
        "seed": seed,
        "n_samples": n_samples,
        "trial_temperature": trial_temperature,
        # identity
        "scenario_id": scenario_id,
        "sample": sample,
        # trajectory
        "trajectory": agent_run.trajectory,
        # outcome
        "final_answer": agent_run.final_answer,
        "citations": list(agent_run.citations),
        "terminated": agent_run.terminated,
        "parse_status": parse_status,
    }


def trajectory_header(*, agent_version, tool_registry_hash, model_id,
                      repo_root=None, n_samples=1):
    """First-line `_meta` header for a trajectory JSONL — mirrors the runner's
    header discipline so a trajectory file is self-describing and pinned."""
    repo_root = Path(repo_root) if repo_root else Path(".")
    return {
        "_meta": True,
        "kind": "trajectory",
        "agent_version": agent_version,
        "tool_registry_hash": tool_registry_hash,
        "model_id": model_id,
        "n_samples": n_samples,
        "harness_git_sha": _git_sha(repo_root),
    }


def write_runs(path, header, units):
    """Write a header + run-units to JSONL (one object per line)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        f.write(json.dumps(header) + "\n")
        for u in units:
            f.write(json.dumps(u) + "\n")


# --------------------------------------------------------------------------- #
# Deterministic scorers (spec §4)
# --------------------------------------------------------------------------- #

def _tool_calls(trajectory):
    """The ordered list of executor tool-call steps (excludes router/planner/
    synthesize/critic)."""
    return [
        s for s in trajectory
        if s.get("role") == "executor" and s.get("action") not in _NON_TOOL_ACTIONS
    ]


def _action_sequence(trajectory):
    """Ordered action names including the pseudo-action 'synthesize' — the basis
    for precedence checks (a tool must precede synthesize, etc.)."""
    seq = []
    for s in trajectory:
        act = s.get("action")
        if act in ("route", "plan", "verify"):
            continue
        seq.append(act)  # tool names + "synthesize"
    return seq


def score_tool_selection(trajectory, rubric):
    """Layered, deterministic (spec §4): legality (hard gate) × mean(coverage,
    precedence, state-legality). Author judgment is frozen in the rubric, so this
    is a pure function of the trajectory + rubric."""
    allowed = set(rubric.get("allowed_tools", []))
    required = list(rubric.get("required_tools", []))
    precedence = rubric.get("precedence", [])  # list of [before, after]

    calls = _tool_calls(trajectory)
    called = [s["action"] for s in calls]
    called_set = set(called)

    # Legality — every called tool must be allowed. Hard gate.
    illegal = [t for t in called if allowed and t not in allowed]
    legality = 0.0 if illegal else 1.0

    # Coverage — required tools all present (1.0 if none required).
    if not required:
        coverage = 1.0
    else:
        coverage = sum(1 for t in required if t in called_set) / len(required)

    # Precedence — fraction of before→after edges satisfied over the action seq
    # (including 'synthesize'). Vacuous edges (an endpoint absent) count as met.
    seq = _action_sequence(trajectory)
    first_idx = {}
    for i, a in enumerate(seq):
        first_idx.setdefault(a, i)
    if not precedence:
        precedence_score = 1.0
    else:
        met = 0
        for before, after in precedence:
            if before not in first_idx or after not in first_idx:
                met += 1  # vacuously satisfied
            elif first_idx[before] < first_idx[after]:
                met += 1
        precedence_score = met / len(precedence)

    # State-legality — fetch_article needs a prior retrieval (an id source);
    # synthesize needs evidence unless the route was direct. A modest, checkable
    # stand-in for "sensible given state".
    retrieval_seen = False
    state_ok = 0
    state_total = 0
    for a in seq:
        if a in ("vector_search", "list_by_category"):
            retrieval_seen = True
        elif a == "fetch_article":
            state_total += 1
            state_ok += 1 if retrieval_seen else 0
    state_legality = 1.0 if state_total == 0 else state_ok / state_total

    process = legality * (coverage + precedence_score + state_legality) / 3.0
    return {
        "legality": legality,
        "coverage": round(coverage, 4),
        "precedence": round(precedence_score, 4),
        "state_legality": round(state_legality, 4),
        "process": round(process, 4),
        "illegal_tools": sorted(set(illegal)),
    }


def score_arg_validity(trajectory):
    """Fraction of tool-call steps whose args passed schema validation (spec §4;
    §6 must-pass = 100%)."""
    calls = _tool_calls(trajectory)
    if not calls:
        return {"arg_validity": 1.0, "n_calls": 0, "n_invalid": 0}
    invalid = [s for s in calls if s.get("arg_valid") is False]
    return {
        "arg_validity": round((len(calls) - len(invalid)) / len(calls), 4),
        "n_calls": len(calls),
        "n_invalid": len(invalid),
    }


def score_step_efficiency(trajectory, rubric):
    """Report-only (spec §4): step count vs the per-scenario budget, WITH the
    denominator disclosed. Never a gate input."""
    budget = rubric.get("step_budget")
    n_steps = len(trajectory)
    if not budget:
        return {"report_only": True, "n_steps": n_steps, "budget": None, "ratio": None}
    ratio = min(1.0, budget / n_steps) if n_steps else 1.0
    return {
        "report_only": True,
        "n_steps": n_steps,
        "budget": budget,
        "ratio": round(ratio, 4),
        "disclosure": f"{round(ratio, 2)} over {n_steps} steps / budget {budget}",
    }


def score_error_recovery(trajectory, terminated):
    """Did the agent recover from injected faults (retry / fallback) rather than
    crash or stall (spec §4, §5b)? Deterministic from the trajectory: every
    faulted tool step must carry a recovery marker, and the run must terminate
    with an answer."""
    faulted = [s for s in _tool_calls(trajectory) if s.get("faults")]
    if not faulted:
        return {"recovered": True, "n_faults": 0, "applicable": False}
    all_marked = all(s.get("recovery") in ("retry_succeeded", "fallback") for s in faulted)
    recovered = all_marked and terminated == "answered"
    return {
        "recovered": recovered,
        "n_faults": len(faulted),
        "applicable": True,
        "terminated": terminated,
    }


def score_citation_ids(citations, gold_article_ids):
    """Free deterministic check (spec §4): do the answer's citations cover all
    gold supporting article ids? Separates 'right source' from 'right answer'
    with zero judge calls. Citation form is 'article_id#span'."""
    cited_ids = {c.split("#", 1)[0] for c in citations}
    gold = set(gold_article_ids or [])
    missing = sorted(gold - cited_ids)
    return {
        "gold_covered": missing == [],
        "cited_ids": sorted(cited_ids),
        "missing_gold": missing,
    }


def score_trajectory(unit, rubric):
    """Run every deterministic scorer over one run-unit → a per-dimension
    scorecard (spec §6 'eval as a dashboard, not a number'). The judge-mediated
    dimensions (answer-correctness recall, citation faithfulness) are added by
    the Tier-B path; this is the key-free Tier-A scorecard."""
    traj = unit["trajectory"]
    return {
        "scenario_id": unit.get("scenario_id"),
        "sample": unit.get("sample"),
        "tool_selection": score_tool_selection(traj, rubric),
        "arg_validity": score_arg_validity(traj),
        "step_efficiency": score_step_efficiency(traj, rubric),
        "error_recovery": score_error_recovery(traj, unit.get("terminated")),
        "citation_ids": score_citation_ids(unit.get("citations", []),
                                           rubric.get("gold_article_ids", [])),
    }
