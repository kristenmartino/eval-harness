#!/usr/bin/env python3
"""
70B timing benchmark — pre-flight check for §8 of eval-harness-spec.md.

Measures Llama 3.1 70B Q4 throughput on Sift-representative articles via
Ollama on DGX Spark.

Decision rule (§3 of spec): if median generation throughput < 8 tok/s,
70B stays as quality-ceiling reference only (excluded from deployment
cost view). Exit code 0 = pass, 1 = fail.

Usage:
    python scripts/preflight_70b_timing.py --articles articles.jsonl
    python scripts/preflight_70b_timing.py --articles articles.jsonl --model llama3.1:70b-instruct-q4_0

Input JSONL format — one article per line:
    {"text": "<full article body>"}
    {"text": "<full article body>", "length_bucket": "p50"}
    ...

25 articles recommended (matches §8 spec), length-stratified across Sift's
article-length distribution (~5 each at the p10/p25/p50/p75/p90 input-length
percentiles). The first article is treated as warm-up and excluded from
aggregates; cold-start time is reported separately.

Optional per-row field "length_bucket" (any string label, e.g. "p50") triggers
per-bucket median tok/s reporting in the summary. If absent, only flat
aggregates are reported.

No external dependencies — Python 3.9+ stdlib only.
"""

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


SUMMARIZE_PROMPT = """You are summarizing a news article for a daily digest.

Article:
{article}

Write a concise 2-3 sentence summary (≤60 words) capturing the article's key points. Output only the summary, no preamble."""

DECISION_THRESHOLD_TPS = 8.0


def call_ollama(host: str, model: str, prompt: str, timeout: float = 600.0) -> dict:
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(
        f"{host}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def measure_article(host: str, model: str, article_text: str) -> dict:
    prompt = SUMMARIZE_PROMPT.format(article=article_text)
    wall_start = time.perf_counter()
    result = call_ollama(host, model, prompt)
    wall_elapsed = time.perf_counter() - wall_start

    prompt_tokens = result.get("prompt_eval_count", 0)
    prompt_ns = result.get("prompt_eval_duration", 0)
    output_tokens = result.get("eval_count", 0)
    output_ns = result.get("eval_duration", 0)

    prefill_tps = prompt_tokens / (prompt_ns / 1e9) if prompt_ns > 0 else None
    generation_tps = output_tokens / (output_ns / 1e9) if output_ns > 0 else None

    return {
        "wall_seconds": round(wall_elapsed, 3),
        "input_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "prefill_tps": round(prefill_tps, 2) if prefill_tps else None,
        "generation_tps": round(generation_tps, 2) if generation_tps else None,
        "output_text": result.get("response", "").strip(),
    }


def percentile(values: list, pct: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (pct / 100)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def load_articles(path: Path) -> list:
    if not path.exists():
        sys.exit(f"error: articles file not found: {path}")
    articles = []
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
            articles.append({
                "text": row["text"],
                "length_bucket": row.get("length_bucket"),
            })
    return articles


def main() -> int:
    parser = argparse.ArgumentParser(
        description="70B timing benchmark — pre-flight check (§8 of spec)."
    )
    parser.add_argument("--articles", required=True, type=Path,
                        help="JSONL with {'text': ...} (and optional 'length_bucket') per line; 25 recommended")
    parser.add_argument("--model", default="llama3.1:70b-instruct-q4_0",
                        help="Ollama model tag (default: %(default)s)")
    parser.add_argument("--host", default="http://localhost:11434",
                        help="Ollama server URL (default: %(default)s)")
    parser.add_argument("--output", type=Path,
                        default=Path("results/preflight_70b_results.jsonl"),
                        help="Per-article timings JSONL (default: %(default)s)")
    args = parser.parse_args()

    articles = load_articles(args.articles)
    if len(articles) < 2:
        sys.exit(f"error: need ≥2 articles (got {len(articles)}); 25 recommended")

    bucketed = sum(1 for a in articles if a["length_bucket"])
    print(f"Model:    {args.model}")
    print(f"Host:     {args.host}")
    print(f"Articles: {len(articles)} ({bucketed} with length_bucket; "
          f"first is warm-up, excluded from aggregates)")
    print(f"Output:   {args.output}\n")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    with args.output.open("w") as out:
        for i, article in enumerate(articles):
            text = article["text"]
            bucket = article["length_bucket"]
            label = "warmup" if i == 0 else f"article_{i}"
            label_suffix = f" [{bucket}]" if bucket else ""
            print(f"[{i+1}/{len(articles)}] {label}{label_suffix}: ", end="", flush=True)
            try:
                metrics = measure_article(args.host, args.model, text)
            except urllib.error.URLError as e:
                sys.exit(
                    f"\nerror: Ollama request failed on {label}: {e}\n"
                    f"check that Ollama is running at {args.host} and "
                    f"model '{args.model}' is pulled (`ollama pull {args.model}`)."
                )
            metrics["index"] = i
            metrics["is_warmup"] = (i == 0)
            metrics["model"] = args.model
            metrics["length_bucket"] = bucket
            print(
                f"wall={metrics['wall_seconds']}s "
                f"in={metrics['input_tokens']}toks "
                f"out={metrics['output_tokens']}toks "
                f"gen={metrics['generation_tps']}tok/s"
            )
            out.write(json.dumps(metrics) + "\n")
            rows.append(metrics)

    measured = [r for r in rows if not r["is_warmup"] and r["generation_tps"] is not None]
    if not measured:
        sys.exit("error: no measurable rows after warm-up; cannot apply decision rule")

    wall = [r["wall_seconds"] for r in measured]
    gen_tps = [r["generation_tps"] for r in measured]
    prefill_tps = [r["prefill_tps"] for r in measured if r["prefill_tps"] is not None]

    median_gen = statistics.median(gen_tps)
    p50_wall = percentile(wall, 50)
    p95_wall = percentile(wall, 95)

    print("\n=== Summary (excluding warm-up) ===")
    print(f"Measured articles:           {len(measured)}")
    print(f"Wall-clock p50 / p95:        {p50_wall:.2f}s / {p95_wall:.2f}s")
    print(f"Generation tok/s (median):   {median_gen:.2f}")
    if prefill_tps:
        print(f"Prefill tok/s (median):      {statistics.median(prefill_tps):.2f}")
    print(f"Cold-start wall (article 1): {rows[0]['wall_seconds']}s")

    buckets = {r.get("length_bucket") for r in measured if r.get("length_bucket")}
    if buckets:
        print("\n=== Per-length-bucket generation tok/s (median) ===")
        for bucket in sorted(buckets):
            bucket_rows = [r for r in measured if r.get("length_bucket") == bucket]
            bucket_med = statistics.median(r["generation_tps"] for r in bucket_rows)
            bucket_p95_wall = percentile([r["wall_seconds"] for r in bucket_rows], 95)
            print(f"  {bucket:>6}: {bucket_med:.2f} tok/s, "
                  f"wall p95 {bucket_p95_wall:.2f}s (n={len(bucket_rows)})")

    print(f"\n=== Decision (§3 rule, threshold {DECISION_THRESHOLD_TPS} tok/s) ===")
    if median_gen >= DECISION_THRESHOLD_TPS:
        print(f"PASS — median generation {median_gen:.2f} ≥ {DECISION_THRESHOLD_TPS} tok/s")
        print("70B remains eligible for deployment cost view.")
        return 0
    else:
        print(f"FAIL — median generation {median_gen:.2f} < {DECISION_THRESHOLD_TPS} tok/s")
        print("70B stays as quality-ceiling reference only (per §3 tier split).")
        return 1


if __name__ == "__main__":
    sys.exit(main())
