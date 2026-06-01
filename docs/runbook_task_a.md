# Runbook — first real Task A leaderboard row

Goal: produce the **first non-`pending` Task A (categorization) row** on the
leaderboard — a macro-F1 with bootstrap CI on the locked held-out set, fully
reproducible and provenance-bound. The example backend is one local open-weight
model via Ollama on the DGX Spark; a closed-weight API run swaps only the
`--adapter`/`--model-id` flags.

The harness is ready (runner, Task A, scoring, held-out lock, metrics are all
tested). What this runbook needs from **you** are the three things only you can
supply:

| Input | Where it comes from |
| --- | --- |
| **Real corpus** (`{id, text, category}` JSONL) | Your stratified pull from Sift — the repo has only a 5-row demo |
| **Category taxonomy** | `category_distribution_check.py` output, ≥20/category (§8) |
| **Local model + HF SHA** | Ollama on the DGX: pulled model tag + the weights' HF SHA |
| **The OK to publish** | The leaderboard row is a public claim — your call |

> The step-3 commands run the harness **on the DGX**, so the Ollama adapter's
> default host (`localhost:11434`) is the local server. To run the harness
> elsewhere (e.g. your laptop) against Ollama on the DGX, add
> `--ollama-host http://<dgx-host>:11434` to those commands.

---

## 0. Decide the taxonomy (§8 feasibility)

Export a `category,count` table from Sift and check sampling feasibility — this
applies the §8 rule (drop any category with < 20 articles; don't upsample):

```bash
python scripts/category_distribution_check.py --input categories.csv --target-n 500 --min-per-category 20
```

Set the surviving categories as `CATEGORIES` in `tasks/categorization.py`
(it currently holds a placeholder list). The same list is what you pass to
`--labels` in step 3 so the macro-F1 is taken over the full taxonomy.

## 1. Pull the corpus (your data step)

Produce two JSONL files of `{"id", "text", "category"}`, stratified by the kept
categories, drawn from your Sift export:

- `data/dev/set1.jsonl` — for prompt iteration (safe to look at)
- `data/holdout/set1.jsonl` — final scoring only (gitignored; never iterate on it)

The repo does not pull these for you — it has no Sift access. The committed
`data/sample_categorization.jsonl` (5 rows) is a format reference only.

## 2. Lock the held-out set — BEFORE any prompt iteration

```bash
python scripts/lock_holdout.py --dataset data/holdout/set1.jsonl
git add data/holdout.sha256 && git commit -m "lock Task A Set-1 held-out manifest"
```

This commits the **hash, not the data**. The runner verifies every held-out run
against it and refuses a mutated set — so a reviewer can confirm the test set
never moved. Lock once, at corpus pull, before tuning anything.

## 3. Run the model → results JSONL

Iterate prompts on **dev** (look at the rows, adjust, re-run — it resumes):

```bash
python scripts/run_eval.py --task A --adapter ollama \
    --model-id <ollama_tag> --hf-sha <hf_sha> \
    --dataset data/dev/set1.jsonl --output results/<model>_A_dev.jsonl
```

When the prompt is frozen, the **final** held-out run (note the explicit opt-in;
it is verified against the step-2 lock):

```bash
python scripts/run_eval.py --task A --adapter ollama \
    --model-id <ollama_tag> --hf-sha <hf_sha> \
    --dataset data/holdout/set1.jsonl --output results/<model>_A_final.jsonl \
    --include-held-out
```

`model_id` in every row is `<ollama_tag>:<hf_sha[:7]>`, so a result traces
unambiguously to the weights that produced it.

## 4. Score → headline metric

```bash
python scripts/score_results.py --results results/<model>_A_final.jsonl \
    --labels Tech Politics Energy Health Business Sports \
    --require-full-coverage
```

(Substitute your real `CATEGORIES` for `--labels`.) This prints a human summary
to stderr and machine JSON to stdout:

- **`macro_f1`** + **`macro_f1_ci_low/high`** — the leaderboard headline (95% CI,
  seeded bootstrap, default 1000 resamples).
- **`accuracy`** — secondary.
- **`coverage`** — must be `1.0`. `--require-full-coverage` makes the command
  **exit non-zero if any item errored**; resume step 3 until coverage is 100%
  before publishing. Parse failures already count as wrong (not skipped).
- Provenance (`model_id`, `dataset_sha256_prefix`, `harness_git_sha`,
  `held_out: true`, `started_at`) is carried on the metric itself.

Capture the JSON for the record: append ` > results/<model>_A_final.metrics.json`.

## 5. Fill the leaderboard row (the public claim)

In `web/src/app/leaderboard/page.tsx`, replace one `pending` Task A cell with the
`macro_f1` and its CI from step 4. Keep the per-vendor hedging discipline; cite
the held-out lock. **This is the only step that makes a public claim — do it
deliberately and on your sign-off.**

---

## Honesty guardrails baked in

- **Held-out lock is enforced, not documented** — the runner refuses a held-out
  run without `--include-held-out` and refuses a set that doesn't match its
  committed manifest.
- **Coverage is explicit** — error rows lower `coverage` below 1.0 instead of
  silently shrinking the denominator; `--require-full-coverage` gates a publish.
- **Parse failures are penalized**, not dropped.
- **The bootstrap CI needs per-class support.** With singleton classes the CI can
  sit below the point estimate — meaningless. It is interpretable only at real
  Set-1 scale (≥ 20/class, §8), not on the 5-row demo.
- **Every metric is recomputable from the JSONL** — re-scoring never re-runs the
  model.

## Smoke test (plumbing only — no model, no data, nothing public)

Confirms the runner → score chain works end to end on the committed demo. Macro-F1
here is **not** a real result (mock model, 5 rows, CI not interpretable — use
`--bootstrap 0` to suppress it):

```bash
printf '%s\n' '{"M5 chips":"Tech","energy bill":"Energy","immigration reform":"Politics","gene therapy":"Health","Quarterly earnings":"Business"}' > /tmp/mock_A.json
python scripts/run_eval.py --task A --adapter mock --mock-responses /tmp/mock_A.json \
    --model-id smoke --dataset data/sample_categorization.jsonl --output /tmp/smoke_A.jsonl
python scripts/score_results.py --results /tmp/smoke_A.jsonl --bootstrap 0
```
