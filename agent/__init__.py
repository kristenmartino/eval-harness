"""
Agentic RAG agent (spec v0.3) — the system under test for trajectory eval.

A single loop with four responsibilities (router / planner / executor / critic)
over a `ToolRegistry`. The registry is the seam, exactly as the adapter Protocol
is the seam for models: swap the deterministic MockToolRegistry for a real vector
store and nothing in the loop, the trajectory writer, or the scorers changes.

Public surface:
  agent.tools  — ToolRegistry, Tool, ToolResult, MockToolRegistry, validate_args
  agent.loop   — run_agent, AgentRun
"""

from agent import loop, tools  # noqa: F401
