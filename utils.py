"""
Shared helpers used by the harness and downstream analysis.

Note: the pre-flight scripts (in /scripts/) intentionally do not import from
here — they're kept stdlib-only and self-contained so they can run in any
order without package-import setup. Some duplication of `percentile` and
`load_jsonl` is the accepted cost; CHANGELOG documents this as tech debt.
"""

import json
import statistics
from pathlib import Path


def load_jsonl(path: Path) -> list:
    """Load a JSONL file into a list of dicts. Skips blank lines.
    Raises ValueError with line number on bad JSON for actionable debugging."""
    rows = []
    with path.open() as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"bad JSONL on line {i}: {e}") from e
    return rows


def percentile(values: list, pct: float) -> float:
    """Linear-interpolation percentile — matches numpy's default behavior."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (pct / 100)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def macro_f1(predictions: list, golds: list, labels: list) -> float:
    """Macro F1 — unweighted mean of per-label F1. Handles label imbalance
    (per spec §2 Task A — categories are imbalanced, accuracy alone misleads)."""
    f1s = []
    for label in labels:
        tp = sum(1 for p, g in zip(predictions, golds) if p == label and g == label)
        fp = sum(1 for p, g in zip(predictions, golds) if p == label and g != label)
        fn = sum(1 for p, g in zip(predictions, golds) if p != label and g == label)
        if tp + fp == 0 or tp + fn == 0:
            f1s.append(0.0)
            continue
        precision = tp / (tp + fp)
        recall = tp / (tp + fn)
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
        f1s.append(f1)
    return statistics.mean(f1s) if f1s else 0.0


def accuracy(predictions: list, golds: list) -> float:
    """Plain accuracy. None predictions count as incorrect."""
    if not predictions:
        return 0.0
    correct = sum(1 for p, g in zip(predictions, golds) if p == g and p is not None)
    return correct / len(predictions)
