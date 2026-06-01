"""
Task A metrics aggregation — turn a categorization results JSONL into the
leaderboard's headline numbers: accuracy + macro-F1 with a bootstrap CI.

Reads the runner's output (eval/runner.py): a `_meta` header row followed by
one row per (item_id, sample_idx). Honest by construction — the three ways a
score gets quietly inflated are all closed here:

  - Parse failures (score.predicted is None) count as INCORRECT. A model that
    won't emit a parseable label is penalized, not excused.
  - Error rows (the runner recorded an `error`, no score) are coverage gaps,
    NOT silently dropped. They're counted and surfaced as coverage < 1.0 so the
    headline is never computed over a quietly-shrunk denominator. Resume the run
    to zero errors before publishing (CLI: --require-full-coverage enforces it).
  - macro-F1's label space is explicit. The published number should be scored
    over the task's full taxonomy (pass `--labels`), so a class the model never
    predicts still counts as a 0-F1 against it rather than vanishing.

Metric definitions match the leaderboard ("single-label ... Macro-F1 with
bootstrap CI") and REUSE the tested primitives in utils.py — no reimplementation,
because a second copy of macro_f1 is a second thing that can silently disagree
with the scoreboard. The bootstrap is seeded (default 0) so the CI is
reproducible, consistent with the rest of the harness.

CLI: `python scripts/score_results.py --results results/out.jsonl`.
"""

import argparse
import json
import random
import sys
from pathlib import Path

from utils import accuracy, load_jsonl, macro_f1, percentile


def _split_rows(rows: list):
    """Partition a results JSONL into (header, scored, error).

    scored = rows carrying a `score` dict (includes parse failures, whose
             score.predicted is None — they are real, counted predictions).
    error  = rows carrying an `error` field (runner failures, no score) — these
             are coverage gaps, reported but not scorable (the error row has no
             gold to score against).
    A row with neither is ignored defensively rather than crashing the report.
    """
    header = {}
    scored, error = [], []
    for row in rows:
        if row.get("_meta"):
            header = row
        elif "score" in row:
            scored.append(row)
        elif "error" in row:
            error.append(row)
    return header, scored, error


def _bootstrap_ci(predictions: list, golds: list, labels: list, *,
                  n_boot: int, seed: int, alpha: float):
    """Percentile bootstrap CI for macro-F1.

    Resamples (prediction, gold) pairs WITH replacement n_boot times, recomputes
    macro-F1 over the SAME fixed label space each time, and returns the
    (alpha/2, 1-alpha/2) percentiles. Seeded so the interval is reproducible.

    Degenerate inputs return a zero-width interval at the point estimate: a CI
    needs resampling variety (>= 2 items) and at least one resample to mean
    anything, and faking width on a single point would overstate precision.

    Validity note: a percentile bootstrap needs adequate per-class support. With
    singleton classes (~1 item/class) most resamples drop a class entirely, so
    macro-F1 in nearly every resample falls below the full-sample point and the
    interval can sit BELOW the point estimate. Methodology §8 keeps only classes
    with >= 20 articles — the same condition that makes this CI meaningful. On
    the 5-row demo the CI is not interpretable; on a real Set-1 it is."""
    point = macro_f1(predictions, golds, labels) if predictions else 0.0
    if n_boot < 1 or len(predictions) < 2:
        return point, point
    rng = random.Random(seed)
    n = len(predictions)
    stats = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        bp = [predictions[i] for i in idx]
        bg = [golds[i] for i in idx]
        stats.append(macro_f1(bp, bg, labels))
    return percentile(stats, 100 * (alpha / 2)), percentile(stats, 100 * (1 - alpha / 2))


def aggregate(rows: list, *, labels: list = None, n_boot: int = 1000,
              seed: int = 0, alpha: float = 0.05) -> dict:
    """Compute the Task A headline metrics from a list of results rows.

    labels: the macro-F1 label space. Default = sorted unique gold labels
        observed in the file. For a PUBLISHED row pass the task's official
        CATEGORIES so the macro is taken over the full taxonomy (a class the
        model never predicts then counts as 0 F1 rather than being dropped).

    The run's provenance (model_id, dataset hash, harness git SHA, held_out
    flag, timestamp) is read from the `_meta` header and echoed into the result,
    so the emitted metric is inseparable from the exact run that produced it.
    """
    header, scored, error = _split_rows(rows)
    predictions = [r.get("score", {}).get("predicted") for r in scored]
    golds = [r.get("score", {}).get("gold") for r in scored]
    n_parse_failed = sum(1 for p in predictions if p is None)
    if labels is None:
        labels = sorted({g for g in golds if g is not None})

    n_scored = len(scored)
    n_error = len(error)
    n_total = n_scored + n_error
    coverage = (n_scored / n_total) if n_total else 0.0

    acc = accuracy(predictions, golds) if scored else 0.0
    mf1 = macro_f1(predictions, golds, labels) if scored else 0.0
    ci_low, ci_high = _bootstrap_ci(
        predictions, golds, labels, n_boot=n_boot, seed=seed, alpha=alpha)

    return {
        # provenance — bound to the run, not asserted separately
        "model_id": header.get("model_id"),
        "task": header.get("task"),
        "dataset_path": header.get("dataset_path"),
        "dataset_sha256_prefix": header.get("dataset_sha256_prefix"),
        "harness_git_sha": header.get("harness_git_sha"),
        "held_out": header.get("held_out"),
        "started_at": header.get("started_at"),
        # what was scored
        "labels": list(labels),
        "n_scored": n_scored,
        "n_parse_failed": n_parse_failed,
        "n_error": n_error,
        "coverage": coverage,
        # headline numbers
        "accuracy": acc,
        "macro_f1": mf1,
        "macro_f1_ci_low": ci_low,
        "macro_f1_ci_high": ci_high,
        "ci_alpha": alpha,
        "bootstrap_n": n_boot,
        "bootstrap_seed": seed,
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _format_human(summary: dict) -> str:
    """A glanceable summary for stderr. The machine-readable JSON (stdout) is
    the source of truth for the leaderboard; this is for the human running it."""
    def pct(x):
        return f"{x * 100:.1f}%" if x is not None else "n/a"
    conf = int(round((1 - summary["ci_alpha"]) * 100))
    return "\n".join([
        f"  model_id   {summary['model_id']}",
        f"  task       {summary['task']}",
        f"  dataset    {summary['dataset_path']}  (sha {summary['dataset_sha256_prefix']})",
        f"  git SHA    {summary['harness_git_sha']}",
        f"  held_out   {summary['held_out']}",
        f"  scored     {summary['n_scored']}  "
        f"(parse-failed {summary['n_parse_failed']}, errored {summary['n_error']})",
        f"  coverage   {pct(summary['coverage'])}",
        f"  accuracy   {pct(summary['accuracy'])}",
        f"  macro-F1   {summary['macro_f1']:.4f}  "
        f"[{summary['macro_f1_ci_low']:.4f}, {summary['macro_f1_ci_high']:.4f}]  "
        f"({conf}% CI, {summary['bootstrap_n']} boot, seed {summary['bootstrap_seed']})",
        f"  labels     {', '.join(summary['labels'])}",
    ])


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="python scripts/score_results.py",
        description="Aggregate a Task A results JSONL into accuracy + macro-F1 (bootstrap CI).",
    )
    p.add_argument("--results", required=True, type=Path, help="runner output JSONL")
    p.add_argument("--labels", nargs="*", default=None,
                   help="official taxonomy for macro-F1 (default: gold labels observed). "
                        "Pass the task's CATEGORIES for a published row.")
    p.add_argument("--bootstrap", type=int, default=1000,
                   help="bootstrap resamples for the macro-F1 CI (0 = point estimate only)")
    p.add_argument("--seed", type=int, default=0, help="bootstrap seed (reproducible CI)")
    p.add_argument("--alpha", type=float, default=0.05, help="CI alpha (0.05 = 95%% CI)")
    p.add_argument("--require-full-coverage", action="store_true",
                   help="exit nonzero if any item errored (coverage < 100%%) — "
                        "gate a publish on a complete run")
    args = p.parse_args(argv)

    rows = load_jsonl(args.results)
    summary = aggregate(rows, labels=args.labels, n_boot=args.bootstrap,
                        seed=args.seed, alpha=args.alpha)

    print(_format_human(summary), file=sys.stderr)
    print(json.dumps(summary, indent=2))

    if args.require_full_coverage and summary["n_error"] > 0:
        print(
            f"error: coverage {summary['coverage'] * 100:.1f}% < 100% "
            f"({summary['n_error']} item(s) errored). Resume the run to zero errors "
            f"before publishing this row.",
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
