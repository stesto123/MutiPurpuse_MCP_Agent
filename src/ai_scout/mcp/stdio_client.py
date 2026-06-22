from __future__ import annotations

import asyncio
import json
import sys
import time
from collections.abc import Mapping
from typing import Any

from .client import MCPClient
from .models import ErrorCode, MCPRegistryError, ToolCallResult
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
        started = time.monotonic()
        try:
            server_spec = self.registry.get_server(server)
            effective_timeout = (
                timeout_s if timeout_s is not None else self.registry.timeout_for(server, tool)
            )
        except MCPRegistryError as exc:
            return exc.to_result(server, tool)

        if effective_timeout <= 0:
            return ToolCallResult.failure(
                server,
                tool,
                ErrorCode.VALIDATION_ERROR,
                "MCP tool timeout must be positive.",
                elapsed_s=_elapsed(started),
            )

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
                elapsed_s=_elapsed(started),
            )

        transport = dict(server_spec.transport)
        if transport.get("type", "stdio") != "stdio":
            return ToolCallResult.failure(
                server,
                tool,
                ErrorCode.INVALID_CONFIG,
                "Only stdio MCP transport is supported by StdioMCPClient.",
                details={"transport": transport.get("type")},
                elapsed_s=_elapsed(started),
            )
        command = transport.get("command")
        if not command:
            return ToolCallResult.failure(
                server,
                tool,
                ErrorCode.INVALID_CONFIG,
                "MCP stdio server transport requires a command.",
                elapsed_s=_elapsed(started),
            )

        params = StdioServerParameters(
            command=_resolve_command(str(command), transport),
            args=[str(arg) for arg in transport.get("args", [])],
            env={str(k): str(v) for k, v in dict(transport.get("env", {})).items()} or None,
        )
        try:
            raw_result = await asyncio.wait_for(
                _call_stdio_tool(
                    client_session=ClientSession,
                    stdio_client_factory=stdio_client,
                    params=params,
                    tool=tool,
                    arguments=arguments,
                ),
                timeout=effective_timeout,
            )
        except asyncio.TimeoutError:
            return ToolCallResult.failure(
                server,
                tool,
                ErrorCode.TIMEOUT,
                "MCP tool call timed out after %.3f seconds." % effective_timeout,
                retryable=True,
                elapsed_s=_elapsed(started),
            )
        except Exception as exc:  # pragma: no cover - requires real MCP server.
            return ToolCallResult.failure(
                server,
                tool,
                ErrorCode.TOOL_ERROR,
                f"{exc.__class__.__name__}: {exc}",
                details={"exception_type": exc.__class__.__name__},
                elapsed_s=_elapsed(started),
            )

        data = _coerce_mcp_result(raw_result)
        if data.get("is_error"):
            return ToolCallResult.failure(
                server,
                tool,
                ErrorCode.TOOL_ERROR,
                str(data.get("text") or "MCP tool returned an error."),
                details=data,
                elapsed_s=_elapsed(started),
            )
        return ToolCallResult.success(server, tool, data, elapsed_s=_elapsed(started))


async def _call_stdio_tool(
    *,
    client_session: Any,
    stdio_client_factory: Any,
    params: Any,
    tool: str,
    arguments: Mapping[str, Any],
) -> Any:
    async with stdio_client_factory(params) as (read, write):
        async with client_session(read, write) as session:
            await session.initialize()
            return await session.call_tool(tool, dict(arguments))


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


def _elapsed(started: float) -> float:
    return time.monotonic() - started


def _resolve_command(command: str, transport: Mapping[str, Any]) -> str:
    use_current_python = bool(transport.get("use_current_python", command in {"python", "python3"}))
    if use_current_python and command in {"python", "python3"}:
        return sys.executable
    return command
