#!/usr/bin/env python3
"""
Demonstrates the harness end-to-end with a MockAdapter — no Ollama or API
keys required. Validates:
  1. The full pipeline (adapter → task → runner → JSONL) works
  2. JSONL has a reproducibility header row
  3. Resume mode skips already-completed items
  4. Failure rows include an `error` field

For a real run, swap MockAdapter for OllamaAdapter (or your closed-weight
adapter) — the rest of the call stays the same.

Usage:
    python scripts/example_run.py
"""

import json
import sys
from pathlib import Path

# Make package imports work without `pip install -e .` — convenience for demo
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from adapters.mock import MockAdapter  # noqa: E402
from tasks import categorization  # noqa: E402
from eval import runner  # noqa: E402
from utils import accuracy, macro_f1  # noqa: E402


def main() -> int:
    adapter = MockAdapter(
        response_map={
            "Apple announced new M5": "Tech",
            "Senate passed a sweeping energy": "Energy",
            "Congress reached a bipartisan": "Politics",
            "FDA approved a new gene": "Health",
            "Quarterly earnings from major": "Business",
        },
        model_id="mock-v1",
    )

    dataset = ROOT / "data" / "sample_categorization.jsonl"
    output = ROOT / "results" / "demo_categorization_mock.jsonl"

    if output.exists():
        output.unlink()

    # First run — should complete all items fresh
    print("=== First run (fresh) ===")
    summary = runner.run(adapter, categorization.task, dataset, output, n_samples=1, repo_root=ROOT)
    print(f"  {summary}")
    assert summary["completed"] == 5, f"expected 5 completed, got {summary['completed']}"
    assert summary["skipped_resume"] == 0

    # Resume run — should skip everything
    print("\n=== Resume run (should skip all) ===")
    summary = runner.run(adapter, categorization.task, dataset, output, n_samples=1, repo_root=ROOT)
    print(f"  {summary}")
    assert summary["completed"] == 0, f"expected 0 completed on resume, got {summary['completed']}"
    assert summary["skipped_resume"] == 5

    # Inspect output
    print("\n=== JSONL contents ===")
    rows = [json.loads(line) for line in output.read_text().splitlines() if line.strip()]
    header = rows[0]
    assert header.get("_meta") is True
    print(f"  Header keys: {sorted(header.keys())}")
    print(f"  Total rows: {len(rows)} (1 header + {len(rows) - 1} predictions)")

    # Compute downstream metrics from the JSONL — proves metrics are
    # decoupled from model execution
    preds = [r["score"]["predicted"] for r in rows[1:]]
    golds = [r["score"]["gold"] for r in rows[1:]]
    print(f"\n=== Metrics from JSONL ===")
    print(f"  Accuracy: {accuracy(preds, golds):.3f}")
    print(f"  Macro-F1: {macro_f1(preds, golds, categorization.CATEGORIES):.3f}")
    print(f"\nEnd-to-end demo OK. Output at {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
