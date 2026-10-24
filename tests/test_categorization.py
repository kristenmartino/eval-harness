from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from adapters.mock import MockAdapter
from eval import runner
from tasks.categorization import CategorizationTask


class TestConfiguredCategorization(unittest.TestCase):
    def test_uses_explicit_taxonomy_and_production_definitions(self):
        task = CategorizationTask(categories=["technology", "world", "general"],
                                  instructions="Use world only for events outside the US.")
        prompt = task.prompt_template({"text": "source article"})
        self.assertIn("- technology", prompt)
        self.assertIn(task.instructions, prompt)
        self.assertNotIn("- Tech\n", prompt)
        self.assertEqual(task.parse_output('"Technology."'), "technology")

    def test_ambiguous_or_explanatory_outputs_are_not_substring_matches(self):
        task = CategorizationTask(categories=["energy", "science"])
        for raw in ("energy or science", "not energy", "bioenergy", "This is energy."):
            with self.subTest(raw=raw):
                self.assertIsNone(task.parse_output(raw))

    def test_invalid_taxonomy_is_rejected(self):
        for cats in ([], ["one"], ["a", "A"], ["a", ""]):
            with self.subTest(cats=cats), self.assertRaises(ValueError):
                CategorizationTask(categories=cats)

    def test_cli_loads_category_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "categories.json"
            path.write_text(json.dumps({"categories": ["energy", "science"], "instructions": "rule"}))
            task = runner._build_task("A", path)
            self.assertEqual(task.categories, ("energy", "science"))
            self.assertEqual(task.instructions, "rule")
            with self.assertRaises(ValueError):
                runner._build_task("B", path)

    def test_resume_refuses_changed_taxonomy_rules_or_sampling(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset, output = root / "dev.jsonl", root / "results.jsonl"
            dataset.write_text(json.dumps({"id": "1", "text": "article", "category": "energy"}) + "\n")
            adapter = MockAdapter(response_map={"article": "energy"})
            original = CategorizationTask(categories=["energy", "science"])
            runner.run(adapter, original, dataset, output, repo_root=root)
            for task in (CategorizationTask(categories=["energy", "politics"]),
                         CategorizationTask(categories=["energy", "science"], instructions="new rule"),
                         CategorizationTask(categories=["energy", "science"],
                             sampling_params=replace(original.sampling_params, seed=42))):
                with self.subTest(task=task), self.assertRaises(runner.ResumeHeaderMismatch):
                    runner.run(adapter, task, dataset, output, repo_root=root)
