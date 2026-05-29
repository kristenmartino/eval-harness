#!/usr/bin/env python3
"""
CLI entrypoint for the eval runner.

Thin wrapper around eval.runner.main() so the documented command is
`python scripts/run_eval.py ...` (matches the other scripts and avoids the
`python -m eval.runner` double-import warning).

Examples:
    # Dev run with the mock adapter (no keys needed)
    python scripts/run_eval.py --task A \
        --dataset data/sample_categorization.jsonl --output results/dev.jsonl

    # Held-out run — refused unless you opt in, then verified against the lock
    python scripts/run_eval.py --task A --dataset data/sample_holdout.jsonl \
        --output results/final.jsonl --include-held-out

    # Real run against a pinned closed-weight snapshot (key from env)
    python scripts/run_eval.py --task A --adapter anthropic \
        --model-id claude-haiku-4-5-20251215 \
        --dataset data/dev/set1.jsonl --output results/haiku_A.jsonl
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.runner import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
