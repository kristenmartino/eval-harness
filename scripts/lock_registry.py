#!/usr/bin/env python3
"""
Snapshot-lock the tool-registry schema (spec §6, §12).

Pins `tool_registry_hash` so a MAJOR tool-schema change (remove a tool /
rename-retype-tighten a required arg / change a return shape) trips a reviewed
re-baseline instead of silently passing the regression gate. Default = VERIFY
the committed manifest against the live registry (CI, exit 1 on mismatch);
`--update` rewrites the snapshot — the reviewed 'jest -u' discipline.

Usage:
    python scripts/lock_registry.py            # verify (CI)
    python scripts/lock_registry.py --update   # re-baseline after a reviewed schema change
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.tools import build_mock_registry  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Lock/verify the tool-registry schema snapshot.")
    p.add_argument("--out", type=Path, default=ROOT / "data" / "registry.sha256")
    p.add_argument("--version", default="1.0.0")
    p.add_argument("--update", action="store_true",
                   help="rewrite the snapshot after a reviewed schema change")
    args = p.parse_args(argv)

    registry = build_mock_registry()
    current = {
        "schema": "registry-lock/v1",
        "version": args.version,
        "registry_sha256": registry.registry_hash(),
        "tools": registry.schemas(),
    }

    if args.update or not args.out.exists():
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(current, indent=2) + "\n")
        print(f"registry snapshot written: {current['registry_sha256']}")
        print("Commit the manifest; a MAJOR schema change must re-baseline via --update.")
        return 0

    committed = json.loads(args.out.read_text())
    if committed.get("registry_sha256") != current["registry_sha256"]:
        print("BASELINE INVALIDATED: the tool-registry schema changed.")
        print(f"  committed {committed.get('registry_sha256')}")
        print(f"  current   {current['registry_sha256']}")
        print("  Re-baseline (after reviewing the schema diff): "
              "python scripts/lock_registry.py --update")
        return 1
    print(f"registry lock matches: {current['registry_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
