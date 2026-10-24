"""Prepare development-only annotation packets with a separate operator key."""

import hashlib
import random


REVIEW_FIELDS = ("review_id", "article_input", "human_category", "confidence",
                 "review_status", "alternative_category", "rationale")


def prepare_review(development, results, *, sample_matches=81, seed):
    headers = [r for r in results if r.get("_meta")]
    if len(headers) != 1 or headers[0].get("held_out") is not False:
        raise ValueError("one explicit development-run header is required")
    header = headers[0]
    if header.get("task") != "A_categorization" or header.get("n_samples") != 1:
        raise ValueError("a single-sample categorization run is required")
    source = {r["id"]: r for r in development}
    if len(source) != len(development) or not source:
        raise ValueError("development input IDs must be unique and nonempty")
    rows = [r for r in results if not r.get("_meta")]
    if len({r.get("item_id") for r in rows}) != len(rows):
        raise ValueError("duplicate result IDs")
    if {r.get("item_id") for r in rows} != set(source):
        raise ValueError("result IDs must exactly cover the development dataset")
    matches, disagreements = [], []
    by_id = {}
    for row in rows:
        item = source[row["item_id"]]
        score = row.get("score", {})
        if "error" in row or score.get("parse_failed") is not False or not score.get("predicted"):
            raise ValueError("review requires a complete run with parseable predictions")
        if row.get("model_id") != header.get("model_id") or row.get("sample_idx") != 0:
            raise ValueError("mixed model identity or sample index")
        if score.get("gold") != item["category"]:
            raise ValueError("stored label differs from the frozen development input")
        same = score["predicted"] == item["category"]
        if score.get("correct") is not same:
            raise ValueError("inconsistent correctness flag")
        if not isinstance(item.get("text"), str) or not item["text"].strip():
            raise ValueError("missing original input text")
        (matches if same else disagreements).append(item["id"])
        by_id[item["id"]] = row
    if not isinstance(sample_matches, int) or not 1 <= sample_matches <= len(matches):
        raise ValueError("match sample must be between one and the available match count")
    selection_rng = random.Random(seed)
    sampled_matches = selection_rng.sample(sorted(matches), sample_matches)
    selected = sorted(disagreements) + sampled_matches
    order_seed = int(hashlib.sha256(f"{seed}:review-order".encode()).hexdigest(), 16)
    random.Random(order_seed).shuffle(selected)
    match_set = set(sampled_matches)
    reviewer, key = [], []
    for index, item_id in enumerate(selected, 1):
        review_id = f"REV-{index:03d}"
        reviewer.append({"review_id": review_id, "article_input": source[item_id]["text"],
                         "human_category": "", "confidence": "", "review_status": "not_started",
                         "alternative_category": "", "rationale": ""})
        is_match = item_id in match_set
        population = len(matches) if is_match else len(disagreements)
        count = sample_matches if is_match else len(disagreements)
        key.append({"review_id": review_id, "item_id": item_id,
                    "stored_category": source[item_id]["category"],
                    "model_prediction": by_id[item_id]["score"]["predicted"],
                    "stratum": "match" if is_match else "disagreement",
                    "stratum_population": population, "stratum_sample": count,
                    "inclusion_probability": count / population,
                    "population_weight": population / count})
    return reviewer, key, {
        "development_n": len(development), "disagreement_population": len(disagreements),
        "match_population": len(matches), "disagreements_selected": len(disagreements),
        "matches_selected": sample_matches, "review_n": len(reviewer), "seed": seed,
        "randomization": "Python random.Random; sorted match IDs, sample without replacement; independent mixed-order shuffle",
        "sampling_fraction": {"disagreement": 1.0, "match": sample_matches / len(matches)},
        "analysis": "Report strata separately or use inverse inclusion weights for the 400-item development population. Do not report an unweighted review-set average as population accuracy.",
    }


def validate_annotations(rows, expected_ids, categories):
    """Check a returned packet without revealing reference or model labels."""
    errors = []
    ids = [r.get("review_id") for r in rows]
    if len(ids) != len(set(ids)):
        errors.append("duplicate review IDs")
    if set(ids) != set(expected_ids):
        errors.append("review IDs must cover the packet exactly")
    for row in rows:
        rid = row.get("review_id", "missing ID")
        status = row.get("review_status")
        if status not in ("reviewed", "needs_adjudication", "insufficient_text"):
            errors.append(f"{rid}: review is incomplete")
        if not isinstance(row.get("rationale"), str) or not row["rationale"].strip():
            errors.append(f"{rid}: rationale required")
        label = row.get("human_category", "")
        if label and label not in categories:
            errors.append(f"{rid}: unknown human category")
        alternative = row.get("alternative_category", "")
        if alternative and (alternative not in categories or alternative == label):
            errors.append(f"{rid}: alternative category must be valid and different")
        if status == "reviewed" and (label not in categories or row.get("confidence") not in ("high", "medium", "low")):
            errors.append(f"{rid}: reviewed rows require category and confidence")
        if status == "needs_adjudication" and row.get("confidence") not in ("high", "medium", "low"):
            errors.append(f"{rid}: confidence required for adjudication")
    return errors
