# First real Sift categorization eval — 2026-10-24

Llama 3.1 8B Instruct Q4_K_M completed **400/400 development articles** across **10 reference categories** with **79.8% agreement** with Sift’s stored labels and **macro-F1 0.7598**.

The descriptive 95% bootstrap interval for macro-F1 is **[0.7100, 0.8035]** (1,000 resamples, seed 0). There were **0 execution errors, 0 retries, and 0 parse failures**.

**Interpretation:** these are existing model-assigned production labels, not independently reviewed human labels. This is a development agreement baseline; it does not establish true classification accuracy or a production-model replacement decision.

## Corpus and split

- Captured 549 usable original RSS inputs through Sift’s reader and combined them with 600 saved original inputs.
- Matched 1,013 inputs to production rows; rejected 123 changed titles and 13 unmatched URLs. Removed 51 duplicate IDs, URLs, or normalized content fingerprints, leaving 962 unique source-matched inputs.
- Selected 500 articles with seed 20261024: 400 development and 100 reserved holdout. Neither generated summaries nor stored category fields were included as article input.
- The development set spans 55 outlets: 205 fresh-capture items and 195 saved-input items. Publication dates range from 2024-10-10 through 2026-10-24; this is not a random recent-production sample.
- `top` had 14 unique inputs in the captured pool and was excluded from the reference sample. All eleven Sift categories remain valid classifier outputs; macro-F1 is over the ten reference labels declared before inference.
- The 100-item holdout was not evaluated. Its saved manifest and file hash remain unchanged, and IDs, URLs, and content fingerprints are disjoint from development.

## Per-category agreement

| Stored category | Support | Matched | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|
| business | 31 | 23 | 0.821 | 0.742 | 0.780 |
| energy | 16 | 14 | 0.737 | 0.875 | 0.800 |
| entertainment | 66 | 54 | 0.885 | 0.818 | 0.850 |
| general | 23 | 4 | 1.000 | 0.174 | 0.296 |
| health | 28 | 21 | 0.875 | 0.750 | 0.808 |
| politics | 103 | 95 | 0.725 | 0.922 | 0.812 |
| science | 21 | 19 | 0.679 | 0.905 | 0.776 |
| sports | 35 | 31 | 0.886 | 0.886 | 0.886 |
| technology | 31 | 29 | 0.806 | 0.935 | 0.866 |
| world | 46 | 29 | 0.853 | 0.630 | 0.725 |

Energy has only 16 development items; per-class estimates and the bootstrap interval should be read as descriptive results for this sample.

## Largest disagreements

| Stored category | Llama output | Count |
|---|---|---:|
| world | politics | 14 |
| general | politics | 10 |
| business | politics | 6 |
| entertainment | politics | 5 |
| entertainment | technology | 4 |
| general | entertainment | 4 |
| health | science | 3 |
| business | technology | 2 |
| entertainment | sports | 2 |
| general | world | 2 |

A disagreement can reflect a model error, a stale or noisy stored label, or ambiguity in the category rules. No disagreement has been independently adjudicated in this run.

## Run provenance

- Model identity: `llama3.1:8b-instruct-q4_K_M@ollama-sha256:46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e`.
- Local macOS ARM64 Ollama 0.40.10; this is not a DGX Spark hardware benchmark. No API model generations were used.
- Categorization-only prompt with Sift’s checked-out category definitions and routing rules. This is not the full production batch summarization operation.
- Temperature 0, seed 20261024, maximum 10 output tokens. The tag’s Ollama manifest digest was checked before each generation; no Hugging Face commit is asserted.
- Median generation HTTP latency: 0.663s; p95: 3.618s. The digest-check request is outside these timings.
- Reported tokens: 385,583 input and 992 output.
- Development dataset SHA-256: `18985deacb5fd0beb4b3945b1c0799d842e503bfe3b84e7380c19e9cd3c031d1`.
- Base Git commit: `6e37a1103443e1d62c712d350820b15e83d99525`. Run-enablement changes were uncommitted; exact executed source files were copied and hashed in the private source snapshot. The base commit alone is not the complete run code.
- Verified one scored row per expected article, no duplicate result IDs, unchanged dataset hashes, and unchanged executed source-file hashes.

## Public evidence

- [Aggregate measurements, category breakdown, configuration, and provenance hashes](../../web/public/results/categorization-development-2026-10-24.json)
- [Site results page](https://evals.kristenmartino.ai/leaderboard)
- [Category definitions](../../data/set1_20261024.categories.json)
- [Reserved-holdout manifest](../../data/set1_20261024.holdout.sha256)
- [Reproduction runbook](../runbook_task_a.md)

The aggregate artifact lists hashes of the exact executed source files. Those source files are published in this repository; the base commit recorded by the run alone does not contain the run-enablement changes. The holdout manifest was saved before inference and is committed with this publication, not in a pre-run commit.

Article text and per-item run artifacts remain local; the public evidence is aggregate measurements and provenance hashes. Independent review of reference labels is still needed before using the reserved holdout for a final comparison.
