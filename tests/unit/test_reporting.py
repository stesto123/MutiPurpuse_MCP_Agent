from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from ai_scout.reporting import ReportWriter


class ReportWriterTests(TestCase):
    def test_report_writer_creates_markdown_and_json(self) -> None:
        with TemporaryDirectory() as raw_dir:
            tmp_path = Path(raw_dir)
            writer = ReportWriter(tmp_path / "reports", tmp_path / "runs")

            written = writer.write(
                "run-1",
                {
                    "mode": "dry_run",
                    "status": "completed",
                    "selected_resources": [{"title": "Example", "url": "https://example.test"}],
                },
            )

            self.assertTrue(written["markdown"].exists())
            self.assertTrue(written["json"].exists())
            self.assertIn("Example", written["markdown"].read_text(encoding="utf-8"))

    def test_report_writer_renders_graph_ranked_items_and_learning_plan(self) -> None:
        with TemporaryDirectory() as raw_dir:
            tmp_path = Path(raw_dir)
            writer = ReportWriter(tmp_path / "reports", tmp_path / "runs")

            written = writer.write(
                "run-graph",
                {
                    "mode": "dry_run",
                    "status": "completed",
                    "ranked": [
                        {
                            "resource": {
                                "title": "LangGraph + MCP local agent patterns",
                                "url": "https://example.test/ai-scout/langgraph-mcp-patterns",
                            },
                            "score": 0.8123,
                        }
                    ],
                    "learning_plan": [
                        {
                            "title": "Review: LangGraph + MCP local agent patterns",
                            "duration_minutes": 30,
                        }
                    ],
                },
            )

            markdown = written["markdown"].read_text(encoding="utf-8")
            self.assertIn("## Selected Resources", markdown)
            self.assertIn("LangGraph + MCP local agent patterns score=0.8123", markdown)
            self.assertIn("https://example.test/ai-scout/langgraph-mcp-patterns", markdown)
            self.assertIn("## Planned Activities", markdown)
            self.assertIn("Review: LangGraph + MCP local agent patterns (30 min)", markdown)
