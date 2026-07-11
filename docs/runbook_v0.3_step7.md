# Runbook — v0.3 step 7: from the mock core to a live trajectory-eval run

Goal: produce the **first live agent-trajectory-eval result** over real Sift
data — for one agent version on one real model backbone, a per-dimension
scorecard (Tier A) plus judged scores + `pass^k` + injection ASR (Tier B),
fully reproducible and provenance-bound.

The **mock/CI core (spec §9 steps 1-6) is done, tested, and green**: the agent
loop, the deterministic trajectory scorers, the adversarial guardrail suite, the
Tier-A replay gate, and the Tier-B judged path all run **key-free**. Step 7 swaps
the mock corpus, the mock tools, and the mock/scripted model for real ones
**behind the same seams** — nothing in the loop or the scorers changes.

What the harness already provides vs. what only **you** can supply:

| Provided (tested, key-free) | You supply (step 7) |
| --- | --- |
| `ToolRegistry` Protocol (`agent/tools.py`) — swap mock → real | **Sift stable article-ID format** (Prerequisite-0) |
| Agent loop (`agent/loop.py`), trajectory writer + deterministic scorers (`eval/trajectory.py`) | **Real corpus** — articles `{id, category, title, body}` from your Sift pull |
| Adversarial harness + locks (`eval/adversarial.py`, `lock_adversarial.py`) | **A real vector store** behind the Protocol (a stated dep — see step 2) |
| Tier-A gate + cassette replay (`eval/gate.py`, `adapters/replay.py`) | **Set 4 authored** — n=50 main + n=20 adversarial, with gold ids + reference answers + nuggets/claims + attacker goals |
| Tier-B judged path + `KeywordJudge` (`eval/tierb.py`) — swap → real cross-vendor judge | **A real model backbone** (Ollama on DGX / API) + **judge keys** |
| Stats: `pass^k`, McNemar, paired bootstrap, kappa (`eval/stats.py`) | **The OK to publish** |

> **Prerequisite-0 gates everything.** The Sift stable article-ID appears in the
> citation schema (`article_id#span`), the adversarial lock, and Set-4's gold
> ids at once (spec §2). The mock path uses a synthetic `sift://<category>/<slug>`
> scheme so nothing is blocked; **step 0 replaces it with the real ID.** Resolve
> it first — steps 3, 4, and 7 all depend on it.

---

## 0. Resolve the article-ID format (Prerequisite-0)

Confirm the stable id Sift uses for an article (from your first SQL query), and
adopt it as the canonical id everywhere the mock uses `sift://…`: the corpus rows
(step 1), Set-4 `gold_article_ids` and citations (step 3). Keep it opaque and
stable — a result's citation must trace to exactly one article forever.

## 1. Pull the corpus (your data step)

Produce the retrieval universe — a JSONL of `{"id", "category", "title",
"body"}` from your Sift export (the real IDs from step 0). This is the corpus the
tools search; it is **not** the question set (that's Set 4, step 3). The committed
`agent.tools.DEMO_CORPUS` (5 rows) is a format reference only — the repo has no
Sift access.

## 2. Build the real vector store behind the `ToolRegistry` Protocol

Implement a `SiftToolRegistry` exposing the same three tools over the real corpus
— `vector_search` (embedding index), `fetch_article`, `list_by_category` — with
the **same MCP-shaped `inputSchema`** as `build_mock_registry()`. If the schemas
are byte-identical, `registry_hash()` is unchanged and existing baselines/locks
still apply; if they differ, that is a **MAJOR change** → re-baseline
(`python scripts/lock_registry.py --update`, reviewed) and re-record cassettes
(step 6).

> **The one admitted dependency.** A real embedding index needs a vector library
> (e.g. `pgvector` / `sqlite-vss` / `faiss`). The harness is otherwise stdlib-only;
> per spec §2 this is a **stated v0.3 decision**, isolated behind the Protocol —
> the loop, scorers, and CI core stay dep-free. State it in the PR, don't import
> it silently.

## 3. Author Set 4 — the golden trajectory inputs (~6-7 evenings)

Per `rubrics/set4_rag_question_authoring.md` + `rubrics/set5_trajectory_rubric.md`,
write **n=50 main + n=20 adversarial** scenarios. Each carries:

- `question`, `gold_article_ids` (real ids), and a reference answer;
- a **rubric**: `allowed_tools`, `required_tools`, `precedence` edges, `step_budget`;
- **`nuggets`** (vital/okay) + **`claims`** + `reference_context` — the Tier-B judged inputs;
- for adversarial scenarios, an **`attacker_goal`** `{injected_tool,
  injected_arg_pattern, planted_canary, target_assertion}` and the injected
  document.

**Split the main 50 into DEV-20 / TEST-30** (§9, G9): DEV-20 is the *only* tuning
surface; TEST-30 is the flagship, reported. Emit `scenarios.jsonl` + thresholds
in the `data/set5/` shape `scripts/build_golden.py` already writes.

## 4. Lock the held-out slices — BEFORE any prompt iteration

```bash
python scripts/lock_adversarial.py --dataset data/set5/adversarial_20.jsonl
python scripts/lock_holdout.py --dataset data/set5/test_30.jsonl --out data/set5/test30.sha256
git add data/set5/*.sha256 && git commit -m "lock Set-4 adversarial + TEST-30 manifests"
```

Locks the **hashes, not the data** (§5, premortem #5). Default/CI runs then read
only DEV-20; tuning can't leak into the reported set.

## 5. Wire the real model into the loop, iterate on DEV-20 only

The loop is model-agnostic — pass a real adapter:

```python
from adapters.ollama import OllamaAdapter
from agent.loop import run_agent
run = run_agent(OllamaAdapter("<tag>", "<hf_sha>", host="http://<dgx>:11434"),
                registry, question)   # registry = your SiftToolRegistry
```

Iterate the role prompts (`agent/loop.py`) on **DEV-20** until a real model
reliably emits the `ROUTE:` / `TOOL:` / `ANSWER:` directives (the parser is
tolerant of markdown/whitespace, like `eval/judge.py`). **Freeze the prompts**
before touching TEST-30 or the adversarial set.

## 6. Re-record the Tier-A cassettes against the real model + registry

Adapt `scripts/build_golden.py` to record against `RecordingAdapter(OllamaAdapter(...))`
and your `SiftToolRegistry`, then commit the cassettes + `registry.sha256`.
Now the **per-PR Tier-A gate replays real trajectories, key-free** — and any later
prompt/schema edit trips a `ReplayMiss` until you deliberately re-record
(`build_golden.py`), so a prompt regression can't land silently.

## 7. Run the live eval

Commit **N samples/scenario at temperature > 0** (§9, premortem #1 — at temp=0
`pass^k` is null). Run the agent over TEST-30 + adversarial-20, writing the §3
trajectory JSONL, then score:

- **Tier A (deterministic):** `python scripts/ci_trajectory_gate.py` — per-dimension
  scorecard (tool-selection, arg-validity, error-recovery, citations⊇gold-id) +
  the injection guardrail (ASR, reported **separately from utility**).
- **Tier B (judged, keyed):** `python scripts/tierb_nightly.py --judge openai
  --judge-model gpt-4o` — nugget recall + citation faithfulness + answer-correctness.
  **Route the judge cross-vendor** (§7): if the agent backbone is a Claude model,
  the judge is GPT-4o, never Claude-judges-Claude.
- **Reliability + version comparison:** report `pass^k` over the N trials; for
  "did my change help?" use `eval.stats.mcnemar_exact` + `paired_delta_ci` on
  identical scenarios vs. the baseline agent version — **not** Bradley-Terry
  (that's the deferred agent×model matrix).

## 8. Report (the public claim — on your sign-off)

Publish the trajectory scorecard + `pass^k` + injection ASR as an artifact (or a
leaderboard row). **Report DEV and TEST columns; the dev−test gap is the
overfitting signal.** This is the only step that makes a public claim — do it
deliberately.

---

## Honesty guardrails baked in

- **Dev/test discipline is enforced by the locks**, not documented — CI reads only DEV-20; TEST-30 + adversarial-20 are hash-locked and refused if mutated.
- **`pass^k` needs temp > 0** with committed N; at temp=0 with pinned seeds every trial is identical and the reliability metric measures nothing.
- **Cross-vendor judge** — never let a Claude agent be graded solely by a Claude judge (§7); and judge-vs-judge agreement is not validity — calibrate against a small human-gold subset before trusting the faithfulness number.
- **Tool-schema changes re-baseline, loudly** — a `registry_hash` move fails `lock_registry` until reviewed + re-recorded; it never silently passes.
- **Tier A is per-PR + key-free; Tier B is keyed + nightly** — the gate you run on every change cannot see live-model drift or §5a injection *susceptibility*; those are "as fresh as the last re-record." Don't oversell the green badge.
- **Every score is recomputable from the trajectory JSONL** — re-scoring never re-invokes the model (§3 invariant).

## Smoke test (plumbing only — no corpus, no model, no keys)

The whole chain already runs green on the committed mock golden, proving the
seams before you plug in real data/model:

```bash
python scripts/example_agent_run.py     # loop → §3 JSONL → deterministic score
python scripts/ci_trajectory_gate.py    # Tier-A per-dimension gate (replay)
python scripts/example_tierb.py         # Tier-B judged path (KeywordJudge, key-free)
python scripts/lock_registry.py         # tool-schema baseline still valid
```
