#!/usr/bin/env python3
"""
Lock the adversarial trajectory set: compute its SHA-256 manifest and commit it
(NOT the data). A clone of scripts/lock_holdout.py for the §5 adversarial suite —
same discipline: lock the attacker-goal specs (injected args, canary, target
assertions) ONCE, before any prompt iteration, so guardrail cases can't leak
into the tuning loop (premortem #5). The runner/scorers verify against this
manifest exactly as they do the held-out lock.

Usage:
    python scripts/lock_adversarial.py --dataset data/set5_adversarial.jsonl
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
    p = argparse.ArgumentParser(description="Lock the adversarial set into a SHA-256 manifest.")
    p.add_argument("--dataset", required=True, type=Path)
    p.add_argument("--out", type=Path, default=ROOT / "data" / "adversarial.sha256")
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
        "schema": "adversarial-lock/v1",
        "dataset_file": rel,
        "n_items": len(items),
        "aggregate_sha256": _holdout_aggregate(items),
        "item_sha256": per_item,
        "note": args.note,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"Locked {len(items)} adversarial scenarios from {rel}")
    print(f"  aggregate_sha256: {manifest['aggregate_sha256']}")
    print(f"  manifest written: {args.out}")
    print("Commit the manifest (NOT the data) before any prompt iteration.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
