#!/usr/bin/env python3
"""
Key-free smoke for the Tier-B judged scoring path (spec §6). Runs the judged
dimensions (nugget recall, citation faithfulness, answer correctness) over the
committed golden using the deterministic KeywordJudge — no API keys — so the
Tier-B code path is exercised and gated in CI. The real nightly swaps in a
cross-vendor LLM judge behind the same interface.

Usage:  python scripts/example_tierb.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from adapters.keyword_judge import KeywordJudge  # noqa: E402
from eval import tierb  # noqa: E402


def main() -> int:
    result = tierb.run_tierb(ROOT / "data" / "set5", KeywordJudge())
    print(tierb.format_report(result))
    print()
    for p in result.per_scenario:
        print(f"  {p['scenario_id']:26s} recall={p['recall']} "
              f"faith={p['faithfulness']} correct={p['correct']}")

    assert result.scorecard["n_scenarios"] >= 3, result.scorecard
    assert result.scorecard["correct_rate"] == 1.0, result.scorecard
    assert result.scorecard["mean_recall"] >= 0.8, result.scorecard
    assert result.passed, result.failures
    print("\nTier-B key-free smoke OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
