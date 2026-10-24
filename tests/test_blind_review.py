import unittest

from eval.blind_review import REVIEW_FIELDS, prepare_review, validate_annotations


def fixture():
    dev = [{"id": f"source-{i}", "text": f"original input {i}", "category": "a"} for i in range(12)]
    results = [{"_meta": True, "held_out": False, "task": "A_categorization", "n_samples": 1, "model_id": "m"}]
    for i, row in enumerate(dev):
        same = i < 8
        results.append({"item_id": row["id"], "model_id": "m", "sample_idx": 0,
                        "score": {"gold": "a", "predicted": "a" if same else "b",
                                  "correct": same, "parse_failed": False}})
    return dev, results


class TestBlindReview(unittest.TestCase):
    def test_all_disagreements_and_uniform_match_sample_are_blinded(self):
        dev, results = fixture()
        reviewer, key, meta = prepare_review(dev, results, sample_matches=3, seed=91)
        self.assertEqual(len(reviewer), 7)
        self.assertEqual({k["item_id"] for k in key if k["stratum"] == "disagreement"},
                         {f"source-{i}" for i in range(8, 12)})
        self.assertEqual(sum(k["stratum"] == "match" for k in key), 3)
        self.assertTrue(all(tuple(row) == REVIEW_FIELDS for row in reviewer))
        self.assertTrue(all(row["human_category"] == row["confidence"] == row["rationale"] == "" for row in reviewer))
        for row, mapping in zip(reviewer, key):
            self.assertEqual(row["review_id"], mapping["review_id"])
            self.assertEqual(row["article_input"], next(d["text"] for d in dev if d["id"] == mapping["item_id"]))
        self.assertEqual({k["population_weight"] for k in key if k["stratum"] == "match"}, {8 / 3})

    def test_randomization_is_reproducible_and_independent_of_input_order(self):
        dev, results = fixture()
        a = prepare_review(dev, results, sample_matches=3, seed=9)
        b = prepare_review(list(reversed(dev)), [results[0]] + list(reversed(results[1:])), sample_matches=3, seed=9)
        self.assertEqual(a, b)
        self.assertNotEqual(a[1], prepare_review(dev, results, sample_matches=3, seed=10)[1])

    def test_holdout_run_and_incomplete_or_duplicate_results_fail(self):
        for kind in ("holdout", "missing", "duplicate", "wrong_label", "error"):
            dev, rows = fixture()
            if kind == "holdout": rows[0]["held_out"] = True
            elif kind == "missing": rows.pop()
            elif kind == "duplicate": rows.append(rows[-1])
            elif kind == "wrong_label": rows[1]["score"]["gold"] = "b"
            else: rows[1]["error"] = "failed"
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                prepare_review(dev, rows, sample_matches=3, seed=1)

    def test_returned_labels_need_all_required_fields_and_exact_ids(self):
        row = {"review_id": "REV-001", "human_category": "a", "confidence": "high",
               "review_status": "reviewed", "alternative_category": "", "rationale": "source evidence"}
        self.assertEqual(validate_annotations([row], ["REV-001"], ["a", "b"]), [])
        for field in ("human_category", "confidence", "rationale"):
            for empty in ("", None):
                with self.subTest(field=field, empty=empty):
                    self.assertTrue(validate_annotations([dict(row, **{field: empty})], ["REV-001"], ["a", "b"]))
        self.assertTrue(validate_annotations([row, row], ["REV-001"], ["a", "b"]))
        self.assertTrue(validate_annotations([row], ["REV-002"], ["a", "b"]))

    def test_insufficient_input_is_retained_without_forcing_a_category(self):
        row = {"review_id": "REV-001", "human_category": "", "confidence": "",
               "review_status": "insufficient_text", "rationale": "no event information"}
        self.assertEqual(validate_annotations([row], ["REV-001"], ["a", "b"]), [])
