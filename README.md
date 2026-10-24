# Eval Harness

A Python evaluation harness for Sift's news-processing tasks. Categorization, summarization, model adapters, and scripted agent regression tests are implemented. A first real categorization development baseline ran on 2026-10-24; the full model comparison and routing recommendations remain pending.

The first baseline used local Llama 3.1 8B Instruct Q4_K_M on 400 original RSS inputs across ten reference categories: **319/400 stored-label matches (79.8%)**, **macro-F1 0.7598** (descriptive bootstrap interval 0.7100–0.8035), zero execution or parsing failures. The reference labels are existing production model labels, not independently reviewed human gold. Another 100 items remain reserved and unevaluated. See the [published run report](docs/results/2026-10-24-categorization-development.md), [aggregate data](web/public/results/categorization-development-2026-10-24.json), and [runbook](docs/runbook_task_a.md).

[Methodology](docs/methodology.md) · [Project summary](docs/executive_summary.md) · [Task-study spec](eval-harness-spec.md) · [Agent-study spec](eval-harness-spec-v0.3.md) · [Changelog](CHANGELOG.md)

## Run locally

Python 3.9+, with no runtime dependencies. These commands need no API keys:

```bash
python scripts/example_run.py
python scripts/example_task_b.py
python scripts/example_holdout.py
python scripts/example_agent_run.py
python scripts/example_tierb.py
python scripts/ci_trajectory_gate.py
python -m unittest discover -s tests
```

The task-run CLI defaults to the mock adapter:

```bash
python scripts/run_eval.py --task A --dataset data/sample_categorization.jsonl --output results/dev.jsonl
```

Real adapters require their respective service or credentials. See the [Task A runbook](docs/runbook_task_a.md) and [agent runbook](docs/runbook_v0.3_step7.md).

## Implemented

- `adapters/`: Ollama, Anthropic, OpenAI, mock, scripted, replay, and keyword-judge adapters.
- `tasks/`: categorization and summarization prompt/parser/scorer modules.
- `eval/runner.py`: JSONL results with run metadata, resume validation, transient-error retries, and held-out opt-in and manifest checks.
- `eval/judge.py`, `eval/metrics.py`, `eval/bradley_terry.py`: pairwise summary judgments, categorization metrics, and preference ranking.
- `agent/`: router/planner/executor/critic loop over mock corpus tools. Retrieved text reaches synthesis and critique and is retained with the run.
- `eval/trajectory.py`, `eval/gate.py`: deterministic process checks and a replay gate over three scripted scenarios.
- `eval/stats.py`, `eval/tierb.py`: nugget recall, support of generated answer sentences/clauses, and faithfulness to retrieved spans actually cited. Partial support receives half credit and fails the strict correctness gate; missing or unresolved citations also fail.
- `scripts/` and `rubrics/`: corpus preparation, timing and budget estimators, fixture generation, and annotation guidance.

## Fixture provenance and scoring limits

The three committed agent cassettes are generated from handwritten `ScriptedAdapter` responses in `scripts/build_golden.py`. Scenario records declare `response_source: scripted`. CI replays them to test the loop and scorers; it does not measure a live model's quality or injection resistance. The adversarial fixture includes an instruction embedded in retrieved document text.

The keyword judge uses token overlap only. It makes the scoring path runnable without keys, but cannot establish semantic support or detect every contradiction. Live evaluation requires an independently calibrated semantic judge. Generated answers are segmented into sentences and clauses without filtering; this is not atomic claim extraction, and the judge must evaluate compound assertions in full.

A covered request change causes a replay miss. After reviewing an intentional change, regenerate the scripted baseline with:

```bash
python scripts/build_golden.py
```

Regeneration keeps the authored responses and updates their request keys. It cannot demonstrate how a live model would respond to a changed prompt.

## Dataset and judge limits

The held-out gate checks opt-in and dataset integrity against a supplied SHA-256 manifest. Git history can record baseline changes. These mechanisms do not prevent reading data outside the runner or prove that no tuning used it. The sample fixture lock remains unchanged. The first real corpus has a separate saved 100-item holdout manifest; it was not evaluated in the development run.

Pairwise judge routing avoids Sonnet judging Anthropic candidates. GPT-4o still judges Anthropic-versus-GPT-4o pairs, so self-judging is not eliminated. The proposed overlap calibration has not been measured.

## Pending study work

The original design proposes nine models and four tasks. The initial corpus pull and one categorization development run are complete. Independent label review, the final held-out comparison, entity extraction and Task D implementation, judge calibration, DGX hardware timing, broader model runs, and measured cost comparisons remain pending. The separate agent track currently uses mock tools and scripted responses.

The Next.js site in `web/` presents implementation status and the study plan. It contains no completed production-data leaderboard.

## License and author

Copyright © 2026 Kristen Martino. All rights reserved — see [LICENSE](LICENSE).
