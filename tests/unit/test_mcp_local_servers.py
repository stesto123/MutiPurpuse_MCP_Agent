from __future__ import annotations

from unittest import TestCase
from unittest.mock import patch

from ai_scout.mcp_servers.content_inspector import inspect_resource
from ai_scout.mcp_servers.local_sources import discover_resources
from ai_scout.mcp_servers.web_feed import fetch_feed, parse_feed_bytes


class LocalMCPServerLogicTests(TestCase):
    def test_local_sources_return_discovery_contract(self) -> None:
        result = discover_resources(topics=["MCP"], max_results=2)

        self.assertEqual(result["source"], "built-in-local-sources")
        self.assertEqual(len(result["resources"]), 2)
        self.assertIn("title", result["resources"][0])
        self.assertIn("url", result["resources"][0])

    def test_content_inspector_returns_graph_contract(self) -> None:
        result = inspect_resource(
            {
                "title": "Runnable local AI agent evaluation repo",
                "url": "https://github.com/example/local-agent-evals",
                "summary": "Repository with local-first eval examples.",
                "metadata": {"kind": "github_repo", "tags": ["evals", "mcp"]},
            }
        )

        self.assertEqual(result["content_summary"], "Repository with local-first eval examples.")
        self.assertIn("signals", result)
        self.assertGreaterEqual(result["signals"]["relevance"], 0.75)
        self.assertEqual(result["estimated_minutes"], 60)
        self.assertEqual(result["metadata"]["inspection_strategy"], "metadata_heuristic_v1")

    def test_web_feed_parser_returns_resources(self) -> None:
        feed = b"""<?xml version="1.0"?>
        <rss><channel>
          <item>
            <title>New MCP agent pattern</title>
            <link>https://example.test/mcp-agent</link>
            <description><![CDATA[<p>Practical AI agent notes.</p>]]></description>
            <pubDate>Mon, 01 Jun 2026 10:00:00 GMT</pubDate>
          </item>
        </channel></rss>
        """

        resources = parse_feed_bytes(
            feed,
            feed_url="https://example.test/feed.xml",
            max_results=5,
            topics=["agent"],
            source_id="example-feed",
            kind="rss",
        )

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["source"], "example-feed")
        self.assertEqual(resources[0]["title"], "New MCP agent pattern")
        self.assertEqual(resources[0]["summary"], "Practical AI agent notes.")
        self.assertTrue(resources[0]["metadata"]["content_is_untrusted"])

    def test_web_feed_source_limit_takes_precedence(self) -> None:
        feed = b"""<?xml version="1.0"?>
        <rss><channel>
          <item><title>One</title><link>https://example.test/one</link></item>
          <item><title>Two</title><link>https://example.test/two</link></item>
        </channel></rss>
        """

        with patch("ai_scout.mcp_servers.web_feed._fetch_bytes", return_value=feed):
            result = fetch_feed(
                "https://example.test/feed.xml",
                max_results=10,
                max_items_per_run=1,
            )

        self.assertEqual(len(result["resources"]), 1)
