#!/usr/bin/env python3
"""
Tier-B judged nightly (spec §6) — the KEYED counterpart to the per-PR Tier-A
gate. Replays the committed golden trajectories (deterministic, no agent re-run)
and drives the pointwise judge over the authored nuggets/claims to score
answer-correctness + citation faithfulness, then gates on tierb_thresholds.json.

Runs on a schedule, not per-PR, because the judged dimensions need a live model.
Use `--judge keyword` for a key-free dry run (same path CI smoke-tests).

For the real nightly the judge should be CROSS-VENDOR (spec §7 / eval.judge):
if the agent backbone is a Claude model, route the judge to GPT-4o to avoid
self-preference. This CLI takes a single judge for simplicity; wire
eval.judge.select_judge in when the model axis lands.

Usage:
    python scripts/tierb_nightly.py --judge keyword          # key-free dry run
    python scripts/tierb_nightly.py --judge openai --judge-model gpt-4o
    ANTHROPIC_API_KEY=... python scripts/tierb_nightly.py --judge anthropic \
        --judge-model claude-sonnet-4-6
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval import tierb  # noqa: E402


def _build_judge(args):
    if args.judge == "keyword":
        from adapters.keyword_judge import KeywordJudge
        return KeywordJudge()
    if args.judge == "anthropic":
        from adapters.anthropic import AnthropicAdapter
        return AnthropicAdapter(_require(args.judge_model, "--judge-model"))
    if args.judge == "openai":
        from adapters.openai import OpenAIAdapter
        return OpenAIAdapter(_require(args.judge_model, "--judge-model"))
    if args.judge == "ollama":
        from adapters.ollama import OllamaAdapter
        return OllamaAdapter(_require(args.judge_model, "--judge-model"),
                             _require(args.judge_hf_sha, "--judge-hf-sha"),
                             host=args.ollama_host)
    raise ValueError(f"unknown judge {args.judge!r}")


def _require(val, flag):
    if not val:
        raise SystemExit(f"{flag} is required for this judge")
    return val


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Tier-B judged nightly gate.")
    p.add_argument("--judge", default="keyword",
                   choices=["keyword", "anthropic", "openai", "ollama"])
    p.add_argument("--judge-model")
    p.add_argument("--judge-hf-sha")
    p.add_argument("--ollama-host", default="http://localhost:11434")
    p.add_argument("--golden", type=Path, default=ROOT / "data" / "set5")
    args = p.parse_args(argv)

    result = tierb.run_tierb(args.golden, _build_judge(args))
    print(tierb.format_report(result))
    if result.failures:
        print(f"  FAILURES: {result.failures}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
