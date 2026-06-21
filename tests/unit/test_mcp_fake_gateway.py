from __future__ import annotations

import asyncio
import sys
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ai_scout.mcp import ErrorCode, FakeMCPClient, MCPGateway, MCPToolRegistry

FIXTURE = ROOT / "tests" / "fixtures" / "mcp" / "registry.example.json"


class FakeMCPClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.registry = MCPToolRegistry.from_file(FIXTURE)
        self.client = FakeMCPClient(self.registry)
        self.gateway = MCPGateway(self.client, self.registry)

    async def test_gateway_search_uses_fake_tool_and_records_redacted_arguments(self) -> None:
        self.client.register_tool(
            "fake_services",
            "search_resources",
            lambda args: {"items": [{"title": args["query"], "url": "https://example.test/resource"}]},
        )

        result = await self.gateway.discovery_search(
            "mcp agents",
            filters={"api_key": "secret-value", "source": "https://example.test/?token=secret-token&x=1"},
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.data["items"][0]["title"], "mcp agents")
        self.assertEqual(len(self.client.calls), 1)
        recorded = self.client.calls[0]
        self.assertEqual(recorded.server, "fake_services")
        self.assertEqual(recorded.tool, "search_resources")
        self.assertNotIn("secret-value", str(recorded.arguments))
        self.assertNotIn("secret-token", str(recorded.arguments))

    async def test_timeout_returns_structured_retryable_error(self) -> None:
        async def slow_handler(args: Mapping[str, Any]) -> Mapping[str, Any]:
            await asyncio.sleep(0.1)
            return {"items": []}

        self.client.register_tool("fake_services", "search_resources", slow_handler)

        result = await self.client.call_tool(
            "fake_services",
            "search_resources",
            {"query": "slow"},
            timeout_s=0.01,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, ErrorCode.TIMEOUT)
        self.assertTrue(result.error.retryable)

    async def test_handler_exception_is_redacted(self) -> None:
        def broken_handler(args: Mapping[str, Any]) -> Mapping[str, Any]:
            raise RuntimeError("upstream failed with token=super-secret")

        self.client.register_tool("fake_services", "search_resources", broken_handler)

        result = await self.client.call_tool("fake_services", "search_resources", {"query": "x"})

        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, ErrorCode.TOOL_ERROR)
        self.assertNotIn("super-secret", result.error.message)
        self.assertIn("[REDACTED]", result.error.message)

    async def test_output_validation_failure_is_structured(self) -> None:
        self.client.register_tool("fake_services", "search_resources", lambda args: {"missing": []})

        result = await self.client.call_tool("fake_services", "search_resources", {"query": "x"})

        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, ErrorCode.OUTPUT_VALIDATION_ERROR)
        self.assertEqual(result.error.details["missing"], ["items"])

    async def test_calendar_and_report_writes_stay_generic_mcp_calls(self) -> None:
        self.client.register_tool(
            "fake_services",
            "calendar_write",
            lambda args: {
                "event_id": "event-1",
                "idempotency_key": args["idempotency_key"],
            },
        )
        self.client.register_tool(
            "fake_services",
            "report_write",
            lambda args: {
                "path": args["path"],
                "written": True,
                "run_id": args["run_id"],
            },
        )

        calendar_result = await self.gateway.write_calendar_event(
            {"title": "Read paper", "private_notes": "local-only"},
            idempotency_key="run-1:item-1",
        )
        report_result = await self.gateway.write_report(
            "data/reports/run-1.md",
            "# Run report\n",
            run_id="run-1",
        )

        self.assertTrue(calendar_result.ok)
        self.assertTrue(report_result.ok)
        self.assertEqual([call.tool for call in self.client.calls], ["calendar_write", "report_write"])
        self.assertNotIn("local-only", str(self.client.calls[0].arguments))
        self.assertNotIn("# Run report", str(self.client.calls[1].arguments))


if __name__ == "__main__":
    unittest.main()
