from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ai_scout.models import (  # noqa: E402
    ActivityKind,
    CalendarWindow,
    LearningActivity,
    SchedulingPolicy,
)
from ai_scout.scheduling import plan_calendar_slots  # noqa: E402


def _activity(
    title: str,
    *,
    duration: int,
    priority: float,
    resource_id: str | None = None,
) -> LearningActivity:
    return LearningActivity(
        resource_id=resource_id or f"res_{title.casefold().replace(' ', '_')}",
        title=title,
        kind=ActivityKind.READ,
        duration_minutes=duration,
        priority_score=priority,
    )


class SchedulingCoreTests(TestCase):
    def test_calendar_planner_schedules_high_priority_first_with_buffer(self) -> None:
        start = datetime(2026, 6, 22, 9, 0, tzinfo=timezone.utc)
        low = _activity("Low priority article", duration=30, priority=0.2)
        high = _activity("High priority repo", duration=60, priority=0.9)

        plan = plan_calendar_slots(
            (low, high),
            (CalendarWindow(start=start, end=start + timedelta(hours=2), label="morning"),),
            SchedulingPolicy(buffer_minutes=10, round_to_minutes=5),
        )

        self.assertEqual(
            [event.activity.title for event in plan.events],
            ["High priority repo", "Low priority article"],
        )
        self.assertEqual(plan.events[0].start, start)
        self.assertEqual(plan.events[0].end, start + timedelta(minutes=60))
        self.assertEqual(plan.events[1].start, start + timedelta(minutes=70))
        self.assertEqual(plan.unscheduled, ())

    def test_calendar_planner_rounds_window_start(self) -> None:
        start = datetime(2026, 6, 22, 9, 3, 30, tzinfo=timezone.utc)
        activity = _activity("Rounded activity", duration=30, priority=0.5)

        plan = plan_calendar_slots(
            (activity,),
            (CalendarWindow(start=start, end=start + timedelta(hours=1)),),
            SchedulingPolicy(round_to_minutes=15),
        )

        self.assertEqual(plan.events[0].start, datetime(2026, 6, 22, 9, 15, tzinfo=timezone.utc))
        self.assertEqual(plan.events[0].end, datetime(2026, 6, 22, 9, 45, tzinfo=timezone.utc))

    def test_calendar_planner_enforces_daily_limits(self) -> None:
        start = datetime(2026, 6, 22, 9, 0, tzinfo=timezone.utc)
        first = _activity("First", duration=45, priority=0.8)
        second = _activity("Second", duration=30, priority=0.7)

        plan = plan_calendar_slots(
            (first, second),
            (CalendarWindow(start=start, end=start + timedelta(hours=3)),),
            SchedulingPolicy(max_daily_minutes=60),
        )

        self.assertEqual(plan.planned_activity_ids, (first.activity_id,))
        self.assertEqual(plan.total_planned_minutes, 45)
        self.assertEqual(len(plan.unscheduled), 1)
        self.assertIs(plan.unscheduled[0].activity, second)

    def test_calendar_planner_rejects_activity_outside_duration_policy(self) -> None:
        start = datetime(2026, 6, 22, 9, 0, tzinfo=timezone.utc)
        too_long = _activity("Too long", duration=180, priority=1.0)

        plan = plan_calendar_slots(
            (too_long,),
            (CalendarWindow(start=start, end=start + timedelta(hours=4)),),
            SchedulingPolicy(max_activity_minutes=120),
        )

        self.assertEqual(plan.events, ())
        self.assertEqual(
            plan.unscheduled[0].reason,
            "activity exceeds the maximum schedulable duration",
        )
