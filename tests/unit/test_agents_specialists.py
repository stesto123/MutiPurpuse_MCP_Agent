from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from typing import Any
from unittest import TestCase

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from ai_scout.agents import (  # noqa: E402
    AuditAgent,
    CalendarExecutionAgent,
    DeduplicationAgent,
    DiscoveryAgent,
    InspectionAgent,
    PlanningAgent,
    RankingAgent,
    RetryPolicy,
)


class FakeMCPGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail_once: set[str] = set()

    def call_tool(self, tool_name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append((tool_name, dict(arguments)))
        if tool_name in self.fail_once:
            self.fail_once.remove(tool_name)
            raise RuntimeError("transient failure")
        if tool_name == "sources.discover":
            return {
                "items": [
                    {
                        "title": "Model Context Protocol Guide",
                        "url": "https://example.test/mcp",
                        "summary": "Practical MCP notes",
                    }
                ]
            }
        if tool_name == "content.inspect":
            return {
                "summary": "Inspection summary",
                "signals": {"relevance": 0.9, "novelty": 0.8, "source_trust": 0.7},
                "estimated_minutes": 30,
            }
        if tool_name == "calendar.read_availability":
            return {"slots": [{"start": "2026-07-01T09:00:00Z", "end": "2026-07-01T09:30:00Z"}]}
        if tool_name == "calendar.create_event":
            return {"status": "created", "event_id": "evt_1"}
        raise AssertionError(f"unexpected tool {tool_name}")


class SpecialistAgentTests(TestCase):
    def test_discovery_and_inspection_use_mcp_gateway_with_retry(self) -> None:
        gateway = FakeMCPGateway()
        gateway.fail_once.add("content.inspect")

        discovery = DiscoveryAgent(gateway)
        discovered = discovery.run({"profile": {"topics": ["MCP"]}})

        inspection = InspectionAgent(gateway, RetryPolicy(max_attempts=2))
        inspected = inspection.run(discovered.items)

        self.assertEqual(discovered.items[0]["title"], "Model Context Protocol Guide")
        self.assertEqual(inspected.items[0]["status"], "inspected")
        self.assertEqual(inspected.items[0]["signals"]["relevance"], 0.9)
        self.assertEqual([call[0] for call in gateway.calls].count("content.inspect"), 2)
        self.assertTrue(any(entry["event"] == "tool_call_failed" for entry in inspected.log))
        self.assertEqual(inspected.errors, [])

    def test_deduplication_marks_memory_and_current_duplicates(self) -> None:
        first = {
            "resource": {
                "id": "res_a",
                "source": "test",
                "title": "A",
                "url": "https://example.test/a?utm=ignored",
            }
        }
        second = {
            "resource": {
                "id": "res_b",
                "source": "test",
                "title": "A copy",
                "url": "https://example.test/a",
            }
        }
        third = {
            "resource": {
                "id": "res_seen",
                "source": "test",
                "title": "Seen",
                "url": "https://example.test/seen",
            }
        }

        result = DeduplicationAgent().run(
            [first, second, third],
            {"seen_resource_ids": ["res_seen"], "seen_urls": [], "seen_fingerprints": []},
        )

        self.assertFalse(result.items[0]["is_duplicate"])
        self.assertTrue(result.items[1]["is_duplicate"])
        self.assertEqual(result.items[1]["duplicate_of"], "res_a")
        self.assertTrue(result.items[2]["is_duplicate"])
        self.assertEqual(result.items[2]["dedupe_reason"], "memory_resource_id")

    def test_ranking_planning_calendar_and_audit_are_structured(self) -> None:
        gateway = FakeMCPGateway()
        deduped = [
            {
                "resource": {
                    "id": "res_a",
                    "source": "test",
                    "title": "A",
                    "url": "https://example.test/a",
                },
                "content_summary": "Summary",
                "signals": {"relevance": 1.0, "novelty": 0.8, "source_trust": 0.8},
                "estimated_minutes": 30,
                "is_duplicate": False,
            }
        ]

        ranked = RankingAgent().run(deduped, {"min_score": 0.1})
        planned = PlanningAgent().run(ranked.items, {"max_activities": 1}, run_id="run_1")
        calendar = CalendarExecutionAgent(gateway)
        availability = calendar.read_availability({"run_id": "run_1"})
        events = calendar.write_events(planned.items, availability.items, {"run_id": "run_1"})
        audit = AuditAgent().run(
            deduplicated_items=deduped,
            calendar_events=events.items,
            side_effects=events.side_effects,
            errors=[],
            log=events.log,
        )

        self.assertGreater(ranked.items[0]["score"], 0.8)
        self.assertEqual(planned.items[0]["resource_id"], "res_a")
        self.assertEqual(events.items[0]["status"], "created")
        self.assertEqual(events.side_effects[0]["type"], "calendar_event")
        self.assertEqual(audit.items[0]["status"], "passed")
