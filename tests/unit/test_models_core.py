from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ai_scout.models import (  # noqa: E402
    ActivityKind,
    CalendarEventDraft,
    CalendarWindow,
    LearningActivity,
    Resource,
    ResourceCandidate,
    ResourceKind,
    ScoutRun,
)


class ModelCoreTests(TestCase):
    def test_resource_candidate_models_normalize_fields_and_ids(self) -> None:
        published_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
        discovered_at = datetime(2026, 6, 21, tzinfo=timezone.utc)

        resource = Resource(
            title="  LangGraph MCP Scout  ",
            kind="github_repo",
            url="https://github.com/Example/Scout.git ",
            topics=("MCP", " mcp ", "LangGraph"),
            published_at=published_at,
            metadata={"stars": 100},
        )
        candidate = ResourceCandidate(
            resource=resource,
            discovered_at=discovered_at,
            discovery_source=" fake-mcp ",
            source_quality=0.8,
            effort_minutes=45,
            local_applicability=0.9,
            tags=(" Agent ", "agent"),
        )

        self.assertEqual(resource.title, "LangGraph MCP Scout")
        self.assertIs(resource.kind, ResourceKind.GITHUB_REPO)
        self.assertEqual(resource.topics, ("mcp", "langgraph"))
        self.assertTrue(resource.resource_id.startswith("res_"))
        self.assertEqual(candidate.discovery_source, "fake-mcp")
        self.assertEqual(candidate.tags, ("agent",))
        self.assertTrue(candidate.candidate_id.startswith("cand_"))


    def test_learning_activity_from_candidate_uses_resource_kind_defaults(self) -> None:
        candidate = ResourceCandidate(
            resource=Resource(
                title="AI Systems Paper",
                kind=ResourceKind.PAPER,
                url="https://example.test/paper",
            ),
            discovered_at=datetime(2026, 6, 21, tzinfo=timezone.utc),
            effort_minutes=60,
        )

        activity = LearningActivity.from_candidate(
            candidate,
            priority_score=0.72,
            reason="ranked highly",
            run_id="run_test",
        )

        self.assertIs(activity.kind, ActivityKind.READ)
        self.assertEqual(activity.duration_minutes, 60)
        self.assertEqual(activity.priority_score, 0.72)
        self.assertTrue(activity.activity_id.startswith("act_"))


    def test_calendar_event_draft_carries_idempotency_key(self) -> None:
        start = datetime(2026, 6, 22, 9, 0, tzinfo=timezone.utc)
        activity = LearningActivity(
            resource_id="res_test",
            title="Inspect local repo",
            kind=ActivityKind.INSPECT_REPO,
            duration_minutes=30,
            priority_score=0.8,
        )
        window = CalendarWindow(start=start, end=start + timedelta(hours=1), label="morning")
        event = CalendarEventDraft(
            activity=activity,
            start=window.start,
            end=window.start + timedelta(minutes=30),
            window_label=window.label,
        )

        self.assertEqual(event.window_label, "morning")
        self.assertTrue(event.idempotency_key.startswith("cal_"))


    def test_run_model_rejects_negative_candidate_count(self) -> None:
        with self.assertRaises(ValueError) as context:
            ScoutRun(
            started_at=datetime(2026, 6, 21, tzinfo=timezone.utc),
            candidate_count=-1,
            )
        self.assertIn("candidate_count", str(context.exception))
