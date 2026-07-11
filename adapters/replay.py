"""
ReplayAdapter — serve model completions from a cassette keyed by a canonical
hash of the outgoing request (spec §6, Tier A).

The Tier-A CI gate drives the REAL agent loop off recorded real-model responses:
key-free and deterministic, yet it exercises the actual loop + scorer code. And
because the key is a hash of the assembled request, a prompt / tool-schema /
sampling-param edit changes the key → replay MISS → build fails ("re-record"),
so a prompt edit CANNOT silently pass (VCR record_mode=none + Jest -u, fused).

Canonicalization is STRICT (freeze volatile fields) so only *semantic* edits
move the hash — the prompt text, the sampling params, the model id, and the
tool-registry hash. Nothing clock- or host-derived enters the key.

Re-recording is a local dev action (RecordingAdapter over a real/scripted
backend); this module never calls a live model itself.
"""

import hashlib
import json

from adapters.base import Completion


class ReplayMiss(RuntimeError):
    """No cassette entry for a request — the loop asked for a completion the
    committed cassette doesn't have, i.e. the assembled request changed. In CI
    this fails the build with a 're-record' instruction (the whole point)."""


def canonical_request_key(model_id, prompt, params, tool_registry_hash="") -> str:
    """SHA-256 over the canonicalized outgoing request. Only these fields enter
    the key; latency/host/timestamps never do."""
    payload = {
        "model_id": model_id,
        "prompt": prompt,
        "temperature": params.temperature,
        "max_tokens": params.max_tokens,
        "tool_registry_hash": tool_registry_hash,
    }
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


class ReplayAdapter:
    """Replay mode only: every complete() must hit a cassette entry, else
    ReplayMiss (record_mode=none). `cassette` is {request_key: response_text}."""

    def __init__(self, cassette, model_id, tool_registry_hash=""):
        self._map = dict(cassette)
        self.model_id = model_id
        self._trh = tool_registry_hash
        self.misses = []

    def complete(self, prompt, params) -> Completion:
        key = canonical_request_key(self.model_id, prompt, params, self._trh)
        if key not in self._map:
            self.misses.append(key)
            raise ReplayMiss(
                f"no cassette entry for request {key[:12]}… — the assembled "
                f"request changed; re-record the cassette (local: build_golden.py)."
            )
        text = self._map[key]
        return Completion(
            text=text,
            input_tokens=len(prompt) // 4,
            output_tokens=len(text) // 4,
            latency_ms=0.0,
            model_id=self.model_id,
            raw_metadata={"replay": True},
        )


class RecordingAdapter:
    """Wrap a backend adapter (a real model, or a ScriptedAdapter for the golden
    fixtures) and record {request_key: response_text} as it runs. The recorded
    `.cassette` is committed; CI replays it. This is the local 're-record' half."""

    def __init__(self, inner, tool_registry_hash=""):
        self._inner = inner
        self.model_id = inner.model_id
        self._trh = tool_registry_hash
        self.cassette = {}

    def complete(self, prompt, params) -> Completion:
        completion = self._inner.complete(prompt, params)
        key = canonical_request_key(self.model_id, prompt, params, self._trh)
        self.cassette[key] = completion.text
        return completion
