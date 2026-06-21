from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .client import MCPClient
from .models import ErrorCode, ToolCallResult
from .registry import MCPToolRegistry


class StdioMCPClient(MCPClient):
    """MCP stdio client using the official Python SDK when installed.

    A fresh MCP session is opened per tool call. This is intentionally simple
    for phase 1; connection pooling can be added once real local servers are
    wired in and profiled.
    """

    def __init__(self, registry: MCPToolRegistry) -> None:
        self.registry = registry

    async def call_tool(
        self,
        server: str,
        tool: str,
        arguments: Mapping[str, Any],
        *,
        timeout_s: float | None = None,
    ) -> ToolCallResult:
        del timeout_s
        try:
            from mcp import ClientSession, StdioServerParameters  # type: ignore
            from mcp.client.stdio import stdio_client  # type: ignore
        except ImportError as exc:
            return ToolCallResult.failure(
                server,
                tool,
                ErrorCode.INVALID_CONFIG,
                "The mcp package is required for stdio MCP transport.",
                details={"exception": str(exc)},
            )

        server_spec = self.registry.get_server(server)
        transport = dict(server_spec.transport)
        if transport.get("type", "stdio") != "stdio":
            return ToolCallResult.failure(
                server,
                tool,
                ErrorCode.INVALID_CONFIG,
                "Only stdio MCP transport is supported by StdioMCPClient.",
                details={"transport": transport.get("type")},
            )
        command = transport.get("command")
        if not command:
            return ToolCallResult.failure(
                server,
                tool,
                ErrorCode.INVALID_CONFIG,
                "MCP stdio server transport requires a command.",
            )

        params = StdioServerParameters(
            command=str(command),
            args=[str(arg) for arg in transport.get("args", [])],
            env={str(k): str(v) for k, v in dict(transport.get("env", {})).items()} or None,
        )
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    raw_result = await session.call_tool(tool, dict(arguments))
        except Exception as exc:  # pragma: no cover - requires real MCP server.
            return ToolCallResult.failure(
                server,
                tool,
                ErrorCode.TOOL_ERROR,
                f"{exc.__class__.__name__}: {exc}",
                details={"exception_type": exc.__class__.__name__},
            )

        data = _coerce_mcp_result(raw_result)
        if data.get("is_error"):
            return ToolCallResult.failure(
                server,
                tool,
                ErrorCode.TOOL_ERROR,
                str(data.get("text") or "MCP tool returned an error."),
                details=data,
            )
        return ToolCallResult.success(server, tool, data)


def _coerce_mcp_result(raw_result: Any) -> Mapping[str, Any]:
    structured = (
        getattr(raw_result, "structuredContent", None)
        or getattr(raw_result, "structured_content", None)
    )
    if isinstance(structured, Mapping):
        return dict(structured)

    is_error = bool(getattr(raw_result, "isError", False) or getattr(raw_result, "is_error", False))
    content = getattr(raw_result, "content", None)
    texts: list[str] = []
    items: list[dict[str, Any]] = []
    if isinstance(content, list):
        for item in content:
            item_type = getattr(item, "type", None) or getattr(item, "kind", None)
            text = getattr(item, "text", None)
            if text is not None:
                texts.append(str(text))
                try:
                    loaded = json.loads(str(text))
                except json.JSONDecodeError:
                    loaded = None
                if isinstance(loaded, Mapping):
                    items.append(dict(loaded))
                    continue
            items.append({"type": item_type or item.__class__.__name__, "text": text})
    if len(items) == 1 and isinstance(items[0], Mapping) and set(items[0]) != {"type", "text"}:
        result = dict(items[0])
        result.setdefault("is_error", is_error)
        return result
    return {
        "is_error": is_error,
        "content": items,
        "text": "\n".join(texts),
    }

