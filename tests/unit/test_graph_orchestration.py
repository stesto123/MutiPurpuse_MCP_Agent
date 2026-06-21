from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence
from typing import Any
from unittest import TestCase

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from ai_scout.graph import (  # noqa: E402
    GraphDependencies,
    SequentialScoutGraph,
    build_scout_graph,
    new_state,
    run_scout,
)


class FakeMCPGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call_tool(self, tool_name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append((tool_name, dict(arguments)))
        if tool_name == "sources.discover":
            return {
                "resources": [
                    {
                        "id": "res_graph",
                        "source": "fixture",
                        "title": "Graph Resource",
                        "url": "https://example.test/graph",
                    }
                ]
            }
        if tool_name == "content.inspect":
            return {
                "content_summary": "Useful graph resource",
                "signals": {"relevance": 0.95, "novelty": 0.9, "source_trust": 0.8},
                "estimated_minutes": 25,
            }
        if tool_name == "calendar.read_availability":
            return {"slots": [{"start": "2026-07-02T10:00:00Z", "end": "2026-07-02T10:30:00Z"}]}
        if tool_name == "calendar.create_event":
            return {"status": "created", "event_id": "evt_graph"}
        raise AssertionError(f"unexpected tool {tool_name}")


class FakeMemoryStore:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def load_snapshot(self, run_id: str) -> Mapping[str, Any]:
        assert run_id == "run_graph"
        return {"seen_resource_ids": [], "seen_urls": [], "seen_fingerprints": []}

    def write_records(
        self, run_id: str, records: Sequence[Mapping[str, Any]]
    ) -> Mapping[str, Any]:
        assert run_id == "run_graph"
        self.records = [dict(record) for record in records]
        return {"status": "written", "count": len(self.records)}


class FakeReportSink:
    def __init__(self) -> None:
        self.report: dict[str, Any] = {}

    def write_run_report(self, run_id: str, report: Mapping[str, Any]) -> Mapping[str, Any]:
        assert run_id == "run_graph"
        self.report = dict(report)
        return {"status": "written", "artifact": "fake://run_graph"}


class GraphOrchestrationTests(TestCase):
    def test_sequential_graph_runs_all_specialist_nodes_with_fake_dependencies(self) -> None:
        gateway = FakeMCPGateway()
        memory = FakeMemoryStore()
        reports = FakeReportSink()
        deps = GraphDependencies(mcp=gateway, memory_store=memory, report_sink=reports)
        state = new_state(
            run_id="run_graph",
            profile={"topics": ["AI agents"]},
            policy={"max_activities": 1, "min_score": 0.1},
        )

        result = run_scout(state, deps, prefer_langgraph=False)

        self.assertEqual(result["last_node"], "audit_run")
        self.assertEqual(result["candidates"][0]["id"], "res_graph")
        self.assertEqual(result["ranked"][0]["rank"], 1)
        self.assertEqual(result["learning_plan"][0]["resource_id"], "res_graph")
        self.assertEqual(result["calendar_events"][0]["event_id"], "evt_graph")
        self.assertEqual(memory.records[0]["resource_id"], "res_graph")
        self.assertEqual(reports.report["ranked_count"], 1)
        self.assertEqual(result["audit"]["status"], "passed")
        self.assertEqual(
            [call[0] for call in gateway.calls],
            [
                "sources.discover",
                "content.inspect",
                "calendar.read_availability",
                "calendar.create_event",
            ],
        )

    def test_build_graph_can_force_clean_fallback_runner(self) -> None:
        deps = GraphDependencies(mcp=FakeMCPGateway())
        graph = build_scout_graph(deps, prefer_langgraph=False)

        self.assertIsInstance(graph, SequentialScoutGraph)

    def test_dry_run_policy_skips_calendar_write_tool(self) -> None:
        gateway = FakeMCPGateway()
        deps = GraphDependencies(
            mcp=gateway,
            memory_store=FakeMemoryStore(),
            report_sink=FakeReportSink(),
        )
        state = new_state(
            run_id="run_graph",
            profile={"topics": ["AI agents"]},
            policy={
                "max_activities": 1,
                "min_score": 0.1,
                "permissions": {"dry_run": {"calendar_writes_via_mcp": False}},
            },
        )
        state["mode"] = "dry_run"

        result = run_scout(state, deps, prefer_langgraph=False)

        self.assertEqual(result["calendar_events"][0]["status"], "dry_run_skipped")
        self.assertNotIn("calendar.create_event", [call[0] for call in gateway.calls])
