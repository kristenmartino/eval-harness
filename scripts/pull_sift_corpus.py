#!/usr/bin/env python3
"""Match original Sift RSS captures to a read-only production-label snapshot.

Run with Sift's Python environment from its project root. No summaries are used
as classifier input. Article data is saved only to gitignored paths. The labels
are existing model-assigned production labels, not independently reviewed gold.
"""

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from eval.corpus import prepare_categorization
from eval.runner import _canonical_bytes, _holdout_aggregate


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


async def pull(args):
    sys.path.insert(0, str(args.sift_root.resolve()))
    import asyncpg
    from dotenv import dotenv_values
    from services.rss import compute_content_hash
    from services.summarizer import VALID_CATEGORIES, _build_prompt, _truncate

    inputs = []
    for source in args.capture:
        for line in source.read_text().splitlines():
            if line.strip():
                inputs.append((source, json.loads(line)))
    config = dotenv_values(args.sift_root / ".env")
    connection = await asyncpg.connect(config["DATABASE_URL"], ssl="require", timeout=30,
        server_settings={"default_transaction_read_only": "on", "statement_timeout": "30000",
                         "application_name": "eval_harness_corpus_export"})
    try:
        async with connection.transaction(isolation="repeatable_read", readonly=True):
            snapshot_at = str(await connection.fetchval("SELECT transaction_timestamp()"))
            rows = await connection.fetch(
                "SELECT id,source_url,title,category,published_date,content_hash FROM articles "
                "WHERE from_search=false AND source_url=ANY($1::text[])",
                sorted({row["source_url"] for _, row in inputs}))
            distribution = await connection.fetch(
                "SELECT category,count(*) AS count FROM articles WHERE from_search=false "
                "GROUP BY category ORDER BY category")
    finally:
        await connection.close()
    by_url = {row["source_url"]: row for row in rows}
    rejected = Counter()
    corpus = []
    normalize = lambda value: " ".join(html.unescape(value or "").split()).casefold()
    for source, row in inputs:
        stored = by_url.get(row["source_url"])
        if stored is None:
            rejected["not_in_production_feed"] += 1
            continue
        if normalize(row["title"]) != normalize(stored["title"]):
            rejected["source_title_changed"] += 1
            continue
        if stored["category"] not in VALID_CATEGORIES:
            rejected["outside_current_taxonomy"] += 1
            continue
        body = re.sub(r"<[^>]+>", "", row.get("raw_content", "")).strip()
        if not body or normalize(body) == normalize(row["title"]):
            rejected["no_source_body"] += 1
            continue
        body = _truncate(body, 500)
        corpus.append({
            "id": stored["id"], "category": stored["category"],
            "text": f"Title: {row['title']}\nSource: {row['source_name']}\nContent: {body}",
            "source_url": row["source_url"], "source_name": row["source_name"],
            "published_date": stored["published_date"].isoformat() if stored["published_date"] else None,
            "input_capture_file": str(source),
            "content_sha256": compute_content_hash(row["title"], row["raw_content"]),
            "label_provenance": "Sift production category; model-assigned, not human-validated",
        })
    dev, held, selection = prepare_categorization(corpus, target_n=args.target_n, seed=args.seed)
    dev_path = ROOT / "data/dev/set1_20261024.jsonl"
    held_path = ROOT / "data/holdout/set1_20261024.jsonl"
    lock_path = ROOT / "data/set1_20261024.holdout.sha256"
    config_path = ROOT / "data/set1_20261024.categories.json"
    manifest_path = args.output / "corpus_manifest.json"
    for path in (dev_path, held_path, lock_path, config_path, manifest_path):
        if path.exists():
            raise ValueError(f"refusing to overwrite existing artifact: {path}")
    # Use the production category definitions, keeping the full output taxonomy.
    prompt = _build_prompt([])
    instructions = prompt.split("Also classify each article into exactly ONE category:\n", 1)[1]
    instructions = instructions.split("\nRules about people and legal matters", 1)[0].strip()
    taxonomy = {"categories": sorted(VALID_CATEGORIES), "instructions": instructions}
    args.output.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output / "matched_corpus.jsonl", corpus)
    write_jsonl(dev_path, dev)
    write_jsonl(held_path, held)
    config_path.write_text(json.dumps(taxonomy, indent=2) + "\n")
    lock = {"schema": "holdout-lock/v1", "dataset_file": str(held_path.relative_to(ROOT)),
            "n_items": len(held), "aggregate_sha256": _holdout_aggregate(held),
            "item_sha256": sorted(hashlib.sha256(_canonical_bytes(row)).hexdigest() for row in held),
            "note": "Reserved before model evaluation; labels are unvalidated production categories."}
    lock_path.write_text(json.dumps(lock, indent=2) + "\n")
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(), "database_snapshot_at": snapshot_at,
        "input_source": "original RSS title/source/body; HTML stripped, body capped at 500 words as in Sift",
        "label_source": "existing production model labels; no independent correctness claim",
        "sift_git_sha": subprocess.check_output(["git", "-C", str(args.sift_root), "rev-parse", "HEAD"], text=True).strip(),
        "captures": [{"path": str(path), "sha256": sha(path)} for path in args.capture],
        "source_code_sha256": {name: sha(args.sift_root / name) for name in ("services/rss.py", "services/summarizer.py")},
        "production_category_counts": [dict(row) for row in distribution],
        "rejected_inputs": dict(rejected), "selection": selection,
        "dev": {"path": str(dev_path), "n": len(dev), "sha256": sha(dev_path)},
        "holdout": {"path": str(held_path), "n": len(held), "sha256": sha(held_path),
                    "aggregate_sha256": lock["aggregate_sha256"]},
        "taxonomy": {"path": str(config_path), "sha256": sha(config_path)},
        "metric_label_space": selection["eligible_labels"],
        "scope": "development agreement baseline; reserved holdout is not evaluated",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"selection": selection, "rejected_inputs": dict(rejected),
                      "manifest": str(manifest_path)}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sift-root", type=Path, required=True)
    parser.add_argument("--capture", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-n", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20261024)
    asyncio.run(pull(parser.parse_args()))


if __name__ == "__main__":
    main()
