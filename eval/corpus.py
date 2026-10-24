"""Deterministic, duplicate-free sampling for a first categorization baseline."""

from collections import Counter, defaultdict
import hashlib
import math


def prepare_categorization(records, *, target_n=500, min_per_category=20,
                           holdout_fraction=0.2, seed=20261024):
    if target_n < 1 or min_per_category < 2 or not 0 < holdout_fraction < 1:
        raise ValueError("invalid sample size, category minimum, or holdout fraction")
    unique = []
    seen_ids, seen_urls, seen_content = set(), set(), set()
    for row in records:
        if not all(isinstance(row.get(k), str) and row[k].strip()
                   for k in ("id", "text", "category", "source_url", "content_sha256")):
            raise ValueError("each record needs id, text, category, source_url, content_sha256")
        if row["id"] in seen_ids or row["source_url"] in seen_urls or row["content_sha256"] in seen_content:
            continue
        unique.append(row)
        seen_ids.add(row["id"])
        seen_urls.add(row["source_url"])
        seen_content.add(row["content_sha256"])
    counts = Counter(row["category"] for row in unique)
    kept = sorted(cat for cat, n in counts.items() if n >= min_per_category)
    if not kept or target_n < len(kept) * min_per_category:
        raise ValueError("target sample cannot support the minimum for every eligible category")
    total = sum(counts[cat] for cat in kept)
    if total < target_n:
        raise ValueError(f"only {total} eligible unique inputs; requested {target_n}")
    quotas = {cat: min_per_category for cat in kept}
    while sum(quotas.values()) < target_n:
        cat = max((c for c in kept if quotas[c] < counts[c]),
                  key=lambda c: (target_n * counts[c] / total - quotas[c], c))
        quotas[cat] += 1
    n_holdout = round(target_n * holdout_fraction)
    held = {cat: max(1, min(quotas[cat] - 1, math.floor(quotas[cat] * holdout_fraction)))
            for cat in kept}
    while sum(held.values()) < n_holdout:
        cat = max((c for c in kept if held[c] < quotas[c] - 1),
                  key=lambda c: (quotas[c] * holdout_fraction - held[c], c))
        held[cat] += 1
    if sum(held.values()) != n_holdout:
        raise ValueError("holdout fraction cannot give each category both dev and holdout support")
    by_cat = defaultdict(list)
    for row in unique:
        by_cat[row["category"]].append(row)
    dev, holdout = [], []
    for cat in kept:
        ordered = sorted(by_cat[cat], key=lambda row: hashlib.sha256(
            f"{seed}:{row['id']}".encode()).hexdigest())[:quotas[cat]]
        holdout.extend(ordered[:held[cat]])
        dev.extend(ordered[held[cat]:])
    return dev, holdout, {
        "seed": seed, "target_n": target_n, "holdout_fraction": holdout_fraction,
        "min_per_category": min_per_category, "input_records": len(records),
        "unique_records": len(unique), "duplicate_records_removed": len(records) - len(unique),
        "eligible_labels": kept, "available_counts": dict(sorted(counts.items())),
        "excluded_categories": {c: n for c, n in sorted(counts.items()) if c not in kept},
        "selected_counts": quotas, "dev_counts": {c: quotas[c] - held[c] for c in kept},
        "holdout_counts": held,
    }
