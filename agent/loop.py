"""
The agent loop — router / planner / executor / critic over a ToolRegistry.

One `run_agent()` call drives a whole trajectory: route → (plan → execute)* →
synthesize → critique → maybe retry. It is model-agnostic (any ModelAdapter)
and tool-agnostic (any ToolRegistryProtocol), so the deterministic mock path
and a future real-model / real-vector-store path share this exact code.

Role output contract (line-based, tolerantly parsed like eval/judge.py so a
real model's markdown/whitespace noise still parses):
  Router     ROUTE: <retrieve|direct>            [QUERY: <text>]
  Planner    TOOL: <name|none>                    [ARGS: {json}]
  Executor   ANSWER: <text>                       [CITATIONS: id#span, id#span]
  Critic     VERDICT: <pass|revise>               [REASONS: <text>]

The loop never crashes on a tool fault: a raised ToolError is retried once, then
falls back to synthesis (spec §5b error-recovery). Whether that recovery is
*good* (grounded/abstaining) or *bad* (hallucinated) is the scorer's call
(eval/trajectory.py) — the loop only records, faithfully, what happened.
"""

import json
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from adapters.base import SamplingParams
from agent.tools import ToolError, ToolValidationError

# Params default to a small deterministic budget; a generation run overrides.
DEFAULT_PARAMS = SamplingParams(temperature=0.0, max_tokens=512)

_MK = r"[*`_]*"  # optional markdown emphasis run, mirroring judge.py


def _labeled(label: str) -> re.Pattern:
    return re.compile(
        rf"^\s*{_MK}\s*{label}\s*{_MK}\s*:\s*{_MK}\s*(.+?)\s*{_MK}\s*$",
        re.IGNORECASE | re.MULTILINE,
    )


_ROUTE_RE = _labeled("ROUTE")
_QUERY_RE = _labeled("QUERY")
_TOOL_RE = _labeled("TOOL")
_ARGS_RE = re.compile(r"^\s*" + _MK + r"\s*ARGS\s*" + _MK + r"\s*:\s*(.+)$",
                      re.IGNORECASE | re.MULTILINE)
_ANSWER_RE = _labeled("ANSWER")
_CITATIONS_RE = _labeled("CITATIONS")
_VERDICT_RE = _labeled("VERDICT")
_REASONS_RE = _labeled("REASONS")


@dataclass(frozen=True)
class AgentRun:
    """The full result of one agent run — the object the trajectory writer
    serializes into the §3 JSONL run-unit."""

    trajectory: list
    final_answer: Optional[str]
    citations: list
    terminated: str  # "answered" | "max_steps" | "tool_error_unrecovered"
    system_prompt: str = ""


def _first(pattern: re.Pattern, text: str) -> Optional[str]:
    m = pattern.search(text)
    return m.group(1).strip() if m else None


def _parse_route(text: str):
    route = (_first(_ROUTE_RE, text) or "").lower()
    query = _first(_QUERY_RE, text) or ""
    if route not in ("retrieve", "direct"):
        route = "retrieve"  # safe default: prefer grounding over guessing
    return route, query


def _parse_plan(text: str):
    tool = (_first(_TOOL_RE, text) or "none").strip()
    args = {}
    m = _ARGS_RE.search(text)
    if m:
        try:
            parsed = json.loads(m.group(1).strip())
            if isinstance(parsed, dict):
                args = parsed
        except json.JSONDecodeError:
            args = {}  # unparseable args → empty → arg-validity will fail
    if tool.lower() in ("none", "synthesize", "answer", "done"):
        return None, {}
    return tool, args


def _parse_citations(text: str) -> list:
    raw = _first(_CITATIONS_RE, text)
    if not raw:
        return []
    parts = [c.strip() for c in raw.split(",")]
    return [c for c in parts if c]


def _parse_verdict(text: str) -> str:
    v = (_first(_VERDICT_RE, text) or "pass").lower()
    return "revise" if v.startswith("revise") else "pass"


def run_agent(
    adapter,
    registry,
    question: str,
    params: SamplingParams = None,
    *,
    system_prompt: str = "",
    max_steps: int = 8,
    k_retries: int = 1,
    tool_retries: int = 1,
    clock=None,
) -> AgentRun:
    """Run the agent over one question. Deterministic given a deterministic
    adapter (ScriptedAdapter/ReplayAdapter) and registry (MockToolRegistry)."""
    params = params or DEFAULT_PARAMS
    now = clock or (lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    trajectory = []
    step_no = 0

    def call(role: str, action: str, prompt: str, extra: dict = None) -> str:
        nonlocal step_no
        completion = adapter.complete(prompt, params)
        step = {
            "step": step_no,
            "role": role,
            "action": action,
            "latency_ms": completion.latency_ms,
            "tokens": {"in": completion.input_tokens, "out": completion.output_tokens},
            "ts": now(),
        }
        if extra:
            step.update(extra)
        trajectory.append(step)
        step_no += 1
        return completion.text, step

    # 1. Router ------------------------------------------------------------- #
    r_prompt = f"{system_prompt}\n[ROUTER] Question: {question}\nDecide ROUTE."
    r_text, r_step = call("router", "route", r_prompt)
    route, query = _parse_route(r_text)
    r_step["args"] = {"route": route, "query": query}

    evidence = []          # list of {"id", "span", "title"} spans in hand
    faulted_twice = set()  # tools that failed even after a retry — don't re-call
    final_answer = None
    citations = []
    terminated = None

    def synthesize_and_critique():
        """Emit the answer, then run the critic. Returns the critic verdict."""
        nonlocal final_answer, citations
        ev_lines = "\n".join(f"- {e['id']}: {e['title']}" for e in evidence) or "(none)"
        s_prompt = (f"{system_prompt}\n[EXECUTOR:SYNTHESIZE] Question: {question}\n"
                    f"Evidence:\n{ev_lines}\nWrite ANSWER and CITATIONS.")
        s_text, _ = call("executor", "synthesize", s_prompt)
        final_answer = _first(_ANSWER_RE, s_text) or ""
        citations = _parse_citations(s_text)
        c_prompt = (f"{system_prompt}\n[CRITIC] Question: {question}\n"
                    f"Draft: {final_answer}\nCitations: {citations}\nEmit VERDICT.")
        c_text, c_step = call("critic", "verify", c_prompt)
        verdict = _parse_verdict(c_text)
        c_step["verdict"] = verdict
        c_step["reasons"] = [x for x in ([_first(_REASONS_RE, c_text)] if _first(_REASONS_RE, c_text) else [])]
        return verdict

    if route == "direct":
        verdict = synthesize_and_critique()
        return AgentRun(trajectory, final_answer, citations,
                        "answered", system_prompt)

    # 2. Plan → execute loop ------------------------------------------------ #
    answer_attempts = 0
    while step_no < max_steps:
        p_ev = "\n".join(f"- {e['id']}" for e in evidence) or "(none)"
        p_prompt = (f"{system_prompt}\n[PLANNER] Question: {question}\n"
                    f"Query: {query}\nEvidence so far:\n{p_ev}\n"
                    f"Emit TOOL (+ ARGS) or TOOL: none to synthesize.")
        p_text, _ = call("planner", "plan", p_prompt)
        tool, args = _parse_plan(p_text)

        if tool is None:
            verdict = synthesize_and_critique()
            if verdict == "pass" or answer_attempts >= k_retries:
                terminated = "answered"
                break
            answer_attempts += 1
            continue

        # Executor: validate args, then call the tool.
        from agent.tools import validate_args  # local import keeps top clean
        schema = None
        try:
            schema = registry.get(tool).input_schema
        except ToolError:
            schema = None
        arg_errors = validate_args(schema, args) if schema is not None else ["unknown tool"]
        e_step = {
            "step": step_no, "role": "executor", "action": tool, "args": args,
            "arg_valid": (arg_errors == []),
        }
        # (executor step is appended by hand — no model call here)
        step_no += 1

        if tool in faulted_twice:
            e_step["result_summary"] = "skipped (previously faulted)"
            trajectory.append(e_step)
            continue
        if arg_errors:
            e_step["result_summary"] = f"invalid args: {'; '.join(arg_errors)}"
            trajectory.append(e_step)
            continue

        recovered = None
        for tool_attempt in range(tool_retries + 1):
            try:
                result = registry.call(tool, args)
                e_step["result_summary"] = result.summary
                if result.ok and result.value:
                    if tool == "vector_search":
                        for hit in result.value:
                            evidence.append({"id": hit["id"], "span": "0",
                                             "title": hit["title"]})
                    elif tool == "fetch_article":
                        a = result.value
                        evidence.append({"id": a["id"], "span": "0", "title": a["title"]})
                if tool_attempt > 0:
                    e_step["recovery"] = "retry_succeeded"
                break
            except ToolValidationError as e:
                e_step["arg_valid"] = False
                e_step["result_summary"] = f"invalid args: {e}"
                break
            except ToolError as e:
                e_step.setdefault("faults", []).append(f"{type(e).__name__}: {e}")
                if tool_attempt < tool_retries:
                    e_step["recovery"] = "retry"
                    continue
                # Retries exhausted → fall back to synthesis with what we have.
                e_step["recovery"] = "fallback"
                faulted_twice.add(tool)
                recovered = True
        trajectory.append(e_step)

    if terminated is None:
        # Ran out of steps without the planner electing to synthesize.
        if final_answer is None:
            terminated = "max_steps"
        else:
            terminated = "answered"

    return AgentRun(trajectory, final_answer, citations, terminated, system_prompt)
