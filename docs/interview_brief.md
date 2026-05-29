# Interview Brief — Eval Harness Talk Tracks

**Purpose:** Rehearsable 60–90 second answers for behavioral and technical-fit interviews. Each story maps to a real decision documented in the spec / noodle / CHANGELOG.
**Audience:** Internal — for delivery practice, not publication.
**Format:** Setup → Tradeoff → Decision → Outcome → Principle.

---

## Story 1 — "Tell me about a hard methodology decision you made"

### Topic: Judge contamination on the summarization task

**Setup.** I was building an eval that uses Claude Sonnet to judge a pairwise summarization comparison — Sonnet looks at two summaries and picks the better one. Standard LLM-as-judge setup. But Sonnet was also one of the models I was evaluating. Sonnet was judging its own outputs.

**Tradeoff.** Self-preference bias in LLM judges is well-documented — Zheng et al. 2023 showed judges score their own outputs measurably higher. Either I find a way to control for it, or Sonnet's eval result is unfalsifiable.

**Decision.** Cross-vendor judge architecture. Sonnet 4.6 judges non-Anthropic-containing pairs only — 21 of 36 pairs at 9 models. GPT-4o judges Anthropic-containing pairs — the other 15. To make sure the two judges are calibrated to a common scale, a 50-pair overlap subset is judged by both, and I report inter-judge Cohen's kappa. If kappa drops below 0.6 the methodology limitation is flagged on the leaderboard.

**Outcome.** Added GPT-4o to the model lineup as a result, which had the side effect of making it a candidate too. Total marginal cost: $0.16 against a $99 budget.

**Principle.** *When an eval has an unfalsifiable result, fix the methodology, not the result.*

---

## Story 2 — "Tell me about a time you scoped something back"

### Topic: Deferring the A/B framing decision until data lands

**Setup.** Two ways to frame this project: (A) a leaderboard with a companion writeup recapping results, or (B) a hybrid-routing decision framework where the leaderboard is the worked example underneath. Different deliverables, different audiences, different effort levels at the synthesis phase.

**Tradeoff.** Framing B is more valuable for a strategy-leaning audience — it positions me as a systems thinker, not just an engineer running an experiment. But it requires having a defensible point of view on routing rules, which I don't have until I see the data. Framing A is the safer execution path but lower ceiling.

**Decision.** Defer the choice until I had data from Task A. The first ~80% of effort is identical between A and B — the framing only matters at the synthesis phase. If the data shows clean tier boundaries (e.g., 8B models tie Haiku within noise on Task A), framing B writes itself. If the data is messy, framing A is the honest call.

**Outcome.** Same engineering work proceeds either way. The framing decision becomes data-driven instead of vibes-driven.

**Principle.** *When commitment cost is asymmetric, defer until decision-relevant data arrives.*

---

## Story 3 — "Tell me about a tradeoff you navigated"

### Topic: 70B Llama in the lineup but excluded from deployment view

**Setup.** Llama 3.1 70B Q4 was originally one of the open-weight models I was testing. Pre-flight analysis showed throughput on my DGX Spark hardware would be ~10–15 tok/s — roughly 20 seconds per article. At Sift's daily volume of thousands of articles, that's not deployable.

**Tradeoff.** If I report 70B's quality in the leaderboard like the other models, the comparison implies it's a viable production choice. If I drop 70B entirely, I lose a useful "what's the upper bound of open-weight on this workload" reference point.

**Decision.** Split the leaderboard into two tiers. "Deployment-feasible" — the 7B, 8B, 14B models that can actually serve production traffic on DGX Spark. "Quality-ceiling reference" — 70B reports in quality tables but is explicitly excluded from cost-per-token deployment view, with the throughput math shown. Reader can see what 70B *could* do as a quality bar; the routing recommendation stays honest.

**Outcome.** Drove a v0.2 spec change. Also propagated into the rubric for what gets recommended for actual hybrid routing.

**Principle.** *Honest framing beats clean comparison when the data points don't support the latter.*

---

## Story 4 — "What would make you abandon this project?"

### Topic: Pre-stated kill criteria

**Setup.** Most projects don't pre-state what disconfirming evidence would look like. They drift indefinitely on sunk cost.

**My four kill criteria for Phase 1:**
1. Set 4 RAG questions unauthorable past evening 8 at any scope → scope back to n=30 main + n=10 adversarial, document as a v1 limitation.
2. Three or more open-weight models fail Task C JSON validity badly enough to be uninterpretable → drop schema-adherence as a primary metric; report it as a side note.
3. Human-vs-judge agreement <0.6 on the calibration check → flag as methodology limitation; the load-bearing pairwise preference claim weakens.
4. Sift's category distribution forces dropping more than 50% of categories → rescope Task A entirely (the stratified-sampling claim doesn't survive).

**Outcome.** Project boundaries are explicit before execution. If any trigger fires, I have a pre-committed response.

**Principle.** *Kill criteria pre-state what disconfirming evidence looks like. They prevent sunk-cost commitment.*

---

## Story 5 — "How did you stress-test your own work?"

### Topic: The v0.1 → v0.2 critique cycle

**Setup.** I drafted a v0.1 spec for the eval harness. Then, before writing any code, I asked for honest critique — pretending I was an interviewer who'd find every methodology hole in my own draft.

**What surfaced.** Eleven items, ranked by leverage. The top four:
- Sonnet judging Sonnet (the contamination story above)
- Held-out 20% with no locking mechanism — "I'll just not look at it" doesn't survive scrutiny
- Llama 70B's silent infeasibility on Task A's volume
- Task C's binary schema gate conflated two distinct capabilities (JSON-adherence vs entity extraction)

**Decision.** Applied nine to v0.2 directly. Three deferred to v0.3 because they're post-data-collection decisions (statistical power, error analysis taxonomy, dual-view cost framing). Each accept/defer was logged with reasoning.

**Outcome.** The critique cycle took ~half a day. The methodology bugs it caught would have cost weeks if discovered after the eval ran.

**Principle.** *Premortem before postmortem. The critique cycle is the cheap part; finding methodology bugs after running the eval is expensive.*

---

## Story 6 — "How do you balance rigor with shipping?"

### Topic: Held-out lock, but the harness builds anyway

**Setup.** The held-out 20% can't be touched during prompt iteration. But the harness needs end-to-end testing before the real eval runs. How do I validate the pipeline without burning held-out items?

**Decision.** Built a `MockAdapter` that returns canned responses, plus sample datasets (a dev sample and a held-out fixture) that live outside the real dev and holdout sets. The full harness pipeline (adapter → task → runner → JSONL → metric aggregation) runs end-to-end on the sample. 47 unit tests cover the load-bearing math (Bradley-Terry MM, macro-F1 with length guards, accuracy with parse failures, JSONL with line-number errors), judge verdict parsing (a malformed verdict is flagged, never silently scored as a tie), and the runner's held-out gate. And the held-out discipline isn't policy — it's enforced in code: the runner refuses a held-out set without `--include-held-out` and verifies it against a committed SHA-256 lock before scoring.

**Outcome.** Pipeline verified before any real model runs. When Sift's corpus is pulled and the real eval begins, the harness is known-correct.

**Principle.** *Rigor isn't slowness — it's instrumentation that lets you ship faster downstream.*

---

## Delivery notes

- **Start with the setup**, not the principle. The story makes the principle land.
- **Numbers anchor.** "n=200 detects ~10pp at p<0.05" is sharper than "I considered statistical power."
- **Quote the v0.1 critique line** ("the line that separates 'I built an eval' from 'I built a defensible eval'") — it's memorable.
- **If asked for code:** point to the [methodology page](methodology.md), not the repo. The methodology is the harder thing; the code is the easier thing.
- **If asked about findings:** be honest — Phase 1 not yet run. The story is about the *design* decisions, not the results. That's the right story for a methodology-leaning role.

---

## What to lead with by audience

- **AI research / methodology role** → Story 1 (judge contamination) — direct ML rigor signal.
- **Consulting / strategy role** → Story 2 (deferring framing) — option-preservation, decision-framework thinking.
- **Product / systems role** → Story 3 (tier split) — systems thinking + honest framing of constraints.
- **Risk / compliance role** → Story 4 (kill criteria) — pre-stated abandonment conditions.
- **Behavioral round, no specifics** → Story 5 (critique cycle) — self-awareness + premortem discipline.
