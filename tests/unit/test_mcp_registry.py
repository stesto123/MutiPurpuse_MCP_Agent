from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ai_scout.mcp import Capability, ErrorCode, MCPRegistryError, MCPToolRegistry

FIXTURE = ROOT / "tests" / "fixtures" / "mcp" / "registry.example.json"
EXAMPLE_CONFIG = ROOT / "config" / "mcp" / "servers.example.yaml"
FIRST_RUN_CONFIG = ROOT / "config" / "mcp" / "first-run.example.yaml"
WEB_RSS_CONFIG = ROOT / "config" / "mcp" / "web-rss.example.yaml"


class MCPRegistryTests(unittest.TestCase):
    def test_loads_fixture_and_resolves_capability(self) -> None:
        registry = MCPToolRegistry.from_file(FIXTURE)

        binding = registry.resolve_capability(Capability.DISCOVERY_SEARCH)

        self.assertEqual(binding.server, "fake_services")
        self.assertEqual(binding.tool, "search_resources")
        self.assertEqual(binding.timeout_s, 0.25)

    def test_rejects_unconfigured_tool_calls(self) -> None:
        registry = MCPToolRegistry.from_file(FIXTURE)

        with self.assertRaises(MCPRegistryError) as context:
            registry.validate_tool_call("fake_services", "direct_github_api", {"repository": "owner/repo"})

        self.assertEqual(context.exception.code, ErrorCode.TOOL_NOT_ALLOWED)

    def test_validates_required_inputs(self) -> None:
        registry = MCPToolRegistry.from_file(FIXTURE)

        with self.assertRaises(MCPRegistryError) as context:
            registry.validate_tool_call("fake_services", "search_resources", {"limit": 5})

        self.assertEqual(context.exception.code, ErrorCode.VALIDATION_ERROR)
        self.assertEqual(context.exception.details["missing"], ["query"])

    def test_redacts_arguments_for_logs(self) -> None:
        registry = MCPToolRegistry.from_file(FIXTURE)

        redacted = registry.redact_arguments(
            "fake_services",
            "search_resources",
            {
                "query": "ai agents",
                "api_key": "secret-value",
                "url": "https://example.test/search?access_token=secret-token&q=agents",
                "normal_url": "https://example.test/search?q=agents",
            },
        )

        self.assertEqual(redacted["api_key"], "[REDACTED]")
        self.assertNotIn("secret-token", redacted["url"])
        self.assertEqual(redacted["normal_url"], "https://example.test/search?q=agents")

    def test_rejects_duplicate_capability_bindings(self) -> None:
        config = {
            "servers": [
                {
                    "name": "fake",
                    "tools": [
                        {"name": "one", "capabilities": ["discovery.search"]},
                        {"name": "two", "capabilities": ["discovery.search"]},
                    ],
                }
            ]
        }

        with self.assertRaises(MCPRegistryError) as context:
            MCPToolRegistry.from_mapping(config)

        self.assertEqual(context.exception.code, ErrorCode.INVALID_CONFIG)

    def test_public_example_includes_first_run_local_mcp_tools(self) -> None:
        registry = MCPToolRegistry.from_file(EXAMPLE_CONFIG)

        servers = registry.servers
        self.assertIn("sources", servers)
        self.assertIn("content", servers)
        self.assertIn("discover", servers["sources"].tools)
        self.assertIn("inspect", servers["content"].tools)
        self.assertEqual(
            servers["content"].tools["inspect"].required_outputs,
            ("content_summary", "signals", "estimated_minutes"),
        )

    def test_first_run_example_enables_only_local_mcp_tools(self) -> None:
        registry = MCPToolRegistry.from_file(FIRST_RUN_CONFIG)

        self.assertTrue(registry.get_server("sources").enabled)
        self.assertTrue(registry.get_server("content").enabled)
        registry.validate_tool_call("sources", "discover", {"topics": ["MCP"]})
        registry.validate_tool_call("content", "inspect", {"resource": {"title": "MCP"}})

    def test_web_rss_example_enables_rss_and_content_tools(self) -> None:
        registry = MCPToolRegistry.from_file(WEB_RSS_CONFIG)

        self.assertTrue(registry.get_server("rss").enabled)
        self.assertTrue(registry.get_server("content").enabled)
        registry.validate_tool_call(
            "rss",
            "fetch_feed",
            {"locator": "https://example.test/feed.xml"},
        )
        registry.validate_tool_call("content", "inspect", {"resource": {"title": "MCP"}})


if __name__ == "__main__":
    unittest.main()
