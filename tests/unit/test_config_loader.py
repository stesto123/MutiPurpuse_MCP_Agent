from __future__ import annotations

from pathlib import Path
from unittest import TestCase

from ai_scout.config.loader import ConfigError, load_app_config


class ConfigLoaderTests(TestCase):
    def test_load_app_config_allows_missing_files(self) -> None:
        config = load_app_config(Path(self._testMethodName), allow_missing=True)

        self.assertEqual(config.mode, "dry_run")
        self.assertTrue(config.dry_run)

    def test_load_app_config_validates_mode(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as raw_dir:
            tmp_path = Path(raw_dir)
            (tmp_path / "policy.yaml").write_text("mode: chaos\n", encoding="utf-8")

            with self.assertRaises(ConfigError):
                load_app_config(tmp_path, allow_missing=True)

    def test_load_app_config_reads_yaml(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as raw_dir:
            tmp_path = Path(raw_dir)
            (tmp_path / "profile.yaml").write_text(
                "interests:\n  - LangGraph\n  - MCP\n",
                encoding="utf-8",
            )

            config = load_app_config(tmp_path, allow_missing=True)

            self.assertEqual(config.profile["interests"], ["LangGraph", "MCP"])
