from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from ai_scout.memory import JsonlMemoryStore, PolicyMemoryStore


class MemoryStoreTests(TestCase):
    def test_memory_store_tracks_seen_resources(self) -> None:
        with TemporaryDirectory() as raw_dir:
            store = JsonlMemoryStore(Path(raw_dir))
            store.append_resource({"id": "resource-1", "url": "https://example.test/a"})

            self.assertIn("resource-1", store.seen_resource_keys())
            self.assertIn("https://example.test/a", store.seen_resource_keys())


    def test_memory_store_tracks_calendar_events(self) -> None:
        with TemporaryDirectory() as raw_dir:
            store = JsonlMemoryStore(Path(raw_dir))
            store.append_event({"calendar_event_id": "event-1"})

            self.assertEqual(store.created_calendar_event_ids(), {"event-1"})


    def test_policy_memory_store_skips_writes_when_disallowed(self) -> None:
        with TemporaryDirectory() as raw_dir:
            store = JsonlMemoryStore(Path(raw_dir))
            wrapped = PolicyMemoryStore(store, allow_writes=False)

            result = wrapped.write_records("run-1", [{"resource_id": "res-1"}])

            self.assertEqual(result["status"], "dry_run_skipped")
            self.assertEqual(store.seen_resource_keys(), set())
