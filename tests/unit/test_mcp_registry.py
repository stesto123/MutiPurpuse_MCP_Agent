from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ai_scout.mcp import Capability, ErrorCode, MCPRegistryError, MCPToolRegistry

FIXTURE = ROOT / "tests" / "fixtures" / "mcp" / "registry.example.json"


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


if __name__ == "__main__":
    unittest.main()
