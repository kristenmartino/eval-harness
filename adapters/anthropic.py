"""
Anthropic adapter — Messages API for Claude models.

Stdlib-only. API key from ANTHROPIC_API_KEY env var (or constructor).

Production runs MUST pin a dated snapshot in model_name per spec §8 (e.g.,
'claude-sonnet-4-6-20260101'). The model_id used in results JSONL is exactly
the model_name — snapshot pinning lives in what you pass to the constructor.

Single-attempt: no retries here. A failure surfaces to the runner, which
records it as an `error` row (visible for debugging and cost accounting) and
re-attempts it on the next resume run.
"""

import json
import os
import time
import urllib.request

from .base import Completion, SamplingParams


ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"


class AnthropicAdapter:
    """Concrete adapter for Anthropic Claude models via Messages API.

    Constructor examples (with snapshot pin):
      AnthropicAdapter('claude-sonnet-4-6-20260101')
      AnthropicAdapter('claude-haiku-4-5-20251215')
    """

    def __init__(self, model_name: str, api_key: str = None, timeout: float = 120.0):
        self.model_name = model_name
        self.model_id = model_name
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set in env and api_key not passed")
        self.timeout = timeout

    def complete(self, prompt: str, params: SamplingParams) -> Completion:
        payload = {
            "model": self.model_name,
            "max_tokens": params.max_tokens,
            "temperature": params.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if params.stop_sequences:
            payload["stop_sequences"] = list(params.stop_sequences)
        # Note: Anthropic Messages API does not accept a seed parameter as of 2026-05.

        req = urllib.request.Request(
            ANTHROPIC_API_URL,
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": ANTHROPIC_API_VERSION,
            },
        )
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            result = json.loads(resp.read())
        latency_ms = (time.perf_counter() - t0) * 1000

        content_blocks = result.get("content", [])
        text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
        usage = result.get("usage", {})

        return Completion(
            text=text.strip(),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            latency_ms=latency_ms,
            model_id=self.model_id,
            raw_metadata={
                "stop_reason": result.get("stop_reason"),
                "response_id": result.get("id"),
            },
        )
