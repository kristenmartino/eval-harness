"""
ScriptedAdapter — returns a fixed sequence of canned completions, in order.

The deterministic, key-free driver for the agent loop (spec §9 steps 1-6).
MockAdapter (substring match) is right for single-shot tasks, but a multi-turn
agent loop needs *ordered* responses — router, then planner, then executor,
then critic — which a stateless substring map cannot provide. This is also the
shape the cassette ReplayAdapter takes at step 6, so the loop is exercised
against the same interface in tests and in CI replay.
"""

from adapters.base import Completion


class ScriptExhausted(RuntimeError):
    """The loop requested more completions than the script provides — usually a
    sign the loop branched differently than the test expected."""


class ScriptedAdapter:
    """Yields `responses` (list of str) in order, one per complete() call.

    Records every prompt in `.calls` for assertions. Token counts mirror
    MockAdapter's chars/4 heuristic so downstream cost accounting sees the same
    shape it would from a real backend."""

    def __init__(self, responses, model_id: str = "scripted-v1"):
        self.model_id = model_id
        self._responses = list(responses)
        self._i = 0
        self.calls = []

    def complete(self, prompt, params) -> Completion:
        self.calls.append(prompt)
        if self._i >= len(self._responses):
            raise ScriptExhausted(
                f"scripted adapter exhausted after {self._i} responses "
                f"(loop asked for #{self._i + 1})"
            )
        text = self._responses[self._i]
        self._i += 1
        return Completion(
            text=text,
            input_tokens=len(prompt) // 4,
            output_tokens=len(text) // 4,
            latency_ms=1.0,
            model_id=self.model_id,
            raw_metadata={"scripted": True, "index": self._i - 1},
        )
