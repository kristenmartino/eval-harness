"""
Model adapter Protocol and shared data classes.

All concrete adapters (Ollama, Anthropic, OpenAI, MockAdapter for tests)
implement the ModelAdapter Protocol. The harness consumes adapters
polymorphically — runner, tasks, and metrics never know which backend
produced a Completion.

This abstraction is what makes the harness reusable across portfolio
projects (GridPulse, Tarazu, GTM Healthcare): swap in a new task module +
a new dataset; adapters and runner are unchanged.
"""

from dataclasses import dataclass, field
from typing import Optional, Protocol


@dataclass(frozen=True)
class SamplingParams:
    """Generation-time parameters. Held constant across model × task per
    spec §5 — temperature=0 for deterministic tasks (A, C), 0.7 with N=3
    samples for generation tasks (B, D)."""

    temperature: float = 0.0
    max_tokens: int = 1024
    seed: Optional[int] = None
    stop_sequences: tuple = ()


@dataclass(frozen=True)
class Completion:
    """The result of one `adapter.complete()` call. Token counts may be
    approximate for adapters whose backend doesn't report them directly —
    flag this in raw_metadata for downstream cost/throughput accounting."""

    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    model_id: str
    raw_metadata: dict = field(default_factory=dict)


class ModelAdapter(Protocol):
    """Adapter contract — single method keeps the interface minimal.

    The model_id is used for results provenance and MUST be stable across
    runs. For open-weight models pin via HF SHA (see spec §8); for
    closed-weight pin via dated snapshot (e.g. claude-sonnet-4-6-20260101).
    """

    model_id: str

    def complete(self, prompt: str, params: SamplingParams) -> Completion:
        """Run one generation. Implementations MUST NOT retry transparently —
        retry is the runner's job, not the adapter's. The runner classifies a
        raised exception (eval.runner._is_transient) and retries transient
        failures (network errors, timeouts, 429/5xx) in-process with exponential
        backoff. A permanent failure — or a transient one that exhausts its
        retries — is recorded as an `error` row (kept visible for debugging and
        cost accounting) and re-attempted on the next resume run."""
        ...
