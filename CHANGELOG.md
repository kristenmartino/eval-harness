# Changelog

## 2026-05-26

### Fixed (pre-publish review pass)
- **Factuality flag now actually collected.** Spec, methodology, and CHANGELOG promised a Task B factuality flag rate. Earlier judge prompt only requested an overall verdict — implementation gap closed: `eval/judge.py` `PAIRWISE_PROMPT` now requests `VERDICT` / `FACTUALITY_A` / `FACTUALITY_B` as three labeled lines; `parse_verdict()` extracts all three via regex; `JudgeVerdict` carries `factuality_a` + `factuality_b` fields. `example_task_b.py` updated to demonstrate factuality flag aggregation per-model.
- **Self-preference bias citation corrected** in `docs/methodology.md`. Was Zheng et al. 2023 (MT-Bench paper, doesn't directly establish self-preference). Now [Panickssery, Bowman & Feng 2024](https://arxiv.org/abs/2404.13076) — paper explicitly titled "LLM Evaluators Recognize and Favor Their Own Generations" — with Stureborg et al. 2024 as supporting reference and DOI link for Hunter 2004.
- **Kill criteria pre-stated explicitly** in new spec §10. Five triggers (Set 4 stall, Task C JSON validity collapse, judge-agreement low, category-distribution collapse, cross-judge kappa low) each mapped to a specific rescope or methodology-limitation response. Resolves the inconsistency where interview brief story #4 listed criteria not in the spec.

## 2026-05-07

### Added (interview-prep + narrative)
- **`docs/methodology.md`** promoted from skeleton to publication-quality. ~2,000 words covering models, tasks, datasets, sampling, cost methodology, reproducibility, contamination, limitations, open questions. Execution-derived numbers marked `[TK]` until Phase 1 runs.
- **`docs/executive_summary.md`** — 1-page exec summary designed for recruiter follow-up emails, LinkedIn DMs, "what are you working on" answers. Hiring-manager-readable, no ML jargon.
- **`docs/interview_brief.md`** — internal talk-track doc with 6 STAR-format stories (judge contamination, framing deferral, tier split, kill criteria, critique cycle, mock-adapter-for-shipping). Each maps to a documented decision. Audience-specific delivery guidance at the bottom.

### Added (afternoon — Task B vertical slice)
- **Anthropic adapter** (`adapters/anthropic.py`) — Messages API, stdlib-only, snapshot-pin in model_name.
- **OpenAI adapter** (`adapters/openai.py`) — Chat Completions API, stdlib-only, supports `seed` for best-effort reproducibility.
- **Task B summarization module** (`tasks/summarization.py`) — prompt template, length compliance, parse-failure handling.
- **Judge module** (`eval/judge.py`) — pairwise prompt, cross-vendor judge selection (Sonnet for non-Anthropic pairs, GPT-4o for Anthropic-containing pairs), constrained verdict parsing with TIE fallback.
- **Bradley-Terry ranking** (`eval/bradley_terry.py`) — MM algorithm (Hunter 2004), normalized geometric mean = 1, ties count as 0.5 wins each side.
- **Task B demo** (`scripts/example_task_b.py`) — full pipeline end-to-end with HeuristicJudge; asserts cross-vendor routing math (C(4,2) with 2 Anthropic → 5 GPT-4o pairs + 1 Sonnet pair) and BT normalization.
- **Tests** (`tests/`) — 25 tests across `test_bradley_terry.py` (7) and `test_utils.py` (18). Covers BT correctness on transitive ranking, ties, geometric-mean normalization; utils on percentile edge cases, macro-F1 with imbalance + missing labels, accuracy with None predictions, JSONL parsing with line-number errors.
- **`pyproject.toml`** — Python ≥3.9 pinned, zero runtime deps (justification documented inline).

### Added (morning — harness skeleton)
- **Harness skeleton.** `adapters/` (Protocol + Completion dataclass + Ollama + Mock), `tasks/` (Task Protocol + CategorizationTask), `eval/runner.py` (JSONL run units, reproducibility header, resumability), `utils.py` (shared helpers). `scripts/example_run.py` demonstrates the full pipeline end-to-end via MockAdapter and asserts contracts.
- **README** at root (project overview, quickstart, status checklist).
- **CHANGELOG** (this file).
- **`docs/methodology.md`** draft outline (section headers + caveat stubs for every metric; numbers TK).
- **Cross-judge calibration overlap** added to spec §2 Task B: 50-pair subset judged by BOTH Sonnet and GPT-4o to verify they're calibrated to each other (Cohen's kappa target ≥0.6). Closes a methodology hole identified in senior-seat review. ~$0.16 marginal cost.
- **Sample dataset** at `data/sample_categorization.jsonl` (5 items for demo + smoke tests).

### Changed
- **Set 4 adversarial** bumped 10 → 20 questions (binomial CI considerations for ~20pp refusal-rate discrimination).
- **Set 3 calibration** bumped 5 → 10 articles, framed as real second-annotator IAA (not solo intra-annotator).
- **Effort estimate** bumped from 21–32 → 26–34 evenings (~2 → 2.5 calendar months).
- **Cost budget** updated to $99.80 (was $98.54) including adversarial set + cross-judge overlap.

### Decisions (Sift-specific TODOs resolved in rubrics)
- Brand names: annotate parent company only ("Apple" yes, "iPhone" no).
- Financial instruments: annotate underlying entity ("$TSLA" → Tesla); skip benchmarks (S&P 500); for ETFs annotate the issuer.
- Time-anchoring: explicit dates required in Temporal questions (Set 4).
- Topic strategy: stratified random sample across category distribution.
- Authoring tooling: JSONL + VS Code + `validate_annotations.py`.
- Calibration source: drawn from outside Set 1's eval pool.
- Judge optimization: keep Sonnet 4.6 across the board (cost savings <$25 not worth the methodology asymmetry).

### Known tech debt
- `percentile` and JSONL-loading logic duplicated between pre-flight scripts and `utils.py`. Pre-flight scripts intentionally stdlib-only and self-contained; consolidation deferred to avoid churning working code.

## 2026-05-06

### Added
- **v0.2 spec** (`eval-harness-spec.md`). 9 critique edits applied from `noodle-on-this-cryptic-knuth.md`:
  1. Task B cross-vendor judging (Sonnet ↔ GPT-4o split by Anthropic-or-not pairs)
  2. §3 model tier split (deployment-feasible vs quality-ceiling)
  3. Task C metric split (validity rate + F1-conditional-on-validity)
  4. §4 held-out lock mechanism (SHA-256 commit pre-iteration)
  5. §5 per-model chat template (content shared, template native)
  6. §5 contamination acknowledgement + safety smoke test (n=50)
  7. §8 expanded pre-flight checklist (judge pinning, rate-limit budget, rubric pre-writes)
  8. §6 reproducibility scope defined (HF SHAs, snapshot IDs, hashes, hardware)
  9. §9 annotation effort revised upward
- **§8 timing benchmark:** 10 → 25 articles, length-stratified across p10/p25/p50/p75/p90.
- **Pre-flight scripts** (5 stdlib-only, all smoke-tested):
  - `preflight_70b_timing.py`
  - `sample_stratified_articles.py`
  - `category_distribution_check.py`
  - `judge_cost_budget.py`
  - `validate_annotations.py`
- **Rubrics** drafted for Set 3 entity annotation and Set 4 RAG question authoring (incl. adversarial subset).
- **Memory** entries saved at `~/.claude/projects/-Users-rootk-eval-harness/memory/`.

### Decisions
- **A vs B framing deferred** until post-Task-A signal — both paths share ~80% of effort; data should drive the framing choice.
- **Spec v0.2 accepted "all 9 as-is"** with one math correction (8→9 models, 28→36 pairs after GPT-4o added for cross-judging).

## Earlier

- v0.1 spec drafted (initial scoping by Kristen).
