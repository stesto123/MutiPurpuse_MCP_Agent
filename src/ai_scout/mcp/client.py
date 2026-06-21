from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from .models import ToolCallResult


class MCPClient(Protocol):
    """Async interface implemented by real and fake MCP clients."""

    async def call_tool(
        self,
        server: str,
        tool: str,
        arguments: Mapping[str, Any],
        *,
        timeout_s: float | None = None,
    ) -> ToolCallResult:
        """Call one configured MCP tool and return a structured result."""
        ...
