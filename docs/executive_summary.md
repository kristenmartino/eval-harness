# Open-Weight vs Frontier LLMs on Sift's Production Pipeline

**A hybrid-routing case study.**

---

## What it is

A public, reproducible eval comparing nine LLMs — five open-weight on local DGX Spark hardware (Llama 3.1, Qwen 2.5, DeepSeek), four closed-weight via API (Claude Haiku/Sonnet, GPT-4o/4o-mini) — across four real production tasks from **Sift**, a news-article processing pipeline I built and run.

The four tasks are the actual stages Sift runs in production: article categorization, summarization for the UI, structured entity extraction, and grounded RAG with citations. Same prompts the production system uses, same data, same eval criteria.

## Why it's different from public benchmarks

Public LLM leaderboards (MMLU, HumanEval, etc.) measure capability in the abstract. They don't tell me whether a specific open-weight model can replace Claude Haiku in *my* pipeline without quality regression — which is the only question that matters when deciding whether to switch.

This eval answers that question directly, on real production workload, with a methodology defensible enough to publish.

## Methodology decisions worth flagging

The credibility of a leaderboard is mostly in its methodology, not its numbers. Five design decisions:

1. **Cross-vendor LLM-as-judge architecture** for the pairwise summarization task. Sonnet 4.6 judges non-Anthropic-containing pairs; GPT-4o judges Anthropic-containing pairs. Plus a 50-pair overlap subset judged by both, with Cohen's kappa reported. Eliminates the self-preference bias that would otherwise make Sonnet's score unfalsifiable.
2. **Hardware-amortized cost methodology** for open-weight models — comparable to closed-weight API token pricing. State all assumptions; pin the DGX Spark capex and Florida residential power rate.
3. **Enforced held-out lock** — the runner refuses held-out data without an explicit `--include-held-out` flag and verifies it against a committed SHA-256 manifest before scoring, so test data can't leak into prompt iteration and any reviewer can confirm the hash never moved.
4. **Per-task tier split.** Llama 3.1 70B Q4 is reported as a quality ceiling but excluded from the deployment cost view, because expected DGX Spark throughput (~10–15 tok/s, ~20s/article) is infeasible at Sift's daily volume. Honest framing > clean comparison.
5. **A v0.2 spec critique round before any code was written.** Eleven methodology items surfaced (judge contamination, scoring conflation in the extraction task, sample-size power, contamination acknowledgement). Nine applied directly to the spec; three deferred to v0.3 as post-data-collection decisions.

## What it outputs

- **A public leaderboard** at `evals.kristenmartino.ai` with per-task quality, latency, and cost on Pareto frontiers.
- **A methodology page** documenting every design decision and its rationale.
- **A companion writeup** positioning findings as a hybrid-routing decision framework — when to use a local open-weight model, when to use frontier, how to detect when escalation is needed.
- **A reusable harness skeleton** — adapter/task abstractions designed so the same evaluation framework can be repointed at GridPulse, Tarazu, or other ML products by swapping the dataset and task modules.

## Current status

- **Spec v0.2** locked, with cross-judge calibration overlap and adversarial subset for grounding-hygiene measurement.
- **Harness infrastructure** end-to-end: adapter Protocol (Ollama + Anthropic + OpenAI), task modules (categorization + summarization), runner with reproducibility headers + resumability + enforced held-out gate + transient retry/backoff + CLI, Bradley-Terry pairwise ranking, 58 tests passing (math, judge parsing, runner reproducibility + held-out gate + retry/backoff), GitHub Actions CI.
- **Pre-flight scripts** complete (5 stdlib-only): timing benchmark, length-stratified sampler, category distribution check, API cost estimator, annotation validator.
- **Annotation rubrics** drafted for entity extraction (with second-annotator IAA protocol) and RAG question authoring (including a 20-item adversarial subset).
- **Projected v0.2 API spend:** $99.96 total, ~3 hours judge wall-clock.

Phase 1 execution begins once the Sift corpus is pulled and the 70B timing benchmark runs on DGX Spark.

---

**Repo:** [github.com/kristenmartino/eval-harness](https://github.com/kristenmartino/eval-harness)
**Methodology page:** [methodology.md](methodology.md)
**Spec v0.2:** [eval-harness-spec.md](../eval-harness-spec.md)
**Owner:** Kristen Martino
