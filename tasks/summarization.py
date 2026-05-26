"""
Task B — Article summarization.

Per spec §2: generate a 2-3 sentence summary (≤60 words) per article.
Metrics (computed downstream from pairwise verdicts in /eval/judge.py):
  - Bradley-Terry preference ranking via cross-vendor judges
  - Length compliance rate (≤60 words)
  - Factuality flag rate (judge marks summaries with claims not in source)

Sampling: temperature=0.7, N=3 samples per item (bootstrap CI in analysis).
"""

from dataclasses import dataclass

from adapters.base import SamplingParams


PROMPT_TEMPLATE = """You are writing a summary of a news article for a daily digest UI.

Article:
{article}

Write a 2-3 sentence summary capturing the article's key points. Maximum 60 words. Output only the summary — no preamble, no quotes."""


@dataclass
class SummarizationTask:
    name: str = "B_summarization"
    sampling_params: SamplingParams = SamplingParams(temperature=0.7, max_tokens=150)

    def prompt_template(self, item: dict) -> str:
        return PROMPT_TEMPLATE.format(article=item["text"])

    def parse_output(self, raw_text: str):
        text = raw_text.strip().strip('"').strip("'")
        if not text:
            return None
        word_count = len(text.split())
        return {
            "summary": text,
            "word_count": word_count,
            "within_length": word_count <= 60,
        }

    def score(self, prediction, item: dict) -> dict:
        """No gold for summarization — pairwise verdicts come from /eval/judge.py.
        This per-sample score propagates parse output for later aggregation."""
        if not prediction:
            return {"summary": None, "word_count": 0, "within_length": False, "parse_failed": True}
        return {
            "summary": prediction["summary"],
            "word_count": prediction["word_count"],
            "within_length": prediction["within_length"],
            "parse_failed": False,
        }


task = SummarizationTask()
