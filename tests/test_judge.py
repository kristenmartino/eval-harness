"""
Tests for eval/judge.py verdict parsing.

The headline guarantee under test: a judge's *unparseable* output must not be
silently counted as a genuine TIE. parse_status records the difference so
downstream Bradley-Terry aggregation can exclude or separately report it.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.judge import (  # noqa: E402
    PARSE_MALFORMED,
    PARSE_MISSING_FACTUALITY,
    PARSE_MISSING_VERDICT,
    PARSE_OK,
    is_anthropic_model,
    parse_verdict,
)


class TestParseVerdict(unittest.TestCase):

    def test_well_formed(self):
        text = "VERDICT: A\nFACTUALITY_A: pass\nFACTUALITY_B: fail\nA is clearer."
        winner, fa, fb, rationale, status = parse_verdict(text)
        self.assertEqual(winner, "A")
        self.assertEqual(fa, "pass")
        self.assertEqual(fb, "fail")
        self.assertEqual(status, PARSE_OK)
        self.assertIn("clearer", rationale)

    def test_tolerates_bold_and_case(self):
        text = "**verdict:** TIE\n**Factuality A:** PASS\n**factuality_b:** pass"
        winner, fa, fb, _, status = parse_verdict(text)
        self.assertEqual(winner, "TIE")
        self.assertEqual((fa, fb), ("pass", "pass"))
        self.assertEqual(status, PARSE_OK)

    def test_genuine_tie_is_ok_not_a_parse_failure(self):
        text = "VERDICT: TIE\nFACTUALITY_A: pass\nFACTUALITY_B: pass"
        winner, _, _, _, status = parse_verdict(text)
        self.assertEqual(winner, "TIE")
        self.assertEqual(status, PARSE_OK)  # a real tie, distinct from a parse failure

    def test_malformed_flags_status_even_though_winner_defaults_tie(self):
        """The critical case: garbage in → winner falls back to TIE for
        backward-compat, but status must NOT be OK."""
        winner, fa, fb, _, status = parse_verdict("I think both summaries are fine, honestly.")
        self.assertEqual(winner, "TIE")
        self.assertIsNone(fa)
        self.assertIsNone(fb)
        self.assertEqual(status, PARSE_MALFORMED)

    def test_missing_verdict_only(self):
        winner, _, _, _, status = parse_verdict("FACTUALITY_A: pass\nFACTUALITY_B: pass")
        self.assertEqual(winner, "TIE")
        self.assertEqual(status, PARSE_MISSING_VERDICT)

    def test_missing_factuality_only(self):
        winner, fa, fb, _, status = parse_verdict("VERDICT: B\nno factuality lines here")
        self.assertEqual(winner, "B")
        self.assertEqual((fa, fb), (None, None))
        self.assertEqual(status, PARSE_MISSING_FACTUALITY)

    def test_invalid_verdict_token_is_not_accepted(self):
        winner, _, _, _, status = parse_verdict("VERDICT: maybe\nFACTUALITY_A: pass\nFACTUALITY_B: pass")
        self.assertEqual(winner, "TIE")
        self.assertEqual(status, PARSE_MISSING_VERDICT)


class TestIsAnthropicModel(unittest.TestCase):

    def test_anthropic_models(self):
        for m in ["claude-sonnet-4-6-20260101", "haiku-4.5", "sonnet-4.6"]:
            self.assertTrue(is_anthropic_model(m))

    def test_non_anthropic_models(self):
        for m in ["gpt-4o-2024-08-06", "llama3.1:8b", "qwen2.5:14b"]:
            self.assertFalse(is_anthropic_model(m))


if __name__ == "__main__":
    unittest.main(verbosity=2)
