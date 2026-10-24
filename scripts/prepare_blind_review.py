#!/usr/bin/env python3
"""Create a blind reviewer packet and a physically separate operator key."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import secrets
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from eval.blind_review import prepare_review


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_rows(path, rows):
    with path.open("x") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample-matches", type=int, default=81)
    args = parser.parse_args()
    root = args.root.resolve()
    base = root / "data/private/sift-pull-2026-10-24"
    corpus = json.loads((base / "corpus_manifest.json").read_text())
    run = json.loads((root / "results/llama31_8b_q4_A_dev_20261024.run.json").read_text())
    dev = Path(corpus["dev"]["path"])
    held = Path(corpus["holdout"]["path"])
    lock = root / "data/set1_20261024.holdout.sha256"
    results = root / "results/llama31_8b_q4_A_dev_20261024.jsonl"
    taxonomy_file = root / "data/set1_20261024.categories.json"
    if dev.resolve().parent != (root / "data/dev").resolve():
        raise ValueError("only the frozen development input is allowed")
    before = {"holdout_dataset": sha(held), "holdout_lock": sha(lock)}
    if before["holdout_dataset"] != corpus["holdout"]["sha256"]:
        raise ValueError("protected holdout hash changed")
    if sha(dev) != corpus["dev"]["sha256"] or sha(results) != run["results_sha256"]:
        raise ValueError("frozen development inputs or run results changed")
    seed = secrets.randbits(128)
    reviewer, key, selection = prepare_review(read_rows(dev), read_rows(results),
                                            sample_matches=args.sample_matches, seed=seed)
    if selection["development_n"] != 400 or selection["disagreements_selected"] != 81:
        raise ValueError("expected the 400-item run and all 81 disagreements")
    root_out = args.output.resolve()
    if not root_out.is_relative_to((root / "data/private").resolve()):
        raise ValueError("review packets contain source text and must stay in data/private")
    reviewer_dir = root_out / "reviewer"
    operator_dir = root_out / "operator"
    reviewer_dir.mkdir(parents=True, exist_ok=False)
    operator_dir.mkdir(parents=True, exist_ok=False)
    operator_dir.chmod(0o700)
    write_rows(reviewer_dir / "review_items.jsonl", reviewer)
    taxonomy = json.loads(taxonomy_file.read_text())
    (reviewer_dir / "rubric.json").write_text(json.dumps(taxonomy, indent=2) + "\n")
    write_rows(operator_dir / "operator_key.jsonl", key)
    (operator_dir / "operator_key.jsonl").chmod(0o600)
    after = {"holdout_dataset": sha(held), "holdout_lock": sha(lock)}
    assert before == after
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
        "selection": selection, "development_sha256": sha(dev), "results_sha256": sha(results),
        "taxonomy_sha256": sha(taxonomy_file), "review_items_sha256": sha(reviewer_dir / "review_items.jsonl"),
        "operator_key_sha256": sha(operator_dir / "operator_key.jsonl"),
        "protected_before": before, "protected_after": after,
        "holdout_text_loaded": False, "holdout_rows_selected": 0,
        "reviewer_fields": list(reviewer[0]),
        "separation": "Only files under reviewer/ may be supplied to a reviewer. Never bundle operator/.",
    }
    (operator_dir / "selection_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (operator_dir / "analysis_instructions.md").write_text(
        "# Operator only\n\nKeep this folder away from reviewers until their labels are frozen.\n\n"
        f"The packet contains all 81 disagreements and a simple random sample of {args.sample_matches} of 319 matches. "
        f"Use stratum weights 1 for disagreements and 319/{args.sample_matches} for sampled matches when estimating totals "
        "over the 400 development items. Keep uncertain/insufficient cases visible; do not silently drop them. "
        "An unweighted average over this balanced packet is not an estimate for all 400 items.\n\n"
        "Join completed labels by review_id after review is locked. Preserve original and human labels "
        "separately. A second independent pass should use the same reviewer files with blank fields, "
        "without sharing the first reviewer’s answers. The 100-item holdout is not part of this review.\n")
    (reviewer_dir / "README.md").write_text(
        "# Sift categorization review\n\nOpen review.xlsx. The Review sheet has the annotation fields; "
        "the article links open the exact supplied source text in Articles. Rubric contains all eleven "
        "categories and routing rules. Review each item independently using only its supplied text. "
        "Do not use the Sift site, prior run reports, or reference labels to decide a category.\n\n"
        "Enter a human category, confidence (high/medium/low), status, and a short evidence-based rationale. "
        "Use reviewed only when category, confidence, and rationale are present. Use needs_adjudication "
        "for an unresolved category boundary and list an alternative if useful. Use insufficient_text "
        "when the input cannot support a defensible label; leave the category blank if necessary. "
        "Do not force a guess. High means the supplied text clearly fits the rule; medium means a "
        "plausible alternative remains; low means sparse or ambiguous evidence.\n\n"
        "Review IDs must stay unchanged. Save the completed workbook and return it. The packet contains "
        f"{len(reviewer)} randomly ordered development items; model outputs, stored labels, original IDs, sampling "
        "groups, and analysis weights are absent. No held-out item is included.\n")
    print(json.dumps({"review_n": len(reviewer), "disagreements": selection["disagreements_selected"],
                      "matches": selection["matches_selected"], "reviewer_directory": str(reviewer_dir),
                      "operator_directory": str(operator_dir), "holdout_unchanged": before == after}, indent=2))


if __name__ == "__main__":
    main()
