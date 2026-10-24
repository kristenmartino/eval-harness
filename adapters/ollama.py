"""
Ollama adapter — local-model backend via Ollama HTTP API on DGX Spark.

Stdlib-only. Production runs must pin Ollama version + HF SHA per spec §8
reproducibility checklist.

Single-attempt by contract: no internal retries. The runner retries transient
failures (network errors, timeouts, 429/5xx) in-process with exponential
backoff and records a permanent or retry-exhausted failure as an `error` row.
"""

import json
import re
import time
import urllib.error
import urllib.request

from .base import Completion, SamplingParams


class OllamaAdapter:
    """Concrete adapter for Ollama-hosted open-weight models.

    model_id format: '<ollama_tag>:<hf_sha_prefix>' so any results JSONL row
    traces unambiguously to the weights that produced it.
    """

    def __init__(self, model_tag: str, hf_sha: str = None,
                 host: str = "http://localhost:11434", model_digest: str = None):
        if not hf_sha and not model_digest:
            raise ValueError("provide an HF SHA or an observed Ollama manifest digest")
        if model_digest and not re.fullmatch(r"[0-9a-f]{64}", model_digest):
            raise ValueError("Ollama model digest must be a full SHA-256 hex digest")
        self.model_tag = model_tag
        self.hf_sha = hf_sha
        self.model_digest = model_digest
        self.model_id = (f"{model_tag}@ollama-sha256:{model_digest}" if model_digest
                         else f"{model_tag}:{hf_sha[:7]}")
        self.host = host

    def complete(self, prompt: str, params: SamplingParams) -> Completion:
        if self.model_digest:
            with urllib.request.urlopen(f"{self.host}/api/tags", timeout=30) as response:
                models = json.load(response).get("models", [])
            actual = next((m.get("digest") for m in models if m.get("name") == self.model_tag), None)
            if actual != self.model_digest:
                raise ValueError("Ollama model manifest changed or the pinned tag is missing")
        payload = {
            "model": self.model_tag,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": params.temperature,
                "num_predict": params.max_tokens,
                "seed": params.seed if params.seed is not None else -1,
                "stop": list(params.stop_sequences) if params.stop_sequences else [],
            },
        }
        req = urllib.request.Request(
            f"{self.host}/api/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=600) as resp:
            result = json.loads(resp.read())
        latency_ms = (time.perf_counter() - t0) * 1000

        return Completion(
            text=result.get("response", "").strip(),
            input_tokens=result.get("prompt_eval_count", 0),
            output_tokens=result.get("eval_count", 0),
            latency_ms=latency_ms,
            model_id=self.model_id,
            raw_metadata={
                "ollama_manifest_sha256": self.model_digest,
                "prompt_eval_duration_ns": result.get("prompt_eval_duration", 0),
                "eval_duration_ns": result.get("eval_duration", 0),
            },
        )
