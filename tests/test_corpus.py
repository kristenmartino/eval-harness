from collections import Counter
import unittest

from eval.corpus import prepare_categorization


def records():
    return [{"id": f"{c}-{i}", "source_url": f"https://example.test/{c}/{i}",
             "text": f"article {c} {i}", "category": c, "content_sha256": f"{c}-{i}"}
            for c, n in (("a", 50), ("b", 30), ("rare", 3)) for i in range(n)]


class TestCorpusSelection(unittest.TestCase):
    def test_deterministic_stratification_and_disjoint_holdout(self):
        dev, held, meta = prepare_categorization(records(), target_n=50)
        self.assertEqual((len(dev), len(held)), (40, 10))
        self.assertEqual(meta["eligible_labels"], ["a", "b"])
        self.assertEqual(meta["excluded_categories"], {"rare": 3})
        self.assertTrue(all(n >= 20 for n in meta["selected_counts"].values()))
        for key in ("id", "source_url", "content_sha256"):
            self.assertFalse({r[key] for r in dev} & {r[key] for r in held})
        again = prepare_categorization(list(reversed(records())), target_n=50)
        self.assertEqual([r["id"] for r in dev], [r["id"] for r in again[0]])
        self.assertEqual([r["id"] for r in held], [r["id"] for r in again[1]])

    def test_duplicate_ids_urls_and_content_never_cross_splits(self):
        base = records()
        duplicates = [dict(base[0]), dict(base[1], id="new-id"),
                      dict(base[2], id="syndication", source_url="https://other.test/copy")]
        dev, held, meta = prepare_categorization(base + duplicates, target_n=50)
        self.assertEqual(meta["duplicate_records_removed"], 3)
        self.assertEqual(len({r["content_sha256"] for r in dev + held}), 50)

    def test_category_distribution_matches_written_splits(self):
        dev, held, meta = prepare_categorization(records(), target_n=50)
        self.assertEqual(dict(Counter(r["category"] for r in dev)), meta["dev_counts"])
        self.assertEqual(dict(Counter(r["category"] for r in held)), meta["holdout_counts"])

    def test_insufficient_corpus_and_missing_source_text_fail(self):
        with self.assertRaisesRegex(ValueError, "eligible unique inputs"):
            prepare_categorization(records(), target_n=100)
        with self.assertRaises(ValueError):
            prepare_categorization([dict(records()[0], text="")])

    def test_target_cannot_silently_drop_an_eligible_category(self):
        with self.assertRaisesRegex(ValueError, "minimum"):
            prepare_categorization(records(), target_n=30)
