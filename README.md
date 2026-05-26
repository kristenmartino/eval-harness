# Open-Weight vs Frontier LLMs on a Production Workload

A reproducible eval harness comparing 9 LLMs across 4 real production tasks from **Sift**, a news-article processing pipeline. Methodology designed for hybrid-routing decisions; harness designed for portability across ML products.

**Why this exists.** Public LLM benchmarks (MMLU, HumanEval, BIG-bench) measure capability in the abstract. They don't tell you whether Llama 3.1 8B can replace Claude Haiku in *your* production pipeline. This eval does.

→ **[Methodology](docs/methodology.md)** · **[Executive Summary](docs/executive_summary.md)** · **[Spec (v0.2)](eval-harness-spec.md)** · **[Changelog](CHANGELOG.md)**

---

## What's interesting

- **Cross-vendor LLM-as-judge architecture** for Task B pairwise summarization. Sonnet 4.6 judges non-Anthropic-containing pairs; GPT-4o judges Anthropic-containing pairs. 50-pair overlap subset judged by both, inter-judge Cohen's kappa reported. Eliminates the self-preference bias that would make Sonnet's score unfalsifiable. *([details](docs/methodology.md#3-tasks))*
- **Hardware-amortized cost methodology** for local models — comparable to closed-weight API token pricing. All assumptions stated; pricing pinned in code.
- **20% held-out set hashed pre-iteration** and committed to git before any prompt tuning. Verifiable, not vibes-based: any reviewer can confirm the hash hasn't changed.
- **Per-task tier split.** Llama 3.1 70B Q4 is reported as a quality ceiling but excluded from deployment cost view, because expected DGX Spark throughput (~10–15 tok/s, ~20s/article) is infeasible at Sift's daily volume. Honest framing > clean comparison.
- **9 spec critiques applied to v0.2 before any code was written.** The premortem is documented in [`spec-v0.2-diff.md`](spec-v0.2-diff.md) — methodology bugs caught at the cheap end of the lifecycle.

## What's in the repo

**Spec & methodology** — the design layer
- [`eval-harness-spec.md`](eval-harness-spec.md) — current spec (v0.2)
- [`docs/methodology.md`](docs/methodology.md) — publication-quality methodology page
- [`docs/executive_summary.md`](docs/executive_summary.md) — 1-page summary
- [`spec-v0.2-diff.md`](spec-v0.2-diff.md) — the v0.1→v0.2 critique cycle
- [`CHANGELOG.md`](CHANGELOG.md) — dated decision log

**Harness skeleton** (Python 3.9+, stdlib only)
- `adapters/` — model adapter Protocol + concrete impls (Ollama, Anthropic, OpenAI, Mock for testing)
- `tasks/` — per-task modules (prompt + parser + scorer; categorization + summarization complete)
- `eval/` — runner with JSONL run units, judge module with cross-vendor selection, Bradley-Terry MM ranking
- `utils.py` — shared helpers
- `tests/` — 25 unit tests on the load-bearing math (BT correctness, macro-F1 with imbalance, JSONL parsing)

**Pre-flight scripts** (`scripts/`, all stdlib-only)
- `preflight_70b_timing.py` — 70B throughput benchmark on DGX Spark
- `sample_stratified_articles.py` — corpus → length-stratified articles
- `category_distribution_check.py` — category distribution + feasibility decision
- `judge_cost_budget.py` — API spend estimator ($99.96 projected for v0.2)
- `validate_annotations.py` — Set 3 + Set 4 schema validator

**Annotation rubrics** (`rubrics/`)
- `set3_entity_annotation.md` — entity rubric with second-annotator IAA protocol
- `set4_rag_question_authoring.md` — RAG question rubric (incl. n=20 adversarial subset)

## Quickstart (no API keys, no Ollama needed)

```bash
python scripts/example_run.py            # Task A end-to-end via MockAdapter
python scripts/example_task_b.py         # Task B with cross-vendor judging + BT ranking
python -m unittest discover tests        # 25 tests
```

For a real run with Ollama + closed-weight APIs, see the pre-flight scripts and the [methodology page](docs/methodology.md).

## Design

The **adapter Protocol** is the seam: swap Ollama for Anthropic for OpenAI without touching tasks or runner. **Tasks are self-contained modules** — adding a task = adding a module. The runner writes one JSONL row per `(model, task, item, sample)` with a reproducibility header carrying model snapshot, dataset hash, harness git SHA, and host. **All metrics computed downstream** from the JSONL — re-running scoring never requires re-running the model.

This abstraction is what makes the harness portable across other ML products (the stretch outcome documented in spec §1).

## Status

Phase 1 in progress. Engineering roughly halfway:

- [x] Spec v0.2 with cross-judge calibration overlap and adversarial subset
- [x] Harness skeleton — 2 of 4 task modules (A, B), all 4 adapter types, runner + judge + BT
- [x] 25 tests passing on load-bearing math
- [x] Pre-flight scripts (5, stdlib-only)
- [x] Annotation rubrics (Set 3 + Set 4 incl. adversarial)
- [x] Methodology page + executive summary + interview brief
- [ ] Tasks C (extraction) + D (RAG)
- [ ] Sift corpus pull + category distribution check
- [ ] 70B timing benchmark on DGX Spark
- [ ] Set 3 entity annotation + IAA calibration (10 articles, 2 annotators)
- [ ] Set 4 RAG main authoring (n=50) + adversarial (n=20)
- [ ] Full eval runs + leaderboard build
- [ ] Companion writeup

## License

MIT — see [LICENSE](LICENSE).

## Author

Kristen Martino. Comments and critique welcome — open an issue or reach out directly.
