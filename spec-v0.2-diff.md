# Spec v0.2 — Diff against v0.1

**Source:** `eval-harness-spec.md` (v0.1, Draft 2026-05-06)
**Status:** Proposed edits, pending Kristen review
**Scope:** 8 accepted critique items from `noodle-on-this-cryptic-knuth.md` (Lens 1) + framing-independent items from Lens 3. Framing-dependent items (#5 dual-cost, #7 power bump, #10 error-analysis budget) deferred until post-Task-A signal.

Each entry shows current text, proposed replacement, and one-line "why" tied to the critique number.

---

## Edit 1 — §2 Task B: judge design (Critiques #1, #2)

### Current (lines 27–31)

> **Metric:** LLM-as-judge pairwise preference (Sonnet 4.6 as judge, blind comparison vs. reference Haiku output) + length compliance + factuality flag (judge marks summaries that contain claims not in source).

### Proposed

> **Metric:** LLM-as-judge round-robin pairwise preference using a Bradley–Terry-style ranking, computed across all model pairs (8 models × 28 unordered pairs × N items). To control for self-preference bias, judges are assigned cross-vendor: Sonnet 4.6 judges all non-Anthropic outputs; GPT-4o judges Anthropic outputs (Haiku and Sonnet). Plus length compliance + factuality flag (judge marks summaries that contain claims not in source). Judge-cost budget: ~5,600 judge calls at chosen N — see §8 rate-limit budget.

**Why:** Critique #1 — Sonnet judging Sonnet is unfalsifiable. Critique #2 — pairwise-vs-Haiku-anchor can't evaluate Haiku itself.

---

## Edit 2 — §3 Models: 70B classification + selection rationale (Critiques #3, minor)

### Current (lines 49–61)

> **Open-weight (local, via Ollama on DGX Spark):**
> - Llama 3.1 8B Instruct (baseline open-weight)
> - Llama 3.1 70B Instruct (if DGX can run Q4 quantized at acceptable latency — confirm in pre-flight)
> - Qwen 2.5 7B Instruct
> - Qwen 2.5 14B Instruct
> - DeepSeek V2 Lite (or V3 if quantized fits)
>
> **Closed-weight reference (via API):**
> - Claude Haiku 4.5 (current Sift production model — the bar to beat)
> - Claude Sonnet 4.6 (upper bound; also serves as judge for Tasks B and D)
> - GPT-4o-mini (cross-vendor reference point)
>
> **Excluded for v1:** anything requiring multi-GPU model parallelism beyond DGX Spark capacity; anything not available via Ollama. Document the exclusion rather than hand-waving it.

### Proposed

> **Selection criteria:** license compatibility (commercial-use permitted), Ollama availability, parameter-size coverage (7B / 14B / 70B classes), vendor diversity (Meta / Alibaba / DeepSeek). Mistral, Phi-4, and Gemma 3 are noted candidates for v2 — excluded from v1 to keep the model list tractable.
>
> **Open-weight, deployment-feasible (target tier — eligible for routing recommendations):**
> - Llama 3.1 8B Instruct
> - Qwen 2.5 7B Instruct
> - Qwen 2.5 14B Instruct
> - DeepSeek V2 Lite (or V3 if quantized fits)
>
> **Open-weight, quality-ceiling reference (NOT deployment-feasible on DGX Spark for Task A's volume — see §8 timing benchmark):**
> - Llama 3.1 70B Instruct (Q4 quantized) — included as a quality upper bound; reported in quality tables but excluded from cost-per-token deployment view because expected throughput (~10–15 tok/s on DGX Spark) gives ~20 sec/article, infeasible at Sift's daily volume.
>
> **Closed-weight reference (via API):**
> - Claude Haiku 4.5 (current Sift production model — the bar to beat)
> - Claude Sonnet 4.6 (upper bound; also serves as judge — see §2 Task B for cross-judge logic)
> - GPT-4o (cross-vendor judge for Anthropic outputs and reference candidate)
> - GPT-4o-mini (cross-vendor reference point)
>
> **Excluded for v1:** anything requiring multi-GPU model parallelism beyond DGX Spark capacity; anything not available via Ollama. Mistral, Phi-4, Gemma 3 deferred to v2 (see selection criteria).

**Why:** Critique #3 — 70B's Task A throughput is silently infeasible; honest split between deployable and quality-ceiling preserves credibility. Plus model-selection rationale closes a loose end. Note: GPT-4o promoted from out-of-list to needed model so it can act as the cross-vendor judge for Anthropic outputs.

---

## Edit 3 — §2 Task C: split metrics (Critique #6)

### Current (lines 33–37)

> **Output format:** JSON matching a fixed schema. Schema-validity check is a hard gate before scoring.
> **Metric:** entity F1 (vs. human-curated ground truth) + JSON validity rate.

### Proposed

> **Output format:** JSON matching a fixed schema (Pydantic-validated).
> **Metrics (two, reported separately):**
> 1. **JSON validity rate** — fraction of outputs that parse and conform to the schema. Measures schema-adherence capability.
> 2. **Entity F1, conditional on validity** — F1 against human-curated ground truth, computed only on schema-valid outputs. Measures extraction quality independent of JSON-following capability.
> Outputs that fail schema validation are excluded from F1 computation but counted against the validity rate. This separation prevents conflating "weak at JSON" with "weak at extraction."

**Why:** Critique #6 — binary gate conflates two distinct capabilities; you can't tell whether a model is bad at extraction or just bad at JSON.

---

## Edit 4 — §4 Held-out discipline: locking mechanism (Critique #4)

### Current (line 81)

> **Held-out discipline:** 20% of each set is held out for final scoring only — never seen during prompt iteration. This is the line that separates "I built an eval" from "I built a defensible eval."

### Proposed

> **Held-out discipline:** 20% of each set is held out for final scoring only — never seen during prompt iteration. This is the line that separates "I built an eval" from "I built a defensible eval."
>
> **Locking mechanism (so the discipline is verifiable, not vibes-based):**
> - Held-out items are stored in `data/holdout/` separately from `data/dev/`.
> - Before any prompt iteration begins, a `holdout.sha256` file is committed to git, containing SHA-256 hashes of every held-out file.
> - Prompt-iteration scripts have read access only to `data/dev/`. The `data/holdout/` directory is gated by a `--include-held-out` flag on the runner, default false.
> - Final-scoring runs commit the result alongside the unchanged `holdout.sha256`. Any reviewer can verify (a) the hash hasn't changed since pre-iteration commit, (b) the runner invocation logs include `--include-held-out` only on the final run.
> - **Rule:** if a held-out file's hash changes during the iteration phase, that set is treated as compromised and replaced with a fresh sample.

**Why:** Critique #4 — "I'll just not look at it" doesn't survive interview scrutiny. Verifiable locking does.

---

## Edit 5 — §5 Prompting: per-model chat templates (Critique #8)

### Current (line 87)

> **Prompting:** one shared prompt template per task, used identically across all models. No model-specific tuning. If a model performs poorly because the prompt format isn't ideal for it, that's a real production cost — surface it rather than paper over it.

### Proposed

> **Prompting:** one shared prompt *content* template per task — identical instructions and few-shot examples (if any) across all models, no model-specific prompt engineering. However, each model's prompt content is wrapped in its own tokenizer's official chat template (Llama 3 chat format, Qwen `<|im_start|>` format, DeepSeek format, Anthropic Messages API, OpenAI ChatML, etc.). This is a tokenizer-level concern, not prompt engineering: applying a foreign chat template to a model measurably degrades performance for reasons unrelated to the underlying capability under test. Content stays uniform; framing respects each model's training. If a model still performs poorly with its native template, that's a real capability gap — surface it rather than paper over it.

**Why:** Critique #8 — "shared template" applied raw to a Qwen tokenizer that expects `<|im_start|>` will systematically harm Qwen for the wrong reason. Distinguishing "prompt content" from "chat template" preserves fair comparison.

---

## Edit 6 — §5 add: contamination + safety smoke test (Critiques #11, minor)

### Insert after current §5 "LLM-as-judge controls" paragraph (around line 97)

> **Pretraining contamination acknowledgement:** Sift's source articles are public news. Most of the open-weight and closed-weight models under test were pretrained on web crawls that likely include the original article text (though not Sift's downstream summaries, categorizations, or extractions). This does not invalidate the eval — the tasks measure pipeline behavior on those articles, not novel-text generalization — but it is acknowledged in the methodology page.
>
> **Safety smoke test (50 prompts):** in addition to the four primary tasks, every model is run on a 50-prompt safety battery: 20 prompts probing toxicity calibration (offensive-but-benign-context content), 15 PII handling (articles containing names/addresses where extraction should redact or refuse), 15 refusal calibration (legitimate journalistic queries that should *not* be refused). Outputs are graded by a fixed rubric and a single judge (Sonnet 4.6, no cross-judging since this is regression-detection not preference). Results reported as a side panel on the leaderboard, not a primary metric. Purpose: detect deployment-blocking regressions if Sift were to swap Haiku for an open-weight model.

**Why:** Critique #11 (safety) and minor contamination acknowledgement. The safety battery is cheap (50 prompts × 8 models = 400 generations) and high-credibility — a sharp reviewer flags its absence.

---

## Edit 7 — §8 Pre-flight: expanded checklist (Lens 3 items)

### Current (lines 127–133)

> - [ ] Confirm Llama 3.1 70B Q4 fits on DGX Spark and inference latency is tolerable
> - [ ] Pull Sift's category distribution to verify stratified sampling is feasible (need ≥20 articles per category for stable per-category metrics)
> - [ ] Decide annotation tooling for Set 3 (Label Studio? Just JSONL + VS Code?)
> - [ ] Set up Ollama model versions and pin them — leaderboard is meaningless if model weights drift mid-eval

### Proposed

> **Hardware / model feasibility:**
> - [ ] Run a 10-article timing benchmark for Llama 3.1 70B Q4 on DGX Spark; record tok/s, p50, p95. **Decision rule:** if sustained throughput <8 tok/s, 70B stays as quality-ceiling reference only (confirms §3 split).
>
> **Dataset feasibility:**
> - [ ] Pull Sift's category distribution. **Decision rule:** any category with <20 articles is dropped from the eval (not upsampled — upsampling biases macro-F1).
>
> **Tooling:**
> - [ ] Annotation tooling: JSONL + VS Code + a `validate_annotations.py` script (schema check + summary stats). Label Studio overhead not justified at n=100.
>
> **Reproducibility (must be in place before any run):**
> - [ ] Pin model weights by Hugging Face SHA, *not* Ollama tags (Ollama re-tags on rebuild). Document Ollama version separately.
> - [ ] Pin judge model snapshot IDs (Sonnet 4.6 dated snapshot, GPT-4o dated snapshot).
> - [ ] Commit `holdout.sha256` containing pre-iteration hashes of all held-out files (see §4).
>
> **Annotation discipline (must be in place before annotating item 1):**
> - [ ] Write Set 3 entity-annotation rubric (entity types, boundary rules, ambiguity tie-breakers). Dual-annotate ≥5 calibration items to surface rubric ambiguity.
> - [ ] Write Set 4 RAG question-authoring rubric (question shape, gold-article identification rule, answer-grounding standard).
> - [ ] Define failure-mode taxonomy for qualitative error tagging (deferred to post-Task-A scoping per noodle Lens 1 #10, but vocabulary should exist before tagging starts).
>
> **Judge-cost budget (do this before kicking off Task B):**
> - [ ] Estimate API rate-limit consumption: Task B alone = ~4,800 generation calls + ~5,600 judge calls. With Sonnet-tier rate limits, judge phase is several hours of wall-clock. Plan for it in the run schedule.

**Why:** Lens 3 reality check — §8 had the right items but missed the lock mechanism, judge pinning, annotation rubric pre-write, rate-limit budget, and concrete decision rules.

---

## Edit 8 — §6 Deliverable: define reproducibility (minor)

### Current (lines 102–111)

> **Public leaderboard at `evals.kristenmartino.ai`** with:
> - Per-task quality table (accuracy / F1 / preference rate, with confidence intervals)
> - Latency table (p50, p95)
> - Cost table ($/1K tokens, with methodology footnote)
> - Pareto frontier chart: quality vs. cost, quality vs. latency
> - Methodology page (this spec, refined post-execution)
> - Repo link with full code, prompts, eval data (where licensable), and reproducibility instructions

### Proposed

> **Public leaderboard at `evals.kristenmartino.ai`** with:
> - Per-task quality table (accuracy / F1 / preference rate, with confidence intervals)
> - Latency table (p50, p95)
> - Cost table ($/1K tokens, with methodology footnote)
> - Pareto frontier chart: quality vs. cost, quality vs. latency
> - Safety-smoke-test side panel (see §5)
> - Methodology page (this spec, refined post-execution)
> - Repo link with full code, prompts, eval data (where licensable), and reproducibility instructions
>
> **Reproducibility scope:** the leaderboard ships with sufficient artifacts that a reader can re-run any cell. Concretely: (a) HF model SHAs for every open-weight model, (b) Ollama version, (c) judge model snapshot IDs, (d) prompt content hashes, (e) dataset file hashes, (f) harness git SHA, (g) hardware ID (DGX Spark CPU/GPU spec). Each results JSONL embeds a header line capturing all of these so any cell traces to exact code state.

**Why:** §6 mentioned reproducibility but didn't define it. Concrete pin list closes the gap. Plus safety-panel reference for consistency.

---

## Edit 9 — §9 Effort: bump annotation estimate (Critique #9)

### Current (lines 138–143)

> - Pre-flight + dataset construction: 4–6 evenings
> - Harness implementation (model adapters, eval runners, metric calculators): 5–8 evenings
> - Annotation work (Sets 1 sub-validation, 3, 4): 4–6 evenings
> - Run + analyze + leaderboard build: 3–5 evenings
>
> Total: ~16–25 evenings of focused work. Calls Phase 1 at ~1.5 calendar months at a sustainable pace alongside Snowflake/dbt sprint completion and Deloitte application work.

### Proposed

> - Pre-flight + dataset construction (incl. holdout-lock commit): 4–6 evenings
> - Harness implementation (model adapters, eval runners, metric calculators, leaderboard scaffold): 5–8 evenings
> - Annotation work — *revised upward*: 8–12 evenings
>     - Set 1 sub-validation (n=100 categorization): ~2 evenings
>     - Set 3 entity annotation (n=100 at ~5 min/article): ~3 evenings
>     - Set 4 RAG question authoring with gold-article identification (n=50): ~3–4 evenings (each Q requires reading multiple articles)
>     - Annotation-rubric writing + calibration round: ~1–2 evenings before the above starts
> - Run + analyze + leaderboard build: 3–5 evenings
> - Safety smoke-test design and run: ~1 evening
>
> Total: ~21–32 evenings of focused work. Calls Phase 1 at ~2 calendar months at a sustainable pace alongside Snowflake/dbt sprint completion and Deloitte application work. **Risk:** annotation phase is the most likely to slip — track weekly.

**Why:** Critique #9 — original estimate was based on aggregate evening-count; line-item breakdown shows annotation is heavier than v0.1 admitted. Honest schedule prevents cascading slip.

---

## Summary of changes

| # | Section | Critique | Type |
|---|---|---|---|
| 1 | §2 Task B | #1, #2 | Methodology fix |
| 2 | §3 Models | #3, model-selection minor | Restructure |
| 3 | §2 Task C | #6 | Metric split |
| 4 | §4 Held-out | #4 | New mechanism |
| 5 | §5 Prompting | #8 | Clarification |
| 6 | §5 (insert) | #11, contamination minor | New paragraph |
| 7 | §8 Pre-flight | Lens 3 | Expanded checklist |
| 8 | §6 Deliverable | reproducibility minor | Definition added |
| 9 | §9 Effort | #9 | Estimate bump |

**Items deferred to v0.3 (post-Task-A signal):**
- Critique #5 — dual-view cost (matters more for B framing)
- Critique #7 — n=200 → n=400 for Task B (only matters for final claims)
- Critique #10 — formal error-analysis budget allocation (much heavier under B framing)

---

## How to apply

If you accept all 9 edits as-is, I can apply them to `eval-harness-spec.md` in one pass and bump the version header to `v0.2`. If you want to push back on any individual edit, list the numbers and what you'd change.
