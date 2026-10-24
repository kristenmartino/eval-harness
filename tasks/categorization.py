"""
Task A — Article categorization.

Per spec §2: classify each article into one of Sift's existing categories.
Headline metrics (computed downstream from per-item scores): accuracy +
macro-F1 (categories are imbalanced).

Sampling: temperature=0 — deterministic; max_tokens small since output is
one label.
"""

from dataclasses import dataclass
import hashlib

from adapters.base import SamplingParams


# Default taxonomy for the committed sample fixtures. Real runs supply their
# observed taxonomy explicitly; the fixture labels are not Sift's taxonomy.
CATEGORIES = ["Tech", "Politics", "Energy", "Health", "Business", "Sports"]


PROMPT_TEMPLATE = """You are categorizing a news article. Output exactly one category from this list:

{categories}

Article:
{article}

Output only the category name, nothing else."""


@dataclass
class CategorizationTask:
    name: str = "A_categorization"
    sampling_params: SamplingParams = SamplingParams(temperature=0.0, max_tokens=10)
    categories: tuple = tuple(CATEGORIES)
    instructions: str = ""

    def __post_init__(self):
        self.categories = tuple(self.categories)
        if len(self.categories) < 2 or any(not isinstance(c, str) or not c.strip()
                                           for c in self.categories):
            raise ValueError("categories must contain at least two nonempty labels")
        if len({c.casefold() for c in self.categories}) != len(self.categories):
            raise ValueError("category labels must be unique ignoring case")

    def configuration(self):
        return {"categories": list(self.categories), "instructions": self.instructions,
                "prompt_template_sha256": hashlib.sha256(PROMPT_TEMPLATE.encode()).hexdigest(),
                "parser": "exact-label-v1"}

    def prompt_template(self, item: dict) -> str:
        categories = "\n".join(f"- {c}" for c in self.categories)
        if self.instructions:
            categories += "\n\nCategory definitions and routing rules:\n" + self.instructions
        return PROMPT_TEMPLATE.format(
            categories=categories,
            article=item["text"],
        )

    def parse_output(self, raw_text: str):
        """Accept one exact label, tolerating case and surrounding punctuation.

        Explanations, multiple labels, and substring matches are parse failures.
        """
        cleaned = raw_text.strip().strip('"\'.,!?')
        for cat in self.categories:
            if cleaned.lower() == cat.lower():
                return cat
        return None  # parse failure — caller checks .get('parse_failed')

    def score(self, prediction, item: dict) -> dict:
        gold = item.get("category")
        return {
            "predicted": prediction,
            "gold": gold,
            "correct": (prediction == gold) if (prediction and gold) else False,
            "parse_failed": prediction is None,
        }


# Module-level instance — runner imports `task` from this module
task = CategorizationTask()
