#!/usr/bin/env python3
"""
Category distribution check — pre-flight check for §8 of eval-harness-spec.md.

Reads a category-count table (CSV or JSON output from your SQL client),
applies the §8 decision rule (categories with <20 articles are dropped from
the eval, not upsampled), and reports stratified-sampling feasibility for
Set 1 (n=500 by default).

Usage:
    python scripts/category_distribution_check.py --input categories.csv
    python scripts/category_distribution_check.py --input categories.json --target-n 500 --min-per-category 20

Input formats:
    CSV — header row "category,count":
        category,count
        Tech,1450
        Politics,890

    JSON — array of {category, count} objects:
        [{"category": "Tech", "count": 1450}, {"category": "Politics", "count": 890}]

SQL one-liners to produce the input:
    Postgres:
        psql -d sift -A -F',' -c "\\copy (SELECT category, COUNT(*) AS count FROM articles GROUP BY category ORDER BY count DESC) TO STDOUT WITH CSV HEADER" > categories.csv

    Snowflake:
        snowsql -q "SELECT category, COUNT(*) AS count FROM articles GROUP BY category ORDER BY count DESC" -o output_format=csv -o header=true > categories.csv

    SQLite:
        sqlite3 -header -csv sift.db "SELECT category, COUNT(*) AS count FROM articles GROUP BY category ORDER BY count DESC" > categories.csv

    Add a date filter if you only want recent articles, e.g.
    `WHERE published_at > CURRENT_DATE - INTERVAL '90 days'` (Postgres)
    or equivalent.

Decision rules (§8 of spec):
  1. Any category with fewer than --min-per-category articles is dropped.
     Rationale: upsampling biases macro-F1; dropping is honest.
  2. Across kept categories, check whether each can supply ceil(target_n / kept)
     articles for an even stratified split. Categories below this threshold
     are bottlenecks.

Exit code:
  0 — PASS  (all kept categories can supply the per-category target)
  1 — PARTIAL (kept categories exist but some are bottlenecks)
  2 — FAIL  (no categories meet the minimum threshold)

No external dependencies — Python 3.9+ stdlib only.
"""

import argparse
import csv
import json
import math
import sys
from pathlib import Path


def load_input(path: Path) -> list:
    if not path.exists():
        sys.exit(f"error: input file not found: {path}")
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open() as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        if not rows:
            sys.exit("error: CSV is empty")
        if "category" not in rows[0] or "count" not in rows[0]:
            sys.exit("error: CSV must have header columns 'category' and 'count'")
        try:
            return [{"category": r["category"], "count": int(r["count"])} for r in rows]
        except (KeyError, ValueError) as e:
            sys.exit(f"error: bad CSV row: {e}")
    elif suffix == ".json":
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            sys.exit(f"error: bad JSON: {e}")
        if not isinstance(data, list):
            sys.exit("error: JSON must be an array of {category, count} objects")
        try:
            return [{"category": r["category"], "count": int(r["count"])} for r in data]
        except (KeyError, ValueError) as e:
            sys.exit(f"error: bad JSON row: {e}")
    else:
        sys.exit(f"error: input must be .csv or .json (got {path.suffix})")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Category distribution check — pre-flight check (§8 of spec)."
    )
    parser.add_argument("--input", required=True, type=Path,
                        help="CSV or JSON with category counts")
    parser.add_argument("--target-n", type=int, default=500,
                        help="Target stratified sample size for Set 1 (default: %(default)s)")
    parser.add_argument("--min-per-category", type=int, default=20,
                        help="Minimum articles required per category (default: %(default)s)")
    parser.add_argument("--output", type=Path, default=None,
                        help="Optional: write JSON report to this path")
    args = parser.parse_args()

    rows = load_input(args.input)
    if not rows:
        sys.exit("error: input has no categories")
    cats = [r["category"] for r in rows]
    if len(cats) != len(set(cats)):
        sys.exit("error: input has duplicate category names")

    rows.sort(key=lambda r: r["count"], reverse=True)
    keep = [r for r in rows if r["count"] >= args.min_per_category]
    drop = [r for r in rows if r["count"] < args.min_per_category]

    total_articles = sum(r["count"] for r in rows)
    keep_articles = sum(r["count"] for r in keep)
    drop_articles = sum(r["count"] for r in drop)

    print(f"=== Category distribution (input: {args.input}) ===")
    print(f"Categories total: {len(rows)} ({total_articles:,} articles)")
    pct_drop = (drop_articles / total_articles * 100) if total_articles else 0
    print(f"  Keep (≥{args.min_per_category}): {len(keep)} categories, {keep_articles:,} articles")
    print(f"  Drop (<{args.min_per_category}): {len(drop)} categories, {drop_articles:,} articles "
          f"({pct_drop:.1f}% of corpus)")

    print(f"\nKept categories:")
    for r in keep:
        print(f"  {r['category']:<30} {r['count']:>8,}")

    if drop:
        print(f"\nDropped categories (<{args.min_per_category} articles):")
        for r in drop:
            print(f"  {r['category']:<30} {r['count']:>8,}")

    decision = "FAIL"
    per_cat_target = None
    bottlenecks = []

    if not keep:
        print(f"\n=== FAIL — no categories meet the {args.min_per_category}-article threshold ===")
    else:
        per_cat_target = math.ceil(args.target_n / len(keep))
        print(f"\n=== Stratified-sampling feasibility (target n={args.target_n}) ===")
        print(f"Even split across {len(keep)} kept categories: {per_cat_target} articles/category")

        bottlenecks = [r for r in keep if r["count"] < per_cat_target]
        if bottlenecks:
            print(f"\nBottlenecks (cannot supply {per_cat_target} articles):")
            for r in bottlenecks:
                deficit = per_cat_target - r["count"]
                print(f"  {r['category']:<30} {r['count']:>8,}  (deficit: {deficit})")

            max_balanced = min(r["count"] for r in keep) * len(keep)
            print(f"\nMax fully-balanced n across kept categories: {max_balanced:,}")
            print(f"Options:")
            print(f"  (a) reduce target_n to {max_balanced} for a balanced sample")
            print(f"  (b) drop the {len(bottlenecks)} bottleneck categories and re-run "
                  f"(would leave {len(keep) - len(bottlenecks)} categories)")
            print(f"  (c) accept an unbalanced sample — flag this in the leaderboard methodology")
            decision = "PARTIAL"
        else:
            print(f"\nPASS — all {len(keep)} kept categories can supply ≥{per_cat_target} articles "
                  f"for stratified n={args.target_n}")
            decision = "PASS"

    if args.output:
        report = {
            "input": str(args.input),
            "min_per_category": args.min_per_category,
            "target_n": args.target_n,
            "categories_total": len(rows),
            "articles_total": total_articles,
            "categories_kept": [{"category": r["category"], "count": r["count"]} for r in keep],
            "categories_dropped": [{"category": r["category"], "count": r["count"]} for r in drop],
            "decision": decision,
            "per_category_target": per_cat_target,
            "bottlenecks": [r["category"] for r in bottlenecks],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2))
        print(f"\nReport written: {args.output}")

    return {"PASS": 0, "PARTIAL": 1, "FAIL": 2}[decision]


if __name__ == "__main__":
    sys.exit(main())
