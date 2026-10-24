import io
import json
import unittest
from unittest.mock import patch

from adapters.base import SamplingParams
from adapters.ollama import OllamaAdapter

DIGEST = "a" * 64


def response(value):
    return io.BytesIO(json.dumps(value).encode())


class TestOllamaDigest(unittest.TestCase):
    def test_digest_identity_is_distinct_from_hf_commit(self):
        adapter = OllamaAdapter("llama:test", model_digest=DIGEST)
        self.assertEqual(adapter.model_id, "llama:test@ollama-sha256:" + DIGEST)
        self.assertIsNone(adapter.hf_sha)

    def test_generation_verifies_digest_and_sends_seed(self):
        with patch("urllib.request.urlopen", side_effect=[
            response({"models": [{"name": "llama:test", "digest": DIGEST}]}),
            response({"response": "energy", "prompt_eval_count": 12, "eval_count": 2}),
        ]) as request:
            out = OllamaAdapter("llama:test", model_digest=DIGEST).complete(
                "prompt", SamplingParams(seed=42, max_tokens=10))
        self.assertEqual(out.text, "energy")
        self.assertEqual(out.raw_metadata["ollama_manifest_sha256"], DIGEST)
        payload = json.loads(request.call_args_list[1].args[0].data)
        self.assertEqual(payload["options"]["seed"], 42)

    def test_missing_or_changed_digest_blocks_generation(self):
        for models in ([], [{"name": "llama:test", "digest": "b" * 64}]):
            with self.subTest(models=models), patch("urllib.request.urlopen", return_value=response({"models": models})) as request:
                with self.assertRaisesRegex(ValueError, "changed|missing"):
                    OllamaAdapter("llama:test", model_digest=DIGEST).complete("prompt", SamplingParams())
                self.assertEqual(request.call_count, 1)

    def test_invalid_digest_is_rejected(self):
        with self.assertRaises(ValueError):
            OllamaAdapter("llama:test", model_digest="short")
