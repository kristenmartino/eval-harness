#!/usr/bin/env python3
"""
Demonstrates the enforced held-out lock end-to-end with a MockAdapter.

Proves three things the methodology claims (spec §5):
  1. The runner REFUSES a held-out set without explicit opt-in.
  2. With --include-held-out, it verifies the set against the committed
     SHA-256 manifest (data/holdout.sha256) before scoring.
  3. The run header records held_out=true + the verified aggregate hash, so a
     final run is provably against the locked set.

Usage:
    python scripts/example_holdout.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from adapters.mock import MockAdapter  # noqa: E402
from tasks import categorization  # noqa: E402
from eval import runner  # noqa: E402


def main() -> int:
    adapter = MockAdapter(
        response_map={
            "Nvidia unveiled": "Tech",
            "offshore wind": "Energy",
            "upper chamber blocked": "Politics",
            "once-weekly injectable": "Health",
            "cut its full-year profit": "Business",
            "defending champions": "Sports",
        },
        model_id="mock-v1",
    )
    dataset = ROOT / "data" / "sample_holdout.jsonl"
    output = ROOT / "results" / "demo_holdout_mock.jsonl"
    if output.exists():
        output.unlink()

    print("=== 1. Refused without opt-in ===")
    try:
        runner.run(adapter, categorization.task, dataset, output, repo_root=ROOT)
        print("  FAIL: expected HeldOutAccessError")
        return 1
    except runner.HeldOutAccessError as e:
        print(f"  OK — runner refused: {type(e).__name__}")

    print("\n=== 2. Allowed with --include-held-out (manifest verified) ===")
    summary = runner.run(adapter, categorization.task, dataset, output,
                         repo_root=ROOT, include_held_out=True)
    print(f"  {summary}")
    assert summary["completed"] == 6 and summary["held_out"] is True

    print("\n=== 3. Header proves the locked set ===")
    header = json.loads(output.read_text().splitlines()[0])
    print(f"  held_out: {header['held_out']}")
    print(f"  holdout_aggregate_sha256: {header['holdout_aggregate_sha256']}")
    manifest = json.loads((ROOT / "data" / "holdout.sha256").read_text())
    assert header["holdout_aggregate_sha256"] == manifest["aggregate_sha256"]
    print("  matches data/holdout.sha256 ✓")

    print("\n=== 4. A mutated set is rejected ===")
    tampered = ROOT / "results" / "_tampered_holdout.jsonl"
    rows = dataset.read_text().splitlines()
    rows[0] = json.dumps({"id": "ho-001", "text": "TAMPERED", "category": "Tech"})
    tampered.write_text("\n".join(rows) + "\n")
    try:
        runner.run(adapter, categorization.task, tampered, output.with_name("_t.jsonl"),
                   repo_root=ROOT, include_held_out=True, split="holdout",
                   holdout_manifest=ROOT / "data" / "holdout.sha256")
        print("  FAIL: expected HoldoutLockError")
        return 1
    except runner.HoldoutLockError:
        print("  OK — runner rejected the mutated set")
    finally:
        tampered.unlink(missing_ok=True)
        output.with_name("_t.jsonl").unlink(missing_ok=True)

    print("\nHeld-out lock demo OK — gate, verification, and tamper-detection all enforced.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
