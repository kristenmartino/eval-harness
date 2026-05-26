#!/usr/bin/env python3
"""
Annotation validator — schema + cross-row checks for Set 3 entity annotations
and Set 4 RAG questions (main + adversarial subsets).

Auto-detects mode from input fields, or override with --mode. Reports per-row
schema errors plus cross-row stats (type distribution vs target, span integrity,
citation hygiene).

Usage:
    python scripts/validate_annotations.py --input set3_annotations.jsonl
    python scripts/validate_annotations.py --input set4_main.jsonl
    python scripts/validate_annotations.py --input set4_adversarial.jsonl
    python scripts/validate_annotations.py --input set3.jsonl --corpus articles.jsonl  # checks offsets

Modes:
    set3-entities    Set 3 entity annotation rows
    set4-main        Set 4 main RAG questions (n=50)
    set4-adversarial Set 4 adversarial subset (n=20)

Exit code: 0 if all rows valid, 1 if any errors found.

No external dependencies — Python 3.9+ stdlib only.
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


SET3_ENTITY_TYPES = {"PERSON", "ORG", "LOC"}
SET4_MAIN_TYPES = {"factoid", "synthesis", "comparative", "temporal"}
SET4_MAIN_TARGETS = {"factoid": 20, "synthesis": 15, "comparative": 10, "temporal": 5}
SET4_ADV_TYPES = {"outside_corpus", "almost_match", "counterfactual"}
SET4_ADV_TARGETS = {"outside_corpus": 8, "almost_match": 8, "counterfactual": 4}

YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")


def load_jsonl(path: Path) -> list:
    if not path.exists():
        sys.exit(f"error: input not found: {path}")
    rows = []
    with path.open() as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append((i, json.loads(line)))
            except json.JSONDecodeError as e:
                sys.exit(f"error: bad JSONL on line {i}: {e}")
    return rows


def detect_mode(rows: list) -> str:
    if not rows:
        sys.exit("error: input is empty")
    sample = rows[0][1]
    if "entities" in sample or "claims" in sample:
        return "set3-entities"
    if "expected_behavior" in sample:
        return "set4-adversarial"
    if "reference_answer" in sample or "gold_article_ids" in sample:
        return "set4-main"
    sys.exit(f"error: cannot auto-detect mode from row 1; pass --mode explicitly")


def validate_set3_row(row: dict, corpus: dict) -> list:
    errors = []
    for field in ("article_id", "entities", "claims"):
        if field not in row:
            errors.append(f"missing field '{field}'")
    if errors:
        return errors

    article_text = corpus.get(row["article_id"]) if corpus else None

    if not isinstance(row["entities"], list):
        errors.append("'entities' must be a list")
    else:
        for j, ent in enumerate(row["entities"]):
            for k in ("type", "span", "start", "end"):
                if k not in ent:
                    errors.append(f"entity[{j}] missing '{k}'")
                    continue
            if "type" in ent and ent["type"] not in SET3_ENTITY_TYPES:
                errors.append(f"entity[{j}] type '{ent.get('type')}' not in {sorted(SET3_ENTITY_TYPES)}")
            if "start" in ent and "end" in ent:
                if not isinstance(ent["start"], int) or not isinstance(ent["end"], int):
                    errors.append(f"entity[{j}] start/end must be ints")
                elif ent["start"] >= ent["end"]:
                    errors.append(f"entity[{j}] start ({ent['start']}) >= end ({ent['end']})")
                elif ent["end"] - ent["start"] < 2:
                    errors.append(f"entity[{j}] span too short ({ent['end'] - ent['start']} chars)")
                elif article_text is not None:
                    actual = article_text[ent["start"]:ent["end"]]
                    if actual != ent.get("span"):
                        errors.append(
                            f"entity[{j}] span mismatch: offsets give {actual!r}, "
                            f"annotation says {ent.get('span')!r}"
                        )

    if not isinstance(row["claims"], list):
        errors.append("'claims' must be a list")
    else:
        if len(row["claims"]) > 10:
            errors.append(f"{len(row['claims'])} claims exceeds rubric cap of 10")
        for j, claim in enumerate(row["claims"]):
            for k in ("text", "start", "end"):
                if k not in claim:
                    errors.append(f"claim[{j}] missing '{k}'")
            if article_text is not None and "start" in claim and "end" in claim:
                actual = article_text[claim["start"]:claim["end"]]
                if actual != claim.get("text"):
                    errors.append(f"claim[{j}] offset/text mismatch")
    return errors


def validate_set4_main_row(row: dict) -> list:
    errors = []
    for field in ("question_id", "question", "type", "gold_article_ids", "reference_answer", "citation_map"):
        if field not in row:
            errors.append(f"missing field '{field}'")
    if errors:
        return errors
    if row["type"] not in SET4_MAIN_TYPES:
        errors.append(f"type '{row['type']}' not in {sorted(SET4_MAIN_TYPES)}")
    if not isinstance(row["gold_article_ids"], list) or not row["gold_article_ids"]:
        errors.append("'gold_article_ids' must be a non-empty list")
    if not isinstance(row.get("citation_map"), dict):
        errors.append("'citation_map' must be a dict")
    else:
        # Check that every cite key in citation_map appears in reference_answer as [N]
        answer = row.get("reference_answer", "")
        for key in row["citation_map"]:
            if f"[{key}]" not in answer:
                errors.append(f"citation_map key '{key}' not referenced as [{key}] in reference_answer")
        # Check that every [N] in answer has a corresponding citation_map entry
        cited = set(re.findall(r"\[(\d+)\]", answer))
        for c in cited:
            if c not in row["citation_map"]:
                errors.append(f"reference_answer cites [{c}] but no citation_map entry")
    if row["type"] == "temporal":
        if not YEAR_PATTERN.search(row.get("question", "")):
            errors.append("temporal question must contain an explicit year (anchoring rule)")
    return errors


def validate_set4_adversarial_row(row: dict) -> list:
    errors = []
    for field in ("question_id", "question", "type", "gold_article_ids", "expected_behavior", "expected_response_traits"):
        if field not in row:
            errors.append(f"missing field '{field}'")
    if errors:
        return errors
    if row["type"] not in SET4_ADV_TYPES:
        errors.append(f"type '{row['type']}' not in {sorted(SET4_ADV_TYPES)}")
    if not isinstance(row["gold_article_ids"], list) or row["gold_article_ids"]:
        errors.append("adversarial 'gold_article_ids' must be an empty list")
    if row["expected_behavior"] not in {"refuse", "abstain"}:
        errors.append(f"expected_behavior '{row['expected_behavior']}' not in ['refuse', 'abstain']")
    if not isinstance(row.get("expected_response_traits"), list) or not row["expected_response_traits"]:
        errors.append("'expected_response_traits' must be a non-empty list")
    return errors


def report_set3_stats(valid_rows: list) -> None:
    print(f"\n=== Set 3 stats ({len(valid_rows)} articles) ===")
    type_counts = Counter()
    per_article_entities = []
    per_article_claims = []
    annotators = Counter()
    for _, r in valid_rows:
        for ent in r.get("entities", []):
            type_counts[ent.get("type")] += 1
        per_article_entities.append(len(r.get("entities", [])))
        per_article_claims.append(len(r.get("claims", [])))
        if "annotator" in r:
            annotators[r["annotator"]] += 1

    print(f"Entity-type totals:")
    for t in sorted(SET3_ENTITY_TYPES):
        print(f"  {t}: {type_counts[t]:,}")
    if per_article_entities:
        print(f"Entities per article:  median={median(per_article_entities)}, min={min(per_article_entities)}, max={max(per_article_entities)}")
        zero_entity_articles = sum(1 for n in per_article_entities if n == 0)
        if zero_entity_articles:
            print(f"  WARNING: {zero_entity_articles} article(s) have zero entities — likely a rubric issue or short articles")
    if per_article_claims:
        print(f"Claims per article:    median={median(per_article_claims)}, min={min(per_article_claims)}, max={max(per_article_claims)}")
    if annotators:
        print(f"Annotators: {dict(annotators)}")


def report_set4_main_stats(valid_rows: list) -> None:
    print(f"\n=== Set 4 main stats ({len(valid_rows)} questions) ===")
    type_counts = Counter()
    gold_counts = []
    answer_lengths = []
    for _, r in valid_rows:
        type_counts[r.get("type")] += 1
        gold_counts.append(len(r.get("gold_article_ids", [])))
        answer_lengths.append(len(r.get("reference_answer", "").split()))

    print(f"Type distribution (actual vs target):")
    for t in sorted(SET4_MAIN_TYPES):
        actual = type_counts[t]
        target = SET4_MAIN_TARGETS[t]
        flag = " ✓" if actual == target else f" (target: {target})"
        print(f"  {t:<14} {actual:>3}{flag}")
    total = sum(type_counts.values())
    print(f"  {'TOTAL':<14} {total:>3} (target: 50)")

    if gold_counts:
        print(f"Gold articles per question:  median={median(gold_counts)}, max={max(gold_counts)}")
        too_broad = sum(1 for c in gold_counts if c > 5)
        if too_broad:
            print(f"  WARNING: {too_broad} question(s) have >5 gold articles — likely too broad")
    if answer_lengths:
        print(f"Answer length (words):       median={median(answer_lengths)}, max={max(answer_lengths)}")
        too_long = sum(1 for n in answer_lengths if n > 100)
        if too_long:
            print(f"  WARNING: {too_long} answer(s) exceed 100 words")


def report_set4_adversarial_stats(valid_rows: list) -> None:
    print(f"\n=== Set 4 adversarial stats ({len(valid_rows)} questions) ===")
    type_counts = Counter()
    behavior_counts = Counter()
    for _, r in valid_rows:
        type_counts[r.get("type")] += 1
        behavior_counts[r.get("expected_behavior")] += 1

    print(f"Type distribution (actual vs target):")
    for t in sorted(SET4_ADV_TYPES):
        actual = type_counts[t]
        target = SET4_ADV_TARGETS[t]
        flag = " ✓" if actual == target else f" (target: {target})"
        print(f"  {t:<18} {actual:>3}{flag}")
    print(f"  {'TOTAL':<18} {sum(type_counts.values()):>3} (target: 20)")
    print(f"Expected behaviors: {dict(behavior_counts)}")


def median(values: list) -> float:
    if not values:
        return 0
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate annotation JSONL against rubric schemas.")
    parser.add_argument("--input", required=True, type=Path, help="JSONL to validate")
    parser.add_argument("--mode", choices=["set3-entities", "set4-main", "set4-adversarial"],
                        default=None, help="Override auto-detection")
    parser.add_argument("--corpus", type=Path, default=None,
                        help="Optional corpus JSONL ({article_id, text}) to verify Set 3 offset spans")
    args = parser.parse_args()

    rows = load_jsonl(args.input)
    mode = args.mode or detect_mode(rows)
    print(f"Mode: {mode} ({len(rows)} rows)")

    corpus = {}
    if args.corpus and mode == "set3-entities":
        for _, r in load_jsonl(args.corpus):
            if "article_id" in r and "text" in r:
                corpus[r["article_id"]] = r["text"]
        print(f"Corpus loaded: {len(corpus)} articles available for offset verification")

    validators = {
        "set3-entities":     lambda r: validate_set3_row(r, corpus),
        "set4-main":         validate_set4_main_row,
        "set4-adversarial":  validate_set4_adversarial_row,
    }
    validate = validators[mode]

    valid_rows = []
    error_count = 0
    for line_no, row in rows:
        errs = validate(row)
        if errs:
            error_count += len(errs)
            print(f"\n  line {line_no}: {row.get('article_id') or row.get('question_id') or '?'}")
            for e in errs:
                print(f"    - {e}")
        else:
            valid_rows.append((line_no, row))

    if mode == "set3-entities":
        report_set3_stats(valid_rows)
    elif mode == "set4-main":
        report_set4_main_stats(valid_rows)
    elif mode == "set4-adversarial":
        report_set4_adversarial_stats(valid_rows)

    print(f"\n=== Result ===")
    print(f"Valid rows:   {len(valid_rows)}/{len(rows)}")
    print(f"Total errors: {error_count}")
    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
