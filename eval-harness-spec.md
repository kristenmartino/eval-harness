# Open-Weight Model Eval Harness — Task Spec

**Owner:** Kristen Martino
**Status:** Draft v0.2 — pre-execution scoping (incorporates noodle-doc critique)
**Goal:** A public, reproducible leaderboard comparing open-weight models (run locally on DGX Spark via Ollama) against closed-weight frontier models (via API) on Sift's actual production workload. Output is the foundation for a hybrid-agent refactor of Sift and a cost/latency case study.

---

## 1. Why this exists

Most public LLM leaderboards (MMLU, HumanEval, etc.) test general capability on synthetic benchmarks. They don't tell me whether Llama 3.1 8B can replace Haiku in *my actual production pipeline* without quality regression. This harness fills that gap: same workload, same prompts, same eval criteria, real Sift data. The deliverable is a decision-support tool for model selection — not another benchmark.

**Stretch outcome:** the harness itself becomes reusable across portfolio projects (GridPulse natural-language insights layer, Tarazu reasoning step, GTM Healthcare Intelligence chat).

---

## 2. Tasks under evaluation

Four tasks, each tied to a real Sift pipeline stage. Ground truth construction described in §4.

### Task A — Article categorization
**Workload:** classify each ingested article into one of Sift's existing categories (Tech, Politics, Energy, etc.).
**Why this task:** runs on every article (~thousands/day), so it's the highest-volume layer — biggest cost lever for hybrid routing.
**Output format:** single category label.
**Metric:** accuracy + macro-F1 (categories are imbalanced).

### Task B — Article summarization
**Workload:** generate the 2–3 sentence summary that appears in Sift's UI.
**Why this task:** user-facing quality matters most here; this is the layer where I most expect to keep Claude.
**Output format:** free text, ≤60 words.
**Metric:** LLM-as-judge round-robin pairwise preference using a Bradley–Terry-style ranking, computed across all model pairs (9 models × 36 unordered pairs × N items). To control for self-preference bias, judges are assigned cross-vendor: Sonnet 4.6 judges all non-Anthropic-containing pairs (21 of 36); GPT-4o judges Anthropic-containing pairs (15 of 36). Plus length compliance + factuality flag (judge marks summaries that contain claims not in source). **Cross-judge calibration overlap:** a 50-pair subset (randomly drawn from the Sonnet-judged set) is judged by BOTH Sonnet 4.6 and GPT-4o; report inter-judge Cohen's kappa. If kappa <0.6, flag as methodology limitation. Judge-cost budget: ~7,250 judge calls at chosen N — see §8 rate-limit budget.

### Task C — Structured extraction
**Workload:** extract named entities (people, orgs, locations) and key claims from article body.
**Why this task:** common agentic-pipeline subtask; tests whether open-weight models can hold structured-output schemas.
**Output format:** JSON matching a fixed schema (Pydantic-validated).
**Metrics (two, reported separately):**
1. **JSON validity rate** — fraction of outputs that parse and conform to the schema. Measures schema-adherence capability.
2. **Entity F1, conditional on validity** — F1 against human-curated ground truth, computed only on schema-valid outputs. Measures extraction quality independent of JSON-following capability.

Outputs that fail schema validation are excluded from F1 computation but counted against the validity rate. This separation prevents conflating "weak at JSON" with "weak at extraction."

### Task D — RAG answer generation
**Workload:** given a user question + top-k retrieved Sift articles, generate a grounded answer with citations.
**Why this task:** this is the agentic capability Deloitte and similar roles actually want to see. Closest to "agent doing useful work."
**Output format:** answer text with inline citation indices.
**Metric:** faithfulness (LLM-judge: does every claim trace to a cited source?) + answer relevance + citation precision.

---

## 3. Models under test

**Selection criteria:** license compatibility (commercial-use permitted), Ollama availability, parameter-size coverage (7B / 14B / 70B classes), vendor diversity (Meta / Alibaba / DeepSeek). Mistral, Phi-4, and Gemma 3 are noted candidates for v2 — excluded from v1 to keep the model list tractable.

**Open-weight, deployment-feasible (target tier — eligible for routing recommendations):**
- Llama 3.1 8B Instruct
- Qwen 2.5 7B Instruct
- Qwen 2.5 14B Instruct
- DeepSeek V2 Lite (or V3 if quantized fits)

**Open-weight, quality-ceiling reference (NOT deployment-feasible on DGX Spark for Task A's volume — see §8 timing benchmark):**
- Llama 3.1 70B Instruct (Q4 quantized) — included as a quality upper bound; reported in quality tables but excluded from cost-per-token deployment view because expected throughput (~10–15 tok/s on DGX Spark) gives ~20 sec/article, infeasible at Sift's daily volume.

**Closed-weight reference (via API):**
- Claude Haiku 4.5 (current Sift production model — the bar to beat)
- Claude Sonnet 4.6 (upper bound; also serves as judge — see §2 Task B for cross-judge logic)
- GPT-4o (cross-vendor judge for Anthropic outputs and reference candidate)
- GPT-4o-mini (cross-vendor reference point)

**Excluded for v1:** anything requiring multi-GPU model parallelism beyond DGX Spark capacity; anything not available via Ollama. Mistral, Phi-4, Gemma 3 deferred to v2 (see selection criteria).

---

## 4. Datasets and ground truth

Four datasets, all derived from Sift's existing corpus (this is the differentiator — real production data, not synthetic).

**Set 1 — Categorization eval set (n=500).**
Stratified sample across Sift categories. Ground truth = current Sift categorization, manually re-validated by me on a 100-item subsample to estimate label noise. Report label noise rate alongside accuracy.

**Set 2 — Summarization eval set (n=200).**
Random sample of articles. No reference summary needed — pairwise preference handles this.

**Set 3 — Extraction eval set (n=100).**
Manually annotate entities and key claims. This is the most expensive ground-truth task; n=100 is chosen for tractability. Use a fixed annotation rubric documented in the repo.

**Set 4 — RAG eval set (n=50 main + 20 adversarial).**
- *Main set (n=50)*: Hand-write 50 questions answerable from Sift's corpus. For each, manually identify the gold-standard supporting articles. Cap at 50 because grading RAG quality is labor-intensive.
- *Adversarial subset (n=20)*: Hand-write 20 questions whose answers are NOT in Sift's corpus. Tests refusal/grounding hygiene — does the model abstain when retrieval fails, or hallucinate? Scored on a separate binary refusal metric, not faithfulness — kept apart from the main RAG ranking. Justified at n=20 by per-model binomial CI: n=10 detects only gross failures; n=20 discriminates ~20pp differences in refusal rate at 95% confidence.

**Held-out discipline:** 20% of each set is held out for final scoring only — never seen during prompt iteration. This is the line that separates "I built an eval" from "I built a defensible eval."

**Locking mechanism (so the discipline is verifiable, not vibes-based):**
- Held-out items are stored in `data/holdout/` separately from `data/dev/`.
- Before any prompt iteration begins, a `holdout.sha256` file is committed to git, containing SHA-256 hashes of every held-out file.
- Prompt-iteration scripts have read access only to `data/dev/`. The `data/holdout/` directory is gated by a `--include-held-out` flag on the runner, default false.
- Final-scoring runs commit the result alongside the unchanged `holdout.sha256`. Any reviewer can verify (a) the hash hasn't changed since pre-iteration commit, (b) the runner invocation logs include `--include-held-out` only on the final run.
- **Rule:** if a held-out file's hash changes during the iteration phase, that set is treated as compromised and replaced with a fresh sample.

---

## 5. Methodology

**Prompting:** one shared prompt *content* template per task — identical instructions and few-shot examples (if any) across all models, no model-specific prompt engineering. However, each model's prompt content is wrapped in its own tokenizer's official chat template (Llama 3 chat format, Qwen `<|im_start|>` format, DeepSeek format, Anthropic Messages API, OpenAI ChatML, etc.). This is a tokenizer-level concern, not prompt engineering: applying a foreign chat template to a model measurably degrades performance for reasons unrelated to the underlying capability under test. Content stays uniform; framing respects each model's training. If a model still performs poorly with its native template, that's a real capability gap — surface it rather than paper over it.

**Sampling:** temperature=0 for Tasks A and C (deterministic outputs expected). Temperature=0.7 with N=3 samples for Tasks B and D (generation tasks); report mean + bootstrap 95% CI.

**Latency measurement:** p50 and p95 over the full eval set. For local models, measure cold-start separately from warm inference. For API models, measure end-to-end including network.

**Cost methodology:**
- *API models:* direct token-priced cost. Trivial.
- *Local models:* amortized cost = (hardware capex / 3-year useful life / hours in 3 years) × wall-clock hours used + electricity at FL residential rate × kWh consumed. State all assumptions in a footnote on the leaderboard. This is the methodology line interviewers will probe — get it right and defensible.

**LLM-as-judge controls:** for Tasks B and D, run a 50-item human-vs-judge agreement check on a subsample to validate the judge isn't drifting. Report agreement rate.

**Pretraining contamination acknowledgement:** Sift's source articles are public news. Most of the open-weight and closed-weight models under test were pretrained on web crawls that likely include the original article text (though not Sift's downstream summaries, categorizations, or extractions). This does not invalidate the eval — the tasks measure pipeline behavior on those articles, not novel-text generalization — but it is acknowledged in the methodology page.

**Safety smoke test (50 prompts):** in addition to the four primary tasks, every model is run on a 50-prompt safety battery: 20 prompts probing toxicity calibration (offensive-but-benign-context content), 15 PII handling (articles containing names/addresses where extraction should redact or refuse), 15 refusal calibration (legitimate journalistic queries that should *not* be refused). Outputs are graded by a fixed rubric and a single judge (Sonnet 4.6, no cross-judging since this is regression-detection not preference). Results reported as a side panel on the leaderboard, not a primary metric. Purpose: detect deployment-blocking regressions if Sift were to swap Haiku for an open-weight model.

---

## 6. Deliverable format

**Public leaderboard at `evals.kristenmartino.ai`** with:
- Per-task quality table (accuracy / F1 / preference rate, with confidence intervals)
- Latency table (p50, p95)
- Cost table ($/1K tokens, with methodology footnote)
- Pareto frontier chart: quality vs. cost, quality vs. latency
- Safety-smoke-test side panel (see §5)
- Methodology page (this spec, refined post-execution)
- Repo link with full code, prompts, eval data (where licensable), and reproducibility instructions

**Reproducibility scope:** the leaderboard ships with sufficient artifacts that a reader can re-run any cell. Concretely: (a) HF model SHAs for every open-weight model, (b) Ollama version, (c) judge model snapshot IDs, (d) prompt content hashes, (e) dataset file hashes, (f) harness git SHA, (g) hardware ID (DGX Spark CPU/GPU spec). Each results JSONL embeds a header line capturing all of these so any cell traces to exact code state.

**Companion writeup** (separate artifact, follows execution): "What I learned routing Sift's pipeline across open-weight and frontier models." This becomes the cost/latency case study (Phase 3 of the broader portfolio piece).

---

## 7. Out of scope (v1)

Documenting these explicitly so they don't quietly creep in:
- Fine-tuning or LoRA adaptation of open-weight models
- Multi-turn agentic tasks (single-turn only for v1)
- Tool use / function calling evals
- Non-English content
- Models that don't run on DGX Spark in <30s/article on Task A
- Vendor-specific optimizations (Anthropic prompt caching, OpenAI structured outputs mode, etc.) — keep prompts portable

---

## 8. Pre-flight checks (do these before starting Phase 1)

**Hardware / model feasibility:**
- [ ] Run a 25-article timing benchmark for Llama 3.1 70B Q4 on DGX Spark, length-stratified across Sift's article-length distribution (~5 articles each at the p10/p25/p50/p75/p90 input-length percentiles). Record tok/s, p50, p95, and per-length-bucket median tok/s. **Decision rule:** if median generation throughput <8 tok/s, 70B stays as quality-ceiling reference only (confirms §3 split). Stratification matters more than n: 25 random short articles is worse signal than 25 length-stratified.

**Dataset feasibility:**
- [ ] Pull Sift's category distribution. **Decision rule:** any category with <20 articles is dropped from the eval (not upsampled — upsampling biases macro-F1).

**Tooling:**
- [ ] Annotation tooling: JSONL + VS Code + a `validate_annotations.py` script (schema check + summary stats). Label Studio overhead not justified at n=100.

**Reproducibility (must be in place before any run):**
- [ ] Pin model weights by Hugging Face SHA, *not* Ollama tags (Ollama re-tags on rebuild). Document Ollama version separately.
- [ ] Pin judge model snapshot IDs (Sonnet 4.6 dated snapshot, GPT-4o dated snapshot).
- [ ] Commit `holdout.sha256` containing pre-iteration hashes of all held-out files (see §4).

**Annotation discipline (must be in place before annotating item 1):**
- [ ] Write Set 3 entity-annotation rubric (entity types, boundary rules, ambiguity tie-breakers). Calibrate via dual annotation of 10 articles with a second annotator (real IAA, not solo intra-annotator); compute entity F1 IAA. Target ≥0.85. Calibration articles drawn from outside Set 1's eval pool.
- [ ] Write Set 4 RAG question-authoring rubric (question shape, gold-article identification rule, answer-grounding standard).
- [ ] Define failure-mode taxonomy for qualitative error tagging (deferred to post-Task-A scoping per noodle Lens 1 #10, but vocabulary should exist before tagging starts).

**Judge-cost budget (do this before kicking off Task B):**
- [ ] Estimate API rate-limit consumption: Task B alone = ~5,400 generation calls + ~7,200 judge calls. With Sonnet-tier rate limits, judge phase is several hours of wall-clock. Plan for it in the run schedule.

---

## 9. Estimated effort

- Pre-flight + dataset construction (incl. holdout-lock commit): 4–6 evenings
- Harness implementation (model adapters, eval runners, metric calculators, leaderboard scaffold): 5–8 evenings
- Annotation work — *revised upward*: 13–14 evenings
    - Annotation rubric tuning (Sift-specific TODOs in /rubrics/): ~1 evening
    - Set 1 sub-validation (n=100 categorization): ~2 evenings
    - Set 3 entity annotation (n=100 at ~5 min/article): ~3 evenings
    - Set 3 calibration (10 articles, dual-annotated with second annotator, IAA target ≥0.85): ~1 evening (your time) + ~1 hr (second annotator)
    - Set 4 RAG main authoring (n=50, gold-article identification): ~3–4 evenings
    - Set 4 adversarial subset authoring (n=20): ~3 evenings
- Run + analyze + leaderboard build: 3–5 evenings
- Safety smoke-test design and run: ~1 evening

Total: ~26–34 evenings of focused work. Calls Phase 1 at ~2.5 calendar months at a sustainable pace alongside Snowflake/dbt sprint completion and Deloitte application work. **Risk:** annotation phase (especially Set 4 main + adversarial) is the most likely to slip — track weekly.

---

## 10. Kill criteria and rescope triggers

Pre-stated conditions under which Phase 1 is scoped back or abandoned rather than pushed through on sunk cost.

- **Set 4 RAG main authoring stalls past evening 8** (at any scope) → scope back to n=30 main + n=10 adversarial. Document the rescope as a v1 limitation in the methodology page.
- **≥3 open-weight models fail Task C JSON validity** badly enough that entity F1 is uninterpretable (schema-valid output rate <20%) → drop schema-adherence as a primary metric; report as a side note.
- **Human-vs-judge agreement <0.6** on the LLM-as-judge calibration check (§5) → flag the pairwise preference claim as methodology-limited; headline ranking carries a caveat.
- **Sift's category distribution forces dropping >50% of categories** in the §8 pre-flight check → rescope Task A entirely; the stratified-sampling claim doesn't survive at that drop rate.
- **Cross-judge Cohen's kappa <0.6** on the Task B overlap subset → flag inter-judge calibration as a methodology limitation; report ranking with caveat.

Each trigger maps to a specific, pre-committed response — not "we'll figure it out then." Kill criteria are reviewed at the end of every Phase 1 milestone; if a trigger fires, the rescope happens before the next milestone begins.
