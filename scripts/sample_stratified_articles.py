#!/usr/bin/env python3
"""
Stratified article sampler — prepares articles.jsonl for preflight_70b_timing.py.

Reads a corpus of articles, identifies the p10/p25/p50/p75/p90 input-length
percentiles (using character count as a proxy for input tokens — we need
relative ordering, not exact token counts), and samples N articles closest
to each percentile target.

Output is suitable as input to preflight_70b_timing.py — each row carries a
'length_bucket' field that the timing script uses for per-bucket aggregates.

Usage:
    python scripts/sample_stratified_articles.py --corpus corpus.jsonl --output articles.jsonl
    python scripts/sample_stratified_articles.py --corpus corpus.jsonl --output articles.jsonl --per-bucket 5 --seed 42

Input corpus.jsonl format — one article per line:
    {"text": "<article body>"}
    {"text": "<article body>", "id": "abc", "title": "..."}   # extra fields preserved

Building corpus.jsonl from Sift (one-liner examples for common backends):
    Postgres:
        psql -d sift -At -c "SELECT json_build_object('id', id, 'text', body) FROM articles WHERE published_at > NOW() - INTERVAL '90 days'" > corpus.jsonl

    Snowflake:
        snowsql -q "SELECT OBJECT_CONSTRUCT('id', id, 'text', body) FROM articles" -o output_format=jsonl > corpus.jsonl

    Directory of .txt files:
        for f in articles/*.txt; do python -c "import json,sys; print(json.dumps({'id': sys.argv[1], 'text': open(sys.argv[1]).read()}))" "$f"; done > corpus.jsonl

Output: per-bucket × bucket-count articles (default 5 × 5 = 25). First row
in the output (closest to p10) becomes warm-up in the timing benchmark.

No external dependencies — Python 3.9+ stdlib only.
"""

import argparse
import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path


PERCENTILES = [10, 25, 50, 75, 90]


def percentile_value(sorted_values: list, pct: float) -> float:
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * (pct / 100)
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


def load_corpus(path: Path) -> list:
    if not path.exists():
        sys.exit(f"error: corpus file not found: {path}")
    rows = []
    with path.open() as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                sys.exit(f"error: bad JSONL on line {i}: {e}")
            if "text" not in row or not isinstance(row["text"], str):
                sys.exit(f"error: line {i} missing string 'text' field")
            rows.append(row)
    return rows


def sample_stratified(corpus: list, percentiles: list, per_bucket: int,
                      rng: random.Random) -> tuple:
    needed = per_bucket * len(percentiles)
    if len(corpus) < needed:
        sys.exit(
            f"error: corpus has {len(corpus)} articles, need at least {needed} "
            f"for {len(percentiles)} buckets × {per_bucket} each"
        )

    annotated = [(i, len(row["text"]), row) for i, row in enumerate(corpus)]
    sorted_lens = sorted(a[1] for a in annotated)
    targets = {pct: percentile_value(sorted_lens, pct) for pct in percentiles}

    selected = set()
    output = []
    for pct in percentiles:
        target = targets[pct]
        candidates = [a for a in annotated if a[0] not in selected]
        candidates.sort(key=lambda a: (abs(a[1] - target), rng.random()))
        for idx, length, row in candidates[:per_bucket]:
            selected.add(idx)
            new_row = dict(row)
            new_row["length_bucket"] = f"p{pct}"
            new_row["_source_char_length"] = length
            output.append(new_row)

    return output, targets


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stratified article sampler for §8 timing benchmark."
    )
    parser.add_argument("--corpus", required=True, type=Path,
                        help="Input JSONL with {'text': ...} per line; extra fields preserved")
    parser.add_argument("--output", required=True, type=Path,
                        help="Output JSONL with stratified articles + length_bucket field")
    parser.add_argument("--per-bucket", type=int, default=5,
                        help="Articles per percentile bucket (default: %(default)s)")
    parser.add_argument("--seed", type=int, default=42,
                        help="RNG seed for tie-breaking (default: %(default)s)")
    args = parser.parse_args()

    corpus = load_corpus(args.corpus)
    needed = args.per_bucket * len(PERCENTILES)
    if len(corpus) < needed:
        sys.exit(f"error: corpus has {len(corpus)} articles; need ≥{needed} for stratified sample")

    rng = random.Random(args.seed)
    sampled, targets = sample_stratified(corpus, PERCENTILES, args.per_bucket, rng)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as out:
        for row in sampled:
            out.write(json.dumps(row) + "\n")

    char_lens = [len(r["text"]) for r in corpus]
    print(f"Corpus size:        {len(corpus)} articles")
    print(f"Char-length range:  {min(char_lens):,} – {max(char_lens):,} "
          f"(median {int(statistics.median(char_lens)):,})")
    print(f"\nTarget char length per bucket:")
    for pct in PERCENTILES:
        print(f"  p{pct:<2}  →  {targets[pct]:>8,.0f}")

    bucket_lengths = defaultdict(list)
    for row in sampled:
        bucket_lengths[row["length_bucket"]].append(row["_source_char_length"])
    print(f"\nActual sampled buckets:")
    for bucket in sorted(bucket_lengths.keys(), key=lambda b: int(b[1:])):
        lens = bucket_lengths[bucket]
        print(f"  {bucket:>4}: median={int(statistics.median(lens)):>7,}, "
              f"range=[{min(lens):,}, {max(lens):,}], n={len(lens)}")

    print(f"\nWrote {len(sampled)} articles → {args.output}")
    print(f"Next:  python scripts/preflight_70b_timing.py --articles {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
