# Methodology

**Status:** First real categorization development agreement baseline published; final held-out and broader model comparisons pending.

**Last updated:** 2026-10-24

This page separates the code that runs today from the proposed model-comparison study. The original designs remain in [spec v0.2](https://github.com/kristenmartino/eval-harness/blob/main/eval-harness-spec.md) and [spec v0.3](https://github.com/kristenmartino/eval-harness/blob/main/eval-harness-spec-v0.3.md).

## First categorization baseline — October 24, 2026

Llama 3.1 8B Instruct Q4_K_M completed 400 real development articles: **79.8% agreement (319/400)** with stored Sift labels, **macro-F1 0.7598**, descriptive 95% bootstrap interval **0.7100–0.8035**. These are existing model-assigned labels, not independently human-validated reference labels. The 100-item reserved holdout was not evaluated. [Results, limitations, and aggregate data](https://evals.kristenmartino.ai/leaderboard).

The sample uses original RSS input, not generated summaries, and combines fresh and saved captures. It covers ten reference categories across 55 outlets and is not a random recent-production sample. `top` had only 14 unique captured inputs and was excluded from reference sampling; all eleven Sift labels remained valid model outputs. The reported interval describes this development sample rather than deployment reliability.

## 1. Evaluation question

Which local models, if any, can handle Sift's news-processing tasks at acceptable quality, latency, and cost? Answering that requires runs on the application's corpus. The current repository provides task modules, scoring, and regression-test fixtures, plus one real development agreement baseline. It has not produced a final held-out model comparison.

## 2. Proposed model set

The original study lists Llama 3.1 8B and 70B Q4, Qwen 2.5 7B and 14B, DeepSeek V2 Lite, Claude Haiku 4.5 and Sonnet 4.6, GPT-4o, and GPT-4o mini.

These are study candidates, not measured recommendations. Exact model snapshots and local quantizations need to be pinned for execution. The proposed separation of 70B as a quality reference depends on the hardware timing benchmark; no deployment-feasibility result is claimed yet.

## 3. Tasks

| Task | Implementation | Proposed measurement |
|---|---|---|
| A: categorization | First development baseline completed | Stored-label agreement and macro-F1; independent label review pending |
| B: summarization | Task module, pairwise judge, and ranking implemented | Pairwise preference, length compliance, factuality flags |
| C: entity extraction | Planned; annotation rubric drafted | Schema validity and entity F1 reported separately |
| D: RAG benchmark | Planned; question-authoring rubric drafted | Answer quality and citation support |

The v0.3 agent track is separate from Task D. It runs a router, planner, executor, and critic with mock retrieval tools and scripted responses. It can exercise the agent and scorers without external services.

### Pairwise summary judging

The routing function assigns Sonnet to pairs without Anthropic candidates and GPT-4o to pairs containing an Anthropic candidate. This avoids Sonnet judging its own candidate outputs, but GPT-4o still judges Anthropic-versus-GPT-4o pairs. Vendor-dependent judgments remain a limitation.

A 50-pair overlap judged by both models and a Cohen's kappa check are planned. Neither judge agreement nor absence of bias has been established. The implementation uses [Bradley–Terry MM](https://www.jstor.org/stable/3448513) to fit strengths from pairwise results; no production-data ranking is available.

## 4. Agent scoring

The loop passes retrieved text to synthesis and critique as untrusted source material. It retains evidence records with article ID, span ID, title, and text, including in serialized trajectory runs. The mock tools use span `0` for an article's full body.

Tier A replays three scripted scenarios and checks tool selection, argument validity, error recovery, citation-ID coverage, and injection channels. A prompt, schema, or sampling change affecting a covered request causes a replay miss. Regenerating fixtures updates that baseline; it does not measure how a live model would respond to the change.

Tier B scores the replayed answers with a supplied judge:

- **Recall:** support for authored vital and optional nuggets in the generated answer.
- **Precision:** support for each sentence or clause from the actual answer against the reference context. Static rubric claims are not used as substitutes for generated content.
- **Citation faithfulness:** support for those same units against retrieved text named by the answer's exact `article_id#span` citations. Gold reference text cannot substitute for a missing source.
- **Credit:** supported = 1, partial = 0.5, unsupported or malformed = 0. All units stay in the denominator. Empty claim sets or empty context score zero.
- **Strict correctness:** full vital-nugget recall, full support for every answer unit, and nonempty, resolvable citations whose text fully supports the answer. Partial support fails this gate.

Sentence/clause splitting is deterministic and does not extract atomic factual claims. A semantic judge must evaluate every assertion in a compound unit. The keyword judge is only a CI smoke-test adapter: lexical overlap cannot reliably detect contradiction or establish entailment.

The document-injection fixture places an attack in retrieved text. Its scripted safe response checks harness behavior; it is not evidence of a model's injection resistance. Confidence intervals over three fixtures describe that fixture set and do not establish population-level reliability.

## 5. Proposed datasets and held-out procedure

| Set | Target size | Preparation still required |
|---|---|---|
| Categorization | 500 | 500 selected: 400 development, 100 reserved; label review pending |
| Summarization | 200 | Corpus sampling |
| Extraction | 100 | Entity annotation and annotator-agreement check |
| RAG | 50 + 20 unanswerable questions | Questions, reference answers, supporting sources |

The study proposes holding out 20% of each set before prompt iteration. The runner requires explicit opt-in for a set marked or detected as held-out and checks its contents against a SHA-256 manifest. The sample fixture lock is unchanged. For the October 24 categorization cohort, a separate 100-item holdout manifest was saved before the development run and is published with these results. That reserved set has not been evaluated. The manifest was not committed before the run; its presence in this publication is not proof of pre-run Git history.

A manifest verifies dataset contents against the supplied baseline. Git history can record when that baseline changed. Neither mechanism prevents someone reading the files outside the runner or proves that no tuning used them.

## 6. Sampling, latency, and cost plan

The original design proposes temperature 0 for categorization and extraction, and three temperature-0.7 samples per item for summarization and RAG. Actual sample sizes and uncertainty estimates must accompany results; no detection-power result is established here.

Latency measurements should include p50/p95, local cold starts, and API network time. Local cost calculations require hardware purchase cost, useful-life and utilization assumptions, measured power, and an electricity rate. API costs require token counts and rates recorded at run time. A sunk-hardware view and an amortized view must be labeled separately.

The first development run records local macOS ARM64 generation HTTP latency: median 0.663s and p95 3.618s. These timings exclude separate model-digest checks and do not constitute a DGX Spark benchmark or cost comparison. The timing script and budget estimator remain planning tools for the broader study.

## 7. Reproducibility and limitations

Task-run headers record model ID, dataset hash, harness commit, host, start time, and held-out status. Results and trajectories can be rescored downstream. Matching metadata helps identify a run; it does not independently validate its labels, judge, or conclusions.

The main outstanding work is independent categorization label review, a final held-out comparison, broader model runs, task implementation for C/D, and judge calibration. Public news may overlap model training data, so the proposed comparison concerns behavior on Sift's workload rather than unseen-text generalization. English content and the selected hardware limit the scope.

See the [repository](https://github.com/kristenmartino/eval-harness), [summary](executive_summary.md), and [results status](https://evals.kristenmartino.ai/leaderboard).
