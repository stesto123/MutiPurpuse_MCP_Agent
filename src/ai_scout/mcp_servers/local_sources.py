"""Built-in local MCP source server for first-run validation.

This server does not fetch external data. It exposes a deterministic
``discover`` tool so a user can validate the real stdio MCP path before wiring
RSS, GitHub, YouTube, web-search, or calendar servers.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def discover_resources(
    *,
    topics: Sequence[Any] | None = None,
    max_results: int | None = None,
) -> dict[str, Any]:
    topic_values = [str(topic).strip() for topic in topics or () if str(topic).strip()]
    topic_text = ", ".join(topic_values) if topic_values else "AI agents"
    limit = _positive_int(max_results, default=5)
    resources = [
        {
            "id": "local_langgraph_mcp_patterns",
            "source": "built-in-local-sources",
            "title": "LangGraph + MCP local agent patterns",
            "url": "https://example.test/ai-scout/langgraph-mcp-patterns",
            "summary": f"Practical notes for building local agents around {topic_text}.",
            "kind": "article",
            "tags": ["langgraph", "mcp", "local-agents"],
        },
        {
            "id": "local_agent_eval_repo",
            "source": "built-in-local-sources",
            "title": "Runnable local AI agent evaluation repo",
            "url": "https://github.com/example/local-agent-evals",
            "summary": "Repository with local-first eval examples and reproducible runs.",
            "kind": "github_repo",
            "tags": ["evals", "github", "local-llm"],
        },
        {
            "id": "local_mcp_calendar_video",
            "source": "built-in-local-sources",
            "title": "Video: MCP calendar automations for personal agents",
            "url": "https://video.example.test/watch/mcp-calendar",
            "summary": "Walkthrough of calendar side effects through MCP tools.",
            "kind": "video",
            "tags": ["mcp", "calendar", "automation"],
        },
    ]
    return {"resources": resources[:limit], "source": "built-in-local-sources"}


def discover(topics: list[Any] | None = None, max_results: int | None = None) -> dict[str, Any]:
    """Return deterministic local resources for testing AI Scout over MCP stdio."""

    return discover_resources(topics=topics, max_results=max_results)


def main() -> int:
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on optional runtime package.
        raise RuntimeError("Install the 'mcp' package to run this MCP server.") from exc

    server = FastMCP("AI Scout Local Sources")
    server.tool()(discover)
    server.run()
    return 0


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value if value is not None else default)
    except (TypeError, ValueError):
        return default
    return max(1, parsed)


if __name__ == "__main__":
    raise SystemExit(main())
