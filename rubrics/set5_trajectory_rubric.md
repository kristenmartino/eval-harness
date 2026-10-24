# Set 5 — Trajectory Rubric (agent eval)

**Status:** Draft v0.1 — schema + the deterministic scorers are implemented
(`eval/trajectory.py`, `agent/`); scenario authoring is ongoing.
**Scope:** per-scenario rubric data that freezes author judgment at authoring
time so the tool-selection / order / state scorers are pure functions at
runtime (spec v0.3 §4). One rubric object per trajectory scenario.

---

## Why a rubric, not a rigid path

A flat "expected-tool set" cannot express *order* or *state*, which §1/§4
require ("the right tool, in a sensible order, given state"). So the rubric
encodes order as a **partial order** (precedence edges) and state as a small
**state-legality** rule — both checkable deterministically from the trajectory.
The irreducibly subjective "was this the smartest path" residue is a *separate*,
explicitly judge-scored row (Tier B), never mixed into the deterministic score.

To honor the single-IC constraint, precedence/state rules are authored as a few
reusable **templates** tagged onto scenarios, not 70 bespoke graphs.

## Rubric schema

```json
{
  "scenario_id": "set5-vogtle-001",
  "question": "What is the planned capacity of the Vogtle nuclear plant?",
  "allowed_tools": ["vector_search", "fetch_article", "list_by_category"],
  "required_tools": ["vector_search"],
  "precedence": [
    ["vector_search", "fetch_article"],
    ["fetch_article", "synthesize"]
  ],
  "step_budget": 8,
  "gold_article_ids": ["sift://energy/vogtle-capacity"]
}
```

| Field | Feeds scorer | Meaning |
|---|---|---|
| `allowed_tools` | tool-selection · **legality** (hard gate) | every called tool must be in this set, else legality → 0 |
| `required_tools` | tool-selection · **coverage** | all must appear in the trajectory |
| `precedence` | tool-selection · **precedence** | `[before, after]` edges; `synthesize` is the pseudo-action for answer synthesis. Fraction of satisfied edges (vacuous when an endpoint is absent) |
| `step_budget` | **step-efficiency** (report-only) | denominator disclosed inline; never gates |
| `gold_article_ids` | **answer-correctness** · deterministic half | the answer's `citations[]` (form `article_id#span`) must cover these ids — separates "right source" from "right answer", zero judge calls |

State-legality is template-derived (not a rubric field): `fetch_article`
requires a prior retrieval; `synthesize` requires evidence unless the route was
`direct`.

## Worked scenario

`set5-vogtle-001` (a factoid) is exercised end-to-end, key-free, in
`scripts/example_agent_run.py`, and its scorers are unit-tested in
`tests/test_trajectory.py`. A "good" trajectory
(`vector_search → fetch_article → synthesize → pass`) scores
`legality=coverage=precedence=state_legality=1.0`, `arg_validity=1.0`,
`gold_covered=True`.

## Tier-B scoring and pending live evaluation

Tier B is implemented in `eval/tierb.py` and `eval/stats.py`. Author vital/optional
nuggets and reference context. Precision and faithfulness score sentences/clauses
from the generated answer, not a static rubric claim list. Faithfulness resolves
the answer's exact citations against evidence text retained by the agent.

Full support earns 1, partial support 0.5, and unsupported or malformed judgments
0. Every unit stays in the denominator. The strict correctness gate requires
full vital recall, full precision, and resolvable citations supporting every
answer unit. Empty context/answer units or missing/invalid citations fail.

The committed adversarial scenario includes a document payload, and all three
agent responses are scripted. CI uses the keyword judge as a smoke adapter;
model reliability, injection susceptibility, and judge calibration require
separate live evaluation over the authored production-corpus scenarios.
