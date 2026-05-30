"""
OpenAI adapter — Chat Completions API for GPT models.

Stdlib-only. API key from OPENAI_API_KEY env var (or constructor).

Production runs MUST pin a dated snapshot in model_name per spec §8 (e.g.,
'gpt-4o-2024-08-06'). The model_id used in results JSONL is exactly the
model_name — snapshot pinning lives in what you pass to the constructor.

Single-attempt: a failure surfaces to the runner, which records it as an
`error` row and re-attempts on the next resume run. Supports the OpenAI `seed`
parameter (best-effort reproducibility, not guaranteed by OpenAI).
"""

import json
import os
import time
import urllib.request

from .base import Completion, SamplingParams


OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIAdapter:
    """Concrete adapter for OpenAI GPT models via Chat Completions API.

    Constructor examples (with snapshot pin):
      OpenAIAdapter('gpt-4o-2024-08-06')
      OpenAIAdapter('gpt-4o-mini-2024-07-18')
    """

    def __init__(self, model_name: str, api_key: str = None, timeout: float = 120.0):
        self.model_name = model_name
        self.model_id = model_name
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set in env and api_key not passed")
        self.timeout = timeout

    def complete(self, prompt: str, params: SamplingParams) -> Completion:
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": params.temperature,
            "max_tokens": params.max_tokens,
        }
        if params.stop_sequences:
            payload["stop"] = list(params.stop_sequences)
        if params.seed is not None:
            payload["seed"] = params.seed

        req = urllib.request.Request(
            OPENAI_API_URL,
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            result = json.loads(resp.read())
        latency_ms = (time.perf_counter() - t0) * 1000

        choices = result.get("choices", [])
        text = choices[0]["message"]["content"] if choices else ""
        usage = result.get("usage", {})

        return Completion(
            text=text.strip(),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            latency_ms=latency_ms,
            model_id=self.model_id,
            raw_metadata={
                "finish_reason": choices[0].get("finish_reason") if choices else None,
                "response_id": result.get("id"),
                "system_fingerprint": result.get("system_fingerprint"),
            },
        )
