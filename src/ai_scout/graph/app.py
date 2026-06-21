"""LangGraph development entrypoint.

This module is intentionally importable without secrets or real MCP servers so
`langgraph dev` can load the graph from a public checkout.
"""

from __future__ import annotations

from ai_scout.graph.nodes import GraphDependencies
from ai_scout.graph.runner import build_scout_graph
from ai_scout.mcp import LocalDryRunMCPGateway

graph = build_scout_graph(
    GraphDependencies(mcp=LocalDryRunMCPGateway(mode="dry_run")),
    prefer_langgraph=True,
)

