"""
ToolRegistry — the tool seam, mirroring adapters/base.ModelAdapter.

The agent depends on this Protocol the way tasks depend on the adapter Protocol.
Swapping a real vector store for the deterministic MockToolRegistry (for CI,
key-free) touches nothing in the agent loop or the scorers.

Stdlib only: tool-arg validation is a small hand-rolled validator, NOT
pydantic/jsonschema (spec §2 constraint). Tool schemas are MCP-shaped
(`{"type": "object", "properties": {...}, "required": [...]}`) so a thin MCP
server could later expose the same registry over JSON-RPC/stdio (spec §2).

The registry_hash() folds into the run-unit reproducibility header and the §6
regression baseline triple — a MAJOR tool-schema change moves the hash.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol


class ToolError(RuntimeError):
    """Raised by a tool handler on a runtime failure (network, timeout, bad
    upstream). The loop's error-recovery (spec §5b) classifies and recovers
    from these; the injected-fault harness raises them to test that recovery.
    Distinct from ToolValidationError, which is an arg-contract failure, not a
    fault — the two feed different scorers (error-recovery vs arg-validity)."""


class ToolValidationError(ToolError):
    """Args failed schema validation before the handler ran. Graded by the
    arg-schema-validity scorer (spec §4), NOT the error-recovery scorer."""


# Minimal JSON-Schema type map for the stdlib validator. bool is handled
# specially because bool is a subclass of int in Python — a stray True must
# not validate as an "integer".
_JSON_TYPES = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


def validate_args(schema: dict, args: dict) -> list:
    """Return a list of human-readable validation errors ([] if valid).

    schema: MCP-shaped {"type": "object", "properties": {name: {"type": ...}},
    "required": [names]}. A dependency-free stand-in for jsonschema; the
    arg-schema-validity scorer (spec §4) grades tool args against exactly this.
    Strict: unknown args are errors too, so a hallucinated argument is caught."""
    if not isinstance(args, dict):
        return [f"args must be an object, got {type(args).__name__}"]
    errors = []
    props = schema.get("properties", {})
    required = schema.get("required", [])

    for name in required:
        if name not in args:
            errors.append(f"missing required arg '{name}'")

    for name, value in args.items():
        if name not in props:
            errors.append(f"unexpected arg '{name}'")
            continue
        expected = props[name].get("type")
        if expected is None:
            continue
        py_type = _JSON_TYPES.get(expected)
        if py_type is None:
            errors.append(f"arg '{name}' has unknown schema type '{expected}'")
            continue
        # bool is a subclass of int: reject it everywhere except boolean.
        if expected != "boolean" and isinstance(value, bool):
            errors.append(f"arg '{name}' expected {expected}, got boolean")
            continue
        if not isinstance(value, py_type):
            got = type(value).__name__
            errors.append(f"arg '{name}' expected {expected}, got {got}")

    return errors


@dataclass(frozen=True)
class ToolResult:
    """A tool call's outcome. `summary` is the short line recorded as the
    trajectory step's result_summary (spec §3) — it must not contain the full
    payload, only a digest, so the trace stays compact."""

    value: Any
    summary: str
    ok: bool = True


@dataclass(frozen=True)
class Tool:
    """One callable tool. `handler(args) -> ToolResult` runs the tool; it may
    raise ToolError to model a runtime fault. `input_schema` is the MCP-shaped
    contract validate_args() checks. The handler is NOT part of registry_hash()
    — only the observable schema is (a behavior change in the handler that keeps
    the schema is a code change, caught by CI, not a schema change)."""

    name: str
    description: str
    input_schema: dict
    handler: Callable[[dict], ToolResult] = field(compare=False, repr=False)


class ToolRegistryProtocol(Protocol):
    """The seam. Any registry (mock or real) implements this."""

    def names(self) -> list: ...
    def get(self, name: str) -> Tool: ...
    def call(self, name: str, args: dict) -> ToolResult: ...
    def schemas(self) -> list: ...
    def registry_hash(self) -> str: ...


class ToolRegistry:
    """Concrete registry over a fixed set of Tools."""

    def __init__(self, tools):
        dupes = [t.name for t in tools]
        if len(set(dupes)) != len(dupes):
            raise ValueError(f"duplicate tool names: {dupes}")
        self._tools = {t.name: t for t in tools}

    def names(self) -> list:
        return sorted(self._tools)

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise ToolError(f"unknown tool '{name}' (registered: {self.names()})")
        return self._tools[name]

    def call(self, name: str, args: dict) -> ToolResult:
        """Validate args, then run the handler. Raises ToolValidationError on a
        bad-args contract violation, or ToolError if the tool doesn't exist or
        the handler raises a runtime fault (propagated for the loop to recover)."""
        tool = self.get(name)
        errors = validate_args(tool.input_schema, args)
        if errors:
            raise ToolValidationError(f"{name}: " + "; ".join(errors))
        return tool.handler(args)

    def schemas(self) -> list:
        """MCP `tools/list`-shaped view: name / description / inputSchema, sorted
        by name. This is exactly what registry_hash() hashes and what a thin MCP
        server would emit."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.input_schema,
            }
            for t in (self._tools[n] for n in self.names())
        ]

    def registry_hash(self) -> str:
        """SHA-256 over the canonical, order-independent schema view. Moves iff a
        tool is added/removed or a schema (name/description/args) changes — the
        signal the §6 regression baseline keys on."""
        canonical = json.dumps(self.schemas(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# MockToolRegistry — a deterministic, key-free registry over a tiny in-memory
# corpus. This is the CI/mock-path tool backend (spec §9 steps 1-6): no vector
# DB, no network, fully reproducible. A real vector store swaps in behind the
# same ToolRegistryProtocol at build step 7.
# --------------------------------------------------------------------------- #

# Synthetic stable IDs use the `sift://<category>/<slug>` scheme (spec §2
# Prerequisite-0) so the deterministic scorers and locks aren't blocked on the
# real Sift article-ID decision.
DEMO_CORPUS = [
    {
        "id": "sift://energy/vogtle-capacity",
        "category": "Energy",
        "title": "Vogtle nuclear plant reaches planned capacity",
        "body": "The Vogtle nuclear plant announced its planned capacity of "
                "2200 megawatts across the two new reactors, the first built in "
                "the United States in decades.",
    },
    {
        "id": "sift://energy/ira-provisions",
        "category": "Energy",
        "title": "Debate over the IRA energy provisions",
        "body": "Supporters argued the IRA energy provisions would cut emissions "
                "and create manufacturing jobs; critics said the subsidies were "
                "costly and distorted the market.",
    },
    {
        "id": "sift://tech/rlhf-approaches",
        "category": "Tech",
        "title": "Comparing RLHF approaches across labs",
        "body": "Anthropic emphasized constitutional methods in its RLHF pipeline, "
                "while other labs leaned more on human preference data collected "
                "at scale.",
    },
    {
        "id": "sift://politics/fed-march-rates",
        "category": "Politics",
        "title": "Fed holds rates steady in March",
        "body": "In March 2026 the Federal Reserve announced it would hold "
                "interest rates steady, citing cooling but still-elevated "
                "inflation.",
    },
    {
        "id": "sift://health/gene-therapy-approval",
        "category": "Health",
        "title": "FDA approves a new gene therapy",
        "body": "The FDA approved a new gene therapy for a rare inherited "
                "disorder, the agency's third such approval this year.",
    },
]

_STOPWORDS = frozenset(
    "a an the of to in on for and or is are was were be been being with by "
    "at as it its this that from what which how does did do".split()
)


def _tokens(text: str) -> set:
    """Lowercased alphanumeric tokens minus stopwords — the deterministic basis
    for the mock's keyword-overlap 'vector' search."""
    out = set()
    for raw in text.lower().split():
        tok = "".join(ch for ch in raw if ch.isalnum())
        if tok and tok not in _STOPWORDS:
            out.add(tok)
    return out


def build_mock_registry(corpus=None) -> ToolRegistry:
    """Build a ToolRegistry with vector_search / fetch_article / list_by_category
    over an in-memory corpus. Fully deterministic: `vector_search` ranks by
    keyword overlap with the id as a stable tiebreak, so the same query always
    returns the same ordered hits."""
    corpus = list(DEMO_CORPUS if corpus is None else corpus)
    by_id = {a["id"]: a for a in corpus}
    doc_tokens = {a["id"]: _tokens(a["title"] + " " + a["body"]) for a in corpus}

    def vector_search(args: dict) -> ToolResult:
        query = args["query"]
        k = args.get("k", 5)
        q_tokens = _tokens(query)
        scored = []
        for a in corpus:
            overlap = len(q_tokens & doc_tokens[a["id"]])
            if overlap > 0:
                scored.append((overlap, a["id"]))
        # Deterministic order: overlap desc, then id asc.
        scored.sort(key=lambda t: (-t[0], t[1]))
        hits = [
            {"id": aid, "title": by_id[aid]["title"], "score": score}
            for score, aid in scored[:k]
        ]
        return ToolResult(value=hits, summary=f"{len(hits)} hits")

    def fetch_article(args: dict) -> ToolResult:
        aid = args["id"]
        article = by_id.get(aid)
        if article is None:
            # A missing id is a normal empty result, not a fault.
            return ToolResult(value=None, summary="not found", ok=False)
        return ToolResult(
            value=article,
            summary=f"{len(article['body'])} chars",
        )

    def list_by_category(args: dict) -> ToolResult:
        cat = args["category"]
        ids = sorted(a["id"] for a in corpus if a["category"] == cat)
        return ToolResult(value=ids, summary=f"{len(ids)} in {cat}")

    return ToolRegistry([
        Tool(
            name="vector_search",
            description="Semantic search over the article corpus; returns ranked hits.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "k": {"type": "integer"},
                },
                "required": ["query"],
            },
            handler=vector_search,
        ),
        Tool(
            name="fetch_article",
            description="Fetch a single article's full body by stable id.",
            input_schema={
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
            },
            handler=fetch_article,
        ),
        Tool(
            name="list_by_category",
            description="List article ids in a category.",
            input_schema={
                "type": "object",
                "properties": {"category": {"type": "string"}},
                "required": ["category"],
            },
            handler=list_by_category,
        ),
    ])
