#!/usr/bin/env python3
"""
Lock a held-out set: compute its SHA-256 manifest and commit it (NOT the data).

This is the enforcement half of the methodology's held-out discipline (§5).
Run ONCE, before any prompt iteration, then `git add` the manifest. The runner
verifies every held-out run against this manifest (eval/runner.py::_verify_holdout)
and refuses to score a set that has changed since it was locked — so a reviewer
can confirm the hash never moved, and you can't tune against the test set.

The held-out *data* stays private (gitignored under data/holdout/); only the
hash manifest is public. This script imports the runner's hashing helpers so the
locked hash is guaranteed identical to what the runner recomputes.

Usage:
    python scripts/lock_holdout.py --dataset data/holdout/set1.jsonl
    python scripts/lock_holdout.py --dataset data/sample_holdout.jsonl \
        --note "demo lock over the sample fixture; real Set-1 lock lands at corpus pull"
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.runner import _canonical_bytes, _holdout_aggregate, _load_dataset  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Lock a held-out set into a SHA-256 manifest.")
    p.add_argument("--dataset", required=True, type=Path)
    p.add_argument("--out", type=Path, default=ROOT / "data" / "holdout.sha256")
    p.add_argument("--note", default="")
    args = p.parse_args(argv)

    items = _load_dataset(args.dataset)
    if not items:
        raise SystemExit(f"{args.dataset} has no items — nothing to lock")

    per_item = sorted(hashlib.sha256(_canonical_bytes(it)).hexdigest() for it in items)
    try:
        rel = str(args.dataset.resolve().relative_to(ROOT))
    except ValueError:
        rel = str(args.dataset)

    manifest = {
        "schema": "holdout-lock/v1",
        "dataset_file": rel,
        "n_items": len(items),
        "aggregate_sha256": _holdout_aggregate(items),
        "item_sha256": per_item,
        "note": args.note,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"Locked {len(items)} items from {rel}")
    print(f"  aggregate_sha256: {manifest['aggregate_sha256']}")
    print(f"  manifest written: {args.out}")
    print("Commit the manifest (NOT the data) before any prompt iteration.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
