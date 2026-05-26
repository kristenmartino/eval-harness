"""
Task A — Article categorization.

Per spec §2: classify each article into one of Sift's existing categories.
Headline metrics (computed downstream from per-item scores): accuracy +
macro-F1 (categories are imbalanced).

Sampling: temperature=0 — deterministic; max_tokens small since output is
one label.
"""

from dataclasses import dataclass

from adapters.base import SamplingParams


# Placeholder — replace with output of category_distribution_check.py once
# the actual Sift distribution is pulled. Categories with <20 articles are
# dropped per §8 decision rule.
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

    def prompt_template(self, item: dict) -> str:
        return PROMPT_TEMPLATE.format(
            categories="\n".join(f"- {c}" for c in CATEGORIES),
            article=item["text"],
        )

    def parse_output(self, raw_text: str):
        """Strip whitespace/punctuation; match against known categories
        first by exact, then by substring (handles 'Tech.' and 'The article
        is about Tech.')."""
        cleaned = raw_text.strip().strip('"\'.,!?')
        for cat in CATEGORIES:
            if cleaned.lower() == cat.lower():
                return cat
        for cat in CATEGORIES:
            if cat.lower() in cleaned.lower():
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
