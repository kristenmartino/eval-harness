#!/usr/bin/env python3
"""
CLI entrypoint for Task A metrics aggregation.

Thin wrapper around eval.metrics.main() so the documented command is
`python scripts/score_results.py ...` (matches scripts/run_eval.py and avoids
the `python -m eval.metrics` double-import warning).

Examples:
    # Dev: score a run, labels inferred from the gold column
    python scripts/score_results.py --results results/dev_A.jsonl

    # Publish-grade: score over the official taxonomy, refuse on any coverage gap
    python scripts/score_results.py --results results/local_A.jsonl \
        --labels Tech Politics Energy Health Business Sports \
        --require-full-coverage

Prints a human summary to stderr and the machine-readable metric JSON to stdout
(redirect stdout to capture the row that feeds the leaderboard).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.metrics import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
