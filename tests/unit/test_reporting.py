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
