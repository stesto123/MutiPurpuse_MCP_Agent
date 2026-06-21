from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from .client import MCPClient
from .models import MCPRegistryError
from .registry import MCPToolRegistry


class SyncMCPToolGateway:
    """Synchronous gateway expected by specialist agents, backed by MCPClient."""

    def __init__(self, client: MCPClient, registry: MCPToolRegistry) -> None:
        self.client = client
        self.registry = registry

    def call_tool(self, tool_name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        server, tool = self._resolve_tool(tool_name)
        result = asyncio.run(self.client.call_tool(server, tool, dict(arguments)))
        if not result.ok:
            if result.error is None:
                raise RuntimeError(f"MCP tool {server}.{tool} failed")
            raise RuntimeError(result.error.message)
        return dict(result.data or {})

    def _resolve_tool(self, tool_name: str) -> tuple[str, str]:
        try:
            binding = self.registry.resolve_capability(tool_name)
            return binding.server, binding.tool
        except MCPRegistryError:
            pass

        if "." not in tool_name:
            raise RuntimeError(
                f"MCP tool {tool_name!r} is not a registered capability and is not in server.tool form."
            )
        server, tool = tool_name.split(".", 1)
        self.registry.require_tool(server, tool)
        return server, tool

