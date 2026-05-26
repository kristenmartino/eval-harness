#!/usr/bin/env python3
"""
Judge-cost budget estimator — pre-flight check for §8 of eval-harness-spec.md.

Estimates closed-weight API spend across all four tasks plus the safety smoke
test. Open-weight models contribute $0 API cost (local compute; see spec §5
for hardware-amortization methodology).

Cross-judge design from spec §2 Task B (v0.2 Edit 1):
  - Sonnet 4.6 judges non-Anthropic pairs (21 of 36 pairs at 9 models)
  - GPT-4o judges Anthropic-containing pairs (15 of 36 pairs at 9 models)

Per-task volumes match v0.2 spec. Token estimates are conservative averages.
Prices are approximate as of ~2026-01; update CLOSED_MODELS if rates shift.

Usage:
    python scripts/judge_cost_budget.py
    python scripts/judge_cost_budget.py --rpm 100 --output budget.json

No external dependencies — Python 3.9+ stdlib only.
"""

import argparse
import json
import sys
from pathlib import Path


# Closed-weight model pricing (USD per million tokens). Update if rates shift.
CLOSED_MODELS = {
    "haiku-4.5":   {"vendor": "anthropic", "input_per_mtok": 1.00, "output_per_mtok": 5.00},
    "sonnet-4.6":  {"vendor": "anthropic", "input_per_mtok": 3.00, "output_per_mtok": 15.00},
    "gpt-4o":      {"vendor": "openai",    "input_per_mtok": 2.50, "output_per_mtok": 10.00},
    "gpt-4o-mini": {"vendor": "openai",    "input_per_mtok": 0.15, "output_per_mtok": 0.60},
}

# Open-weight models contribute to volume but $0 API cost
OPEN_MODELS = ["llama-3.1-8b", "llama-3.1-70b", "qwen-2.5-7b", "qwen-2.5-14b", "deepseek-v2-lite"]

# Task definitions matching v0.2 spec
TASKS = {
    "A_categorization": {"n_items": 500, "n_samples": 1, "input_toks": 3500, "output_toks": 5},
    "B_summarization":  {"n_items": 200, "n_samples": 3, "input_toks": 3500, "output_toks": 100},
    "C_extraction":     {"n_items": 100, "n_samples": 1, "input_toks": 3500, "output_toks": 250},
    "D_rag":            {"n_items": 50,  "n_samples": 3, "input_toks": 6000, "output_toks": 200},
    "D_rag_adversarial":{"n_items": 20,  "n_samples": 1, "input_toks": 6000, "output_toks": 100},
    "safety":           {"n_items": 50,  "n_samples": 1, "input_toks": 1500, "output_toks": 100},
}

# Judge call definitions. Cross-vendor split for Task B per v0.2 Edit 1.
# 9 models, 36 pairs, 200 items → 21 non-Anthropic pairs (Sonnet judges) + 15 Anthropic pairs (GPT-4o judges)
JUDGE_CALLS = {
    "B_pairwise_sonnet":     {"n_calls": 21 * 200,       "judge": "sonnet-4.6", "input_toks": 500,  "output_toks": 200, "description": "Task B pairwise (non-Anthropic pairs)"},
    "B_pairwise_gpt4o":      {"n_calls": 15 * 200,       "judge": "gpt-4o",     "input_toks": 500,  "output_toks": 200, "description": "Task B pairwise (Anthropic pairs)"},
    "B_calibration_overlap": {"n_calls": 50,             "judge": "gpt-4o",     "input_toks": 500,  "output_toks": 200, "description": "Task B cross-judge calibration overlap (GPT-4o side; Sonnet side reuses B_pairwise_sonnet rows)"},
    "D_faithfulness_sonnet": {"n_calls": 9 * 50 * 3,     "judge": "sonnet-4.6", "input_toks": 6000, "output_toks": 300, "description": "Task D faithfulness scoring"},
    "D_adversarial_sonnet":  {"n_calls": 9 * 20,         "judge": "sonnet-4.6", "input_toks": 500,  "output_toks": 50,  "description": "Task D adversarial refusal scoring"},
    "safety_sonnet":         {"n_calls": 9 * 50,         "judge": "sonnet-4.6", "input_toks": 500,  "output_toks": 100, "description": "Safety smoke-test scoring"},
}


def cost_per_call(pricing: dict, input_toks: int, output_toks: int) -> float:
    return (input_toks * pricing["input_per_mtok"] + output_toks * pricing["output_per_mtok"]) / 1_000_000


def main() -> int:
    parser = argparse.ArgumentParser(description="Judge-cost budget estimator (§8 pre-flight).")
    parser.add_argument("--rpm", type=int, default=50,
                        help="Judge model rate-limit RPM for wall-clock estimate (default: %(default)s)")
    parser.add_argument("--output", type=Path, default=None,
                        help="Optional: write JSON breakdown to this path")
    args = parser.parse_args()

    n_closed = len(CLOSED_MODELS)
    n_total = n_closed + len(OPEN_MODELS)

    # Generation cost per task (closed models only)
    print(f"=== Generation costs ({n_closed} closed-weight; {len(OPEN_MODELS)} open contribute $0 API) ===")
    print(f"{'task':<22} {'calls/model':>12} {'closed_total':>14} {'cost':>10}")
    task_costs = {}
    total_generation_cost = 0.0
    for tname, t in TASKS.items():
        calls_per_model = t["n_items"] * t["n_samples"]
        total_calls = calls_per_model * n_closed
        per_model_costs = {}
        task_cost = 0.0
        for model, pricing in CLOSED_MODELS.items():
            cost = calls_per_model * cost_per_call(pricing, t["input_toks"], t["output_toks"])
            per_model_costs[model] = cost
            task_cost += cost
        task_costs[tname] = {"total_cost": task_cost, "calls": total_calls, "per_model": per_model_costs}
        total_generation_cost += task_cost
        print(f"  {tname:<20} {calls_per_model:>12,} {total_calls:>14,} {'$':>4}{task_cost:>6.2f}")
    print(f"  {'GENERATION TOTAL':<20} {'':<12} {'':<14} {'$':>4}{total_generation_cost:>6.2f}")

    # Judge costs
    print(f"\n=== Judge costs ===")
    print(f"{'description':<42} {'judge':<14} {'calls':>10} {'cost':>10}")
    judge_costs = {}
    total_judge_cost = 0.0
    judge_calls_total = 0
    for jname, j in JUDGE_CALLS.items():
        pricing = CLOSED_MODELS[j["judge"]]
        cost = j["n_calls"] * cost_per_call(pricing, j["input_toks"], j["output_toks"])
        judge_costs[jname] = {"cost": cost, "calls": j["n_calls"], "judge": j["judge"]}
        total_judge_cost += cost
        judge_calls_total += j["n_calls"]
        print(f"  {j['description']:<40} {j['judge']:<14} {j['n_calls']:>10,} {'$':>4}{cost:>6.2f}")
    print(f"  {'JUDGE TOTAL':<40} {'':<14} {judge_calls_total:>10,} {'$':>4}{total_judge_cost:>6.2f}")

    # Per-model spend rollup
    model_spend = {m: 0.0 for m in CLOSED_MODELS}
    for tc in task_costs.values():
        for m, c in tc["per_model"].items():
            model_spend[m] += c
    judge_models = {jc["judge"] for jc in judge_costs.values()}
    for jname, jc in judge_costs.items():
        model_spend[jc["judge"]] += jc["cost"]

    print(f"\n=== Per-model spend rollup ===")
    print(f"{'model':<14} {'role':<22} {'spend':>10}")
    for m, total in sorted(model_spend.items(), key=lambda x: -x[1]):
        roles = ["candidate"]
        if m in judge_models:
            roles.append("judge")
        print(f"  {m:<12} {','.join(roles):<22} {'$':>4}{total:>6.2f}")

    # Wall-clock estimate (judge-bound)
    judge_minutes = judge_calls_total / args.rpm
    print(f"\n=== Wall-clock estimate (judge phase, rate-limited) ===")
    print(f"Total judge calls:  {judge_calls_total:,}")
    print(f"At {args.rpm} RPM:        {judge_minutes:.1f} min ({judge_minutes/60:.1f} hours)")

    grand_total = total_generation_cost + total_judge_cost
    print(f"\n=== Grand total ===")
    print(f"Generation:  ${total_generation_cost:>8.2f}")
    print(f"Judging:     ${total_judge_cost:>8.2f}")
    print(f"TOTAL:       ${grand_total:>8.2f}")
    print(f"\nNotes:")
    print(f"  - Approximate. Update CLOSED_MODELS pricing in the script if rates have changed.")
    print(f"  - Open-weight models contribute $0 to API cost; see spec §5 for hardware amortization.")
    print(f"  - Token estimates are averages; real spend will vary ±30% depending on actual article lengths.")

    if args.output:
        report = {
            "tasks": {k: {"total_cost": v["total_cost"], "calls": v["calls"],
                          "per_model": v["per_model"]} for k, v in task_costs.items()},
            "judges": judge_costs,
            "model_spend": model_spend,
            "judge_calls_total": judge_calls_total,
            "wall_minutes_at_rpm": judge_minutes,
            "rpm_assumed": args.rpm,
            "generation_cost": total_generation_cost,
            "judge_cost": total_judge_cost,
            "grand_total": grand_total,
            "pricing_used": CLOSED_MODELS,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2))
        print(f"\nReport: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
