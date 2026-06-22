from __future__ import annotations

import asyncio
import sys
import types
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ai_scout.mcp import (
    ErrorCode,
    MCPToolRegistry,
    StdioMCPClient,
    SyncMCPToolGateway,
    ToolCallResult,
)
from ai_scout.mcp.stdio_client import _resolve_command


class RecordingMCPClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def call_tool(
        self,
        server: str,
        tool: str,
        arguments: Mapping[str, Any],
        *,
        timeout_s: float | None = None,
    ) -> ToolCallResult:
        self.calls.append(
            {
                "server": server,
                "tool": tool,
                "arguments": dict(arguments),
                "timeout_s": timeout_s,
            }
        )
        return ToolCallResult.success(server, tool, {"items": []})


class SlowStdioContext:
    async def __aenter__(self) -> tuple[object, object]:
        return object(), object()

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class SlowClientSession:
    def __init__(self, read: object, write: object) -> None:
        self.read = read
        self.write = write

    async def __aenter__(self) -> SlowClientSession:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    async def initialize(self) -> None:
        return None

    async def call_tool(self, tool: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        del tool, arguments
        await asyncio.sleep(0.1)
        return {"items": []}


class StdioServerParameters:
    def __init__(
        self,
        *,
        command: str,
        args: list[str],
        env: dict[str, str] | None,
    ) -> None:
        self.command = command
        self.args = args
        self.env = env


def slow_stdio_client(params: StdioServerParameters) -> SlowStdioContext:
    del params
    return SlowStdioContext()


def stdio_registry(timeout_s: float = 0.01) -> MCPToolRegistry:
    return MCPToolRegistry.from_mapping(
        {
            "servers": [
                {
                    "name": "stdio_services",
                    "enabled": True,
                    "default_timeout_s": timeout_s,
                    "transport": {"type": "stdio", "command": "fake-mcp-server"},
                    "tools": [{"name": "slow_tool", "allow": True}],
                }
            ]
        }
    )


class StdioMCPClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_client_returns_retryable_timeout(self) -> None:
        registry = stdio_registry(timeout_s=0.01)
        client = StdioMCPClient(registry)
        installed = _install_fake_mcp_modules()
        try:
            result = await client.call_tool("stdio_services", "slow_tool", {})
        finally:
            _restore_modules(installed)

        self.assertFalse(result.ok)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, ErrorCode.TIMEOUT)
        self.assertTrue(result.error.retryable)


class StdioMCPCommandTests(unittest.TestCase):
    def test_python_command_uses_current_interpreter_by_default(self) -> None:
        self.assertEqual(_resolve_command("python3", {}), sys.executable)
        self.assertEqual(_resolve_command("python", {}), sys.executable)
        self.assertEqual(_resolve_command("python3", {"use_current_python": False}), "python3")
        self.assertEqual(_resolve_command("/usr/bin/python3", {}), "/usr/bin/python3")


class SyncMCPToolGatewayTests(unittest.TestCase):
    def test_sync_gateway_passes_registry_timeout_to_client(self) -> None:
        registry = MCPToolRegistry.from_mapping(
            {
                "servers": [
                    {
                        "name": "fake_services",
                        "default_timeout_s": 0.25,
                        "tools": [{"name": "search_resources", "allow": True}],
                    }
                ]
            }
        )
        client = RecordingMCPClient()
        gateway = SyncMCPToolGateway(client, registry)

        result = gateway.call_tool("fake_services.search_resources", {"query": "mcp"})

        self.assertEqual(result, {"items": []})
        self.assertEqual(client.calls[0]["timeout_s"], 0.25)


def _install_fake_mcp_modules() -> dict[str, types.ModuleType | None]:
    module_names = ("mcp", "mcp.client", "mcp.client.stdio")
    previous = {name: sys.modules.get(name) for name in module_names}

    mcp_module = types.ModuleType("mcp")
    mcp_module.__path__ = []  # type: ignore[attr-defined]
    mcp_module.ClientSession = SlowClientSession
    mcp_module.StdioServerParameters = StdioServerParameters

    client_module = types.ModuleType("mcp.client")
    client_module.__path__ = []  # type: ignore[attr-defined]

    stdio_module = types.ModuleType("mcp.client.stdio")
    stdio_module.stdio_client = slow_stdio_client

    sys.modules["mcp"] = mcp_module
    sys.modules["mcp.client"] = client_module
    sys.modules["mcp.client.stdio"] = stdio_module
    return previous


def _restore_modules(previous: Mapping[str, types.ModuleType | None]) -> None:
    for name, module in previous.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


if __name__ == "__main__":
    unittest.main()
