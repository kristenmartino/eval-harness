"""
Task Protocol — each task module exports an instance that implements this.

Tasks are self-contained: prompt template + output parser + scorer. Adding a
task = adding a module. Reusing the harness on a new project = swapping the
tasks directory.

Design constraint per spec §1 stretch outcome: this Protocol is the seam at
which GridPulse / Tarazu / GTM Healthcare reuse begins. Keep it minimal and
backend-agnostic.
"""

from typing import Any, Protocol


class Task(Protocol):
    """All task modules must export an instance of this Protocol as `task`."""

    name: str
    sampling_params: Any  # adapters.base.SamplingParams

    def prompt_template(self, item: dict) -> str:
        """Format one dataset item into the prompt string passed to the adapter."""
        ...

    def parse_output(self, raw_text: str) -> Any:
        """Extract the structured prediction from raw model output.
        MUST NOT raise — return None or a sentinel on parse failure so the
        runner can log it and continue."""
        ...

    def score(self, prediction: Any, item: dict) -> dict:
        """Score one prediction against the gold in `item`. Returns a dict
        of named metrics (e.g. {'correct': True, 'predicted': 'Tech'}).
        The runner writes this verbatim into the results JSONL — keep keys
        stable across runs for downstream metric aggregation."""
        ...
