#!/usr/bin/env python3
"""
CLI for the Tier-A trajectory regression gate (spec §6). Key-free: replays the
committed golden cassettes, scores the deterministic dimensions + injection
guardrail, and gates per-dimension. Exit 0 = pass, 1 = fail (threshold breach or
replay miss). Wired into CI alongside the other smoke steps.

Usage:  python scripts/ci_trajectory_gate.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.gate import format_report, run_gate  # noqa: E402


def main(argv=None) -> int:
    result = run_gate(ROOT / "data" / "set5")
    print(format_report(result))
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
