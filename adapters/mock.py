"""
Mock adapter — for harness self-testing without API or Ollama access.

Used by scripts/example_run.py to demonstrate the full pipeline end-to-end.
Also useful for unit testing tasks and the runner.
"""

import time

from .base import Completion, SamplingParams


class MockAdapter:
    """Returns canned responses keyed by prompt substring match.

    response_map: dict of {substring: response_text}. First match wins.
    Falls back to empty string if nothing matches — useful for testing
    parse-failure handling in tasks.
    """

    def __init__(self, response_map: dict, model_id: str = "mock-v1"):
        self.response_map = response_map
        self.model_id = model_id

    def complete(self, prompt: str, params: SamplingParams) -> Completion:
        time.sleep(0.001)  # small latency so latency_ms is non-zero
        response = ""
        for key, resp in self.response_map.items():
            if key in prompt:
                response = resp
                break
        # Token counts approximated as chars/4 (rough English heuristic)
        return Completion(
            text=response,
            input_tokens=len(prompt) // 4,
            output_tokens=len(response) // 4,
            latency_ms=1.0,
            model_id=self.model_id,
            raw_metadata={"mock": True},
        )
