#!/usr/bin/env python3
"""
Task B demo — pairwise summarization with cross-vendor judging.

Demonstrates the full Task B pipeline end-to-end without real API calls:
  1. Cross-vendor judge selection routes pairs correctly
  2. Judge verdict parsing extracts VERDICT + FACTUALITY_A + FACTUALITY_B
  3. Bradley-Terry ranking aggregates pairwise verdicts into a global ranking

For a real Task B run, swap the demo judges for AnthropicAdapter + OpenAIAdapter
(both stdlib-only, in /adapters/). The select_judge / judge_pair / fit_bradley_terry
call shape stays the same.

Usage:
    python scripts/example_task_b.py
"""

import sys
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from adapters.base import Completion, SamplingParams  # noqa: E402
from eval.bradley_terry import fit_bradley_terry, rank_models  # noqa: E402
from eval.judge import is_anthropic_model, judge_pair, select_judge  # noqa: E402


class HeuristicJudge:
    """Demo judge. Preference heuristic: longer summary wins. Factuality
    heuristic: very-short summaries (<10 words) flagged 'fail' since they
    typically can't represent the source faithfully. Gives the BT + factuality
    demo non-uniform output to exercise the parser."""

    def __init__(self, model_id: str):
        self.model_id = model_id

    def complete(self, prompt: str, params: SamplingParams) -> Completion:
        a_start = prompt.find("Summary A:\n") + len("Summary A:\n")
        a_end = prompt.find("\n\nSummary B:")
        b_start = prompt.find("Summary B:\n") + len("Summary B:\n")
        b_end = prompt.find("\n\nCompare on:")
        if a_end <= a_start or b_end <= b_start:
            winner, len_a, len_b = "TIE", 0, 0
        else:
            len_a = len(prompt[a_start:a_end].split())
            len_b = len(prompt[b_start:b_end].split())
            if abs(len_a - len_b) <= 2:
                winner = "TIE"
            elif len_a > len_b:
                winner = "A"
            else:
                winner = "B"
        fact_a = "fail" if 0 < len_a < 10 else "pass"
        fact_b = "fail" if 0 < len_b < 10 else "pass"
        text = (
            f"VERDICT: {winner}\n"
            f"FACTUALITY_A: {fact_a}\n"
            f"FACTUALITY_B: {fact_b}\n"
            "Heuristic: longer summary preferred; very short summaries flagged unfaithful."
        )
        return Completion(
            text=text,
            input_tokens=len(prompt) // 4,
            output_tokens=20,
            latency_ms=1.0,
            model_id=self.model_id,
        )


def main() -> int:
    article = (
        "The Senate passed a sweeping energy bill last night that expands tax "
        "credits for renewable projects and accelerates permitting for transmission lines."
    )

    summaries = {
        "haiku-4.5":    "The Senate passed an energy bill expanding renewable tax credits and accelerating transmission permitting.",
        "sonnet-4.6":   "Last night's Senate energy bill broadens renewable tax credits and speeds up permitting for transmission infrastructure, advancing clean-energy buildout meaningfully across multiple sectors.",
        "llama-3.1-8b": "Senate passed energy bill. Tax credits. Renewables.",
        "gpt-4o-mini":  "Senators passed legislation overnight that boosts renewable energy investment via tax credits and streamlines transmission line approvals.",
    }
    candidates = list(summaries.keys())
    print(f"=== Candidates ({len(candidates)} models, 1 article) ===")
    for c in candidates:
        print(f"  {c:<14} ({len(summaries[c].split())} words): {summaries[c][:70]}...")

    sonnet_judge = HeuristicJudge("sonnet-4-6-demo")
    gpt4o_judge = HeuristicJudge("gpt-4o-demo")

    # ---- Pairwise judging ----
    print(f"\n=== Pairwise judging (C({len(candidates)},2)={len(candidates)*(len(candidates)-1)//2} pairs) ===")
    print(f"{'pair':<32} {'judge':<18} {'verdict':<8} {'fact_a':<8} {'fact_b':<8}")
    verdicts = []
    judge_counts = {"sonnet-4-6-demo": 0, "gpt-4o-demo": 0}
    for a, b in combinations(candidates, 2):
        judge = select_judge(a, b, sonnet_judge, gpt4o_judge)
        v = judge_pair(judge, article, summaries[a], summaries[b])
        verdicts.append({
            "model_a": a,
            "model_b": b,
            "winner": v.winner,
            "factuality_a": v.factuality_a,
            "factuality_b": v.factuality_b,
        })
        judge_counts[v.judge_id] += 1
        anth = "*" if (is_anthropic_model(a) or is_anthropic_model(b)) else " "
        print(f"  {anth} {a:<12} vs {b:<14} {v.judge_id:<18} {v.winner:<8} {v.factuality_a:<8} {v.factuality_b:<8}")
    print(f"\n  Judge call distribution: {judge_counts}")
    print(f"  (* marks pairs with at least one Anthropic model → routed to GPT-4o)")

    # ---- Factuality flag aggregation (per-summary fail rate) ----
    # Each model appears in (n-1) pairs as A or B. Aggregate factuality flags per model.
    fail_count = {c: 0 for c in candidates}
    appearance = {c: 0 for c in candidates}
    for v in verdicts:
        if v["factuality_a"] == "fail":
            fail_count[v["model_a"]] += 1
        if v["factuality_b"] == "fail":
            fail_count[v["model_b"]] += 1
        appearance[v["model_a"]] += 1
        appearance[v["model_b"]] += 1

    print(f"\n=== Per-model factuality fail rate ===")
    for c in candidates:
        rate = fail_count[c] / appearance[c] if appearance[c] else 0
        print(f"  {c:<14} {fail_count[c]}/{appearance[c]} ({rate*100:.0f}%)")

    # ---- Bradley-Terry ranking ----
    strengths = fit_bradley_terry(verdicts)
    print(f"\n=== Bradley-Terry ranking ===")
    for model_id, strength in rank_models(strengths):
        print(f"  {model_id:<14}: {strength:.4f}")

    # ---- Contract assertions ----
    # 1. Cross-vendor routing identifies Anthropic models correctly
    assert is_anthropic_model("haiku-4.5")
    assert is_anthropic_model("sonnet-4.6")
    assert is_anthropic_model("claude-sonnet-4-6-20260101")
    assert not is_anthropic_model("gpt-4o-mini")
    assert not is_anthropic_model("llama-3.1-8b")

    # 2. select_judge routes Anthropic-containing pairs to GPT-4o
    assert select_judge("haiku-4.5", "gpt-4o-mini", sonnet_judge, gpt4o_judge) is gpt4o_judge
    assert select_judge("llama-3.1-8b", "qwen-2.5-7b", sonnet_judge, gpt4o_judge) is sonnet_judge

    # 3. At 4 models with 2 Anthropic, expected split: 5 Anthropic-containing pairs,
    #    1 non-Anthropic pair. So GPT-4o judges 5, Sonnet judges 1.
    assert judge_counts["gpt-4o-demo"] == 5, f"expected 5 GPT-4o calls, got {judge_counts['gpt-4o-demo']}"
    assert judge_counts["sonnet-4-6-demo"] == 1, f"expected 1 Sonnet call, got {judge_counts['sonnet-4-6-demo']}"

    # 4. BT geometric mean normalized to 1
    import math
    geomean = math.exp(sum(math.log(s) for s in strengths.values() if s > 0) / len(strengths))
    assert abs(geomean - 1.0) < 1e-3, f"BT not normalized: geomean={geomean}"

    # 5. Heuristic predicts longest summary wins: sonnet-4.6 (22 words) should rank #1
    top_model, _ = rank_models(strengths)[0]
    assert top_model == "sonnet-4.6", f"expected sonnet-4.6 to win, got {top_model}"

    # 6. Factuality flags are populated by the parser (the spec-promised metric)
    for v in verdicts:
        assert v["factuality_a"] in ("pass", "fail"), f"factuality_a not parsed: {v['factuality_a']}"
        assert v["factuality_b"] in ("pass", "fail"), f"factuality_b not parsed: {v['factuality_b']}"
    # llama-3.1-8b (7 words) should be the model with factuality fails
    assert fail_count["llama-3.1-8b"] > 0, "expected llama-3.1-8b to have at least one factuality fail"
    assert fail_count["sonnet-4.6"] == 0, "expected sonnet-4.6 to have zero factuality fails"

    print(f"\nTask B pipeline OK — cross-vendor routing, verdict + factuality parsing, BT ranking all verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
