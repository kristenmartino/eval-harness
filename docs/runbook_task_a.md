# Runbook — real Task A categorization baseline

The first run uses original Sift RSS inputs matched to existing production category labels. Those labels were model-assigned and have not been independently reviewed: the resulting accuracy and macro-F1 measure agreement with the stored labels, not human-verified correctness.

## Capture and export

Sift does not persist original article bodies in its database. Its `summary` column is generated output and must not be substituted for source input. Capture RSS inputs through `services.rss.fetch_feeds`, or use the saved original inputs in Sift's `data/eval/summarizer_corpus*.jsonl` files.

Set `SIFT_API_ROOT` and `EVAL_ROOT` to your local checkout paths, then run the exporter from the Sift API project using its virtual environment (the export needs Sift's existing `asyncpg` and `python-dotenv` dependencies):

```bash
cd "$SIFT_API_ROOT"
.venv/bin/python "$EVAL_ROOT/scripts/pull_sift_corpus.py" \
  --sift-root "$SIFT_API_ROOT" \
  --capture "$EVAL_ROOT/data/private/sift-pull-2026-10-24/fresh_rss_capture.jsonl" \
  --capture data/eval/summarizer_corpus.jsonl \
  --capture data/eval/summarizer_corpus_b.jsonl \
  --output "$EVAL_ROOT/data/private/sift-pull-2026-10-24"
```

The exporter uses a read-only, repeatable-read database snapshot and performs no production writes. It matches by source URL, rejects changed titles and missing bodies, and retains stable production article IDs. Input formatting follows Sift's HTML stripping and 500-word body limit. Captures, article text, and the detailed corpus manifest remain in ignored directories.

The one-time 2026-10-24 export refuses to overwrite an existing dataset or manifest. For a new cohort, create new artifact names deliberately rather than replacing this baseline.

## Freeze the dataset and task

`eval/corpus.py` deduplicates article IDs, URLs, and normalized source-content hashes before sampling. It uses a fixed seed, excludes categories with fewer than 20 unique source inputs, and allocates a 500-item stratified sample. It reserves 100 items as holdout and writes 400 development items. The holdout manifest is saved before inference; a saved hash is an integrity baseline, not proof that nobody inspected the underlying data.

The first run artifacts are:

- `data/dev/set1_20261024.jsonl`: 400 development items.
- `data/holdout/set1_20261024.jsonl`: 100 reserved items; not evaluated in the first run.
- `data/set1_20261024.holdout.sha256`: the separate cohort lock. The sample lock used by CI is unchanged.
- `data/set1_20261024.categories.json`: all eleven current Sift labels and their production routing rules. These are explicit run configuration, not the sample fixture's six labels.
- `data/private/sift-pull-2026-10-24/corpus_manifest.json`: source captures, hashes, snapshot date, rejection reasons, and sampling counts.

`top` has only 14 unique source-matched inputs in this captured pool and is excluded from the sampled reference-label space. The classifier can still output `top`; that is scored as a disagreement for a development item whose stored label differs. The reported macro-F1 uses the ten reference categories declared in the manifest.

## Run the model

From the eval-harness root:

```bash
python3 scripts/run_eval.py --task A --adapter ollama \
  --model-id llama3.1:8b-instruct-q4_K_M \
  --model-digest 46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e \
  --categories-file data/set1_20261024.categories.json --seed 20261024 \
  --dataset data/dev/set1_20261024.jsonl \
  --output results/llama31_8b_q4_A_dev_20261024.jsonl
```

The digest is the observed Ollama manifest SHA-256, not an asserted Hugging Face commit. The adapter checks the tag's manifest before each generation. This run uses the local macOS ARM64 runtime; it is not a DGX Spark hardware benchmark.

The runner records the taxonomy, instructions, prompt-template hash, sampling parameters, dataset hash, and model identity. Resume refuses a changed task configuration or sampling setup. Outputs must match one label exactly, allowing case and surrounding punctuation; ambiguous explanations are parse failures.

For this first run, uncommitted run-enablement source files are copied and hashed under `data/private/sift-pull-2026-10-24/harness_source_snapshot/`. The companion `results/llama31_8b_q4_A_dev_20261024.run.json` binds the command and source hashes to the base Git commit; the base commit alone does not describe the modified run code.

## Score and interpret

```bash
python3 scripts/score_results.py \
  --results results/llama31_8b_q4_A_dev_20261024.jsonl \
  --labels business energy entertainment general health politics science sports technology world \
  --require-full-coverage \
  > results/llama31_8b_q4_A_dev_20261024.metrics.json
```

Check one result per expected item, zero execution errors, and explicit parse-failure counts. Report per-category support and confusion counts along with aggregate agreement. Bootstrap intervals describe this development sample and its existing labels; they do not establish deployment readiness. Energy has 16 development items, so its class-level estimate is particularly uncertain.

The held-out set remains reserved for a later frozen-prompt evaluation after independent label review. Do not publish a ranking, switch production models, or turn development agreement into a correctness claim from this first run.
