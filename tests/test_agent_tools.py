"""
Tests for the ToolRegistry seam (agent/tools.py): the stdlib arg validator,
registry-hash stability, and the deterministic mock corpus tools.

Run: python -m unittest tests.test_agent_tools
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.tools import (
    Tool,
    ToolError,
    ToolRegistry,
    ToolResult,
    ToolValidationError,
    build_mock_registry,
    validate_args,
)

_SCHEMA = {
    "type": "object",
    "properties": {"query": {"type": "string"}, "k": {"type": "integer"}},
    "required": ["query"],
}


class TestValidateArgs(unittest.TestCase):

    def test_valid(self):
        self.assertEqual(validate_args(_SCHEMA, {"query": "x", "k": 3}), [])

    def test_missing_required(self):
        errs = validate_args(_SCHEMA, {"k": 3})
        self.assertTrue(any("missing required arg 'query'" in e for e in errs))

    def test_wrong_type(self):
        errs = validate_args(_SCHEMA, {"query": 5})
        self.assertTrue(any("expected string" in e for e in errs))

    def test_bool_is_not_integer(self):
        """bool subclasses int in Python — a stray True must not pass as integer."""
        errs = validate_args(_SCHEMA, {"query": "x", "k": True})
        self.assertTrue(any("expected integer, got boolean" in e for e in errs))

    def test_unknown_arg_rejected(self):
        """A hallucinated argument is an error (strict validation)."""
        errs = validate_args(_SCHEMA, {"query": "x", "bogus": 1})
        self.assertTrue(any("unexpected arg 'bogus'" in e for e in errs))

    def test_optional_absent_ok(self):
        self.assertEqual(validate_args(_SCHEMA, {"query": "x"}), [])


class TestRegistryHash(unittest.TestCase):

    def _reg(self, desc="d"):
        return ToolRegistry([
            Tool("t", desc, _SCHEMA, handler=lambda a: ToolResult(None, "ok"))
        ])

    def test_hash_stable_across_instances(self):
        self.assertEqual(self._reg().registry_hash(), self._reg().registry_hash())

    def test_hash_changes_on_schema_change(self):
        a = self._reg()
        b = ToolRegistry([
            Tool("t", "d", {"type": "object", "properties": {"query": {"type": "string"}},
                            "required": ["query"]},
                 handler=lambda x: ToolResult(None, "ok"))
        ])
        self.assertNotEqual(a.registry_hash(), b.registry_hash())

    def test_hash_changes_on_description_change(self):
        self.assertNotEqual(self._reg("one").registry_hash(),
                            self._reg("two").registry_hash())

    def test_duplicate_names_rejected(self):
        with self.assertRaises(ValueError):
            ToolRegistry([
                Tool("t", "d", _SCHEMA, handler=lambda a: ToolResult(None, "ok")),
                Tool("t", "d", _SCHEMA, handler=lambda a: ToolResult(None, "ok")),
            ])


class TestRegistryCall(unittest.TestCase):

    def test_unknown_tool_raises_toolerror(self):
        reg = build_mock_registry()
        with self.assertRaises(ToolError):
            reg.call("no_such_tool", {})

    def test_invalid_args_raise_validation_error(self):
        reg = build_mock_registry()
        with self.assertRaises(ToolValidationError):
            reg.call("vector_search", {})  # missing required 'query'

    def test_handler_fault_propagates(self):
        """A raised ToolError propagates for the loop to recover from."""
        def boom(args):
            raise ToolError("upstream 503")
        reg = ToolRegistry([Tool("x", "d", {"type": "object", "properties": {}},
                                 handler=boom)])
        with self.assertRaises(ToolError):
            reg.call("x", {})

    def test_raw_stdlib_fault_wraps_as_toolerror(self):
        """A raw stdlib exception (e.g. a real tool's TimeoutError) surfaces at
        the seam as ToolError, with the underlying type visible in the message —
        so the loop recovers uniformly and Phase 2 can check shape-fidelity."""
        def boom(args):
            raise TimeoutError("read timed out")
        reg = ToolRegistry([Tool("x", "d", {"type": "object", "properties": {}},
                                 handler=boom)])
        with self.assertRaises(ToolError) as ctx:
            reg.call("x", {})
        self.assertIn("TimeoutError", str(ctx.exception))


class TestMockCorpusTools(unittest.TestCase):

    def setUp(self):
        self.reg = build_mock_registry()

    def test_vector_search_deterministic_and_relevant(self):
        r1 = self.reg.call("vector_search", {"query": "Vogtle planned capacity", "k": 3})
        r2 = self.reg.call("vector_search", {"query": "Vogtle planned capacity", "k": 3})
        self.assertEqual(r1.value, r2.value)  # deterministic
        self.assertEqual(r1.value[0]["id"], "sift://energy/vogtle-capacity")  # relevant top hit

    def test_vector_search_respects_k(self):
        r = self.reg.call("vector_search", {"query": "energy the plant", "k": 1})
        self.assertLessEqual(len(r.value), 1)

    def test_fetch_article_hit_and_miss(self):
        hit = self.reg.call("fetch_article", {"id": "sift://energy/vogtle-capacity"})
        self.assertTrue(hit.ok)
        self.assertIn("2200", hit.value["body"])
        miss = self.reg.call("fetch_article", {"id": "sift://nope/x"})
        self.assertFalse(miss.ok)

    def test_list_by_category_sorted(self):
        r = self.reg.call("list_by_category", {"category": "Energy"})
        self.assertEqual(r.value, sorted(r.value))
        self.assertIn("sift://energy/vogtle-capacity", r.value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
