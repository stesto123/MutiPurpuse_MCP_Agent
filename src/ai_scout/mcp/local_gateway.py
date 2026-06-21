"""Local fake MCP gateway for source-tree dry runs.

The specialist agents intentionally depend on a very small synchronous
``call_tool`` boundary. This local gateway implements that boundary with
deterministic fixture-like MCP responses, so the public repository can execute
end-to-end without personal accounts or real MCP servers.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any


class LocalDryRunMCPGateway:
    """Deterministic MCP-shaped gateway used for dry-run development."""

    def __init__(self, *, mode: str = "dry_run") -> None:
        self.mode = mode
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call_tool(self, tool_name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append((tool_name, dict(arguments)))
        if tool_name == "sources.discover":
            return self._discover(arguments)
        if tool_name == "content.inspect":
            return self._inspect(arguments)
        if tool_name == "calendar.read_availability":
            return self._availability(arguments)
        if tool_name == "calendar.create_event":
            return self._create_event(arguments)
        raise ValueError(f"No local dry-run MCP handler for tool {tool_name!r}")

    def _discover(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        topics = tuple(str(item) for item in arguments.get("topics", ()) if str(item).strip())
        topic_text = ", ".join(topics) if topics else "AI agents"
        max_results = int(arguments.get("max_results") or 5)
        resources = [
            {
                "id": "local_langgraph_mcp_patterns",
                "source": "local-dry-run",
                "title": "LangGraph + MCP local agent patterns",
                "url": "https://example.test/ai-scout/langgraph-mcp-patterns",
                "summary": f"Practical notes for building local agents around {topic_text}.",
                "kind": "article",
                "tags": ["langgraph", "mcp", "local-agents"],
            },
            {
                "id": "local_agent_eval_repo",
                "source": "local-dry-run",
                "title": "Runnable local AI agent evaluation repo",
                "url": "https://github.com/example/local-agent-evals",
                "summary": "Repository with local-first eval examples and reproducible runs.",
                "kind": "github_repo",
                "tags": ["evals", "github", "local-llm"],
            },
            {
                "id": "local_mcp_calendar_video",
                "source": "local-dry-run",
                "title": "Video: MCP calendar automations for personal agents",
                "url": "https://video.example.test/watch/mcp-calendar",
                "summary": "Walkthrough of calendar side effects through MCP tools.",
                "kind": "video",
                "tags": ["mcp", "calendar", "automation"],
            },
        ]
        return {"resources": resources[:max_results], "source": "local-dry-run"}

    def _inspect(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        resource = arguments.get("resource")
        title = ""
        if isinstance(resource, Mapping):
            title = str(resource.get("title") or "")
        lower_title = title.casefold()
        is_repo = "repo" in lower_title or "github" in lower_title
        is_video = "video" in lower_title
        estimated = 60 if is_repo else 45 if is_video else 30
        return {
            "summary": f"Dry-run inspection summary for {title or 'resource'}.",
            "signals": {
                "relevance": 0.92 if "mcp" in lower_title or "agent" in lower_title else 0.78,
                "novelty": 0.86,
                "source_trust": 0.72 if is_repo else 0.68,
                "local_applicability": 0.95 if is_repo else 0.75,
            },
            "estimated_minutes": estimated,
        }

    def _availability(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        del arguments
        start = datetime.now(timezone.utc).replace(second=0, microsecond=0) + timedelta(days=1)
        first = start.replace(hour=17, minute=30)
        second = first + timedelta(days=2)
        return {
            "slots": [
                {"start": first.isoformat(), "end": (first + timedelta(minutes=90)).isoformat()},
                {"start": second.isoformat(), "end": (second + timedelta(minutes=90)).isoformat()},
            ]
        }

    def _create_event(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        idempotency_key = str(arguments.get("idempotency_key") or "event")
        status = "dry_run" if self.mode != "autonomous" else "created"
        return {
            "status": status,
            "event_id": f"dry_{idempotency_key[-12:]}",
            "dry_run": self.mode != "autonomous",
        }

