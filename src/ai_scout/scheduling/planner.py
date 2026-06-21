from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from ai_scout.models import (
    CalendarEventDraft,
    CalendarPlan,
    CalendarWindow,
    LearningActivity,
    SchedulingPolicy,
    UnscheduledActivity,
    ensure_calendar_windows,
)


@dataclass
class _WindowCursor:
    window: CalendarWindow
    cursor: datetime


def plan_calendar_slots(
    activities: tuple[LearningActivity, ...],
    windows: tuple[CalendarWindow, ...],
    policy: SchedulingPolicy = SchedulingPolicy(),
) -> CalendarPlan:
    """Allocate activities to available windows without calling a calendar API."""

    ordered_windows = ensure_calendar_windows(windows)
    window_cursors = [
        _WindowCursor(window=window, cursor=_round_up(window.start, policy.round_to_minutes))
        for window in ordered_windows
    ]
    ordered_activities = _order_activities(activities)

    daily_minutes: defaultdict[date, int] = defaultdict(int)
    daily_counts: defaultdict[date, int] = defaultdict(int)
    events: list[CalendarEventDraft] = []
    unscheduled: list[UnscheduledActivity] = []

    for activity in ordered_activities:
        policy_reason = _activity_policy_rejection(activity, policy)
        if policy_reason is not None:
            unscheduled.append(UnscheduledActivity(activity=activity, reason=policy_reason))
            continue

        event = _place_activity(
            activity,
            window_cursors,
            policy,
            daily_minutes=daily_minutes,
            daily_counts=daily_counts,
        )
        if event is None:
            unscheduled.append(
                UnscheduledActivity(
                    activity=activity,
                    reason="no available window satisfies duration and daily limits",
                )
            )
            continue
        events.append(event)

    return CalendarPlan(
        events=tuple(sorted(events, key=lambda event: (event.start, event.activity.activity_id))),
        unscheduled=tuple(unscheduled),
        policy=policy,
    )


def _order_activities(
    activities: tuple[LearningActivity, ...],
) -> tuple[LearningActivity, ...]:
    indexed = tuple(enumerate(activities))
    return tuple(
        item[1]
        for item in sorted(
            indexed,
            key=lambda item: (-item[1].priority_score, item[0]),
        )
    )


def _activity_policy_rejection(
    activity: LearningActivity, policy: SchedulingPolicy
) -> str | None:
    if activity.duration_minutes < policy.min_activity_minutes:
        return "activity is shorter than the minimum schedulable duration"
    if activity.duration_minutes > policy.max_activity_minutes:
        return "activity exceeds the maximum schedulable duration"
    if activity.duration_minutes > policy.max_daily_minutes:
        return "activity exceeds the daily planning budget"
    return None


def _place_activity(
    activity: LearningActivity,
    window_cursors: list[_WindowCursor],
    policy: SchedulingPolicy,
    *,
    daily_minutes: defaultdict[date, int],
    daily_counts: defaultdict[date, int],
) -> CalendarEventDraft | None:
    duration = timedelta(minutes=activity.duration_minutes)
    buffer_delta = timedelta(minutes=policy.buffer_minutes)

    for cursor_state in window_cursors:
        start = _round_up(cursor_state.cursor, policy.round_to_minutes)
        if start.weekday() not in policy.allowed_weekdays:
            continue

        event_day = start.date()
        if daily_counts[event_day] >= policy.max_activities_per_day:
            continue
        if daily_minutes[event_day] + activity.duration_minutes > policy.max_daily_minutes:
            continue

        end = start + duration
        if end > cursor_state.window.end:
            continue

        event = CalendarEventDraft(
            activity=activity,
            start=start,
            end=end,
            window_label=cursor_state.window.label,
        )
        cursor_state.cursor = _round_up(end + buffer_delta, policy.round_to_minutes)
        daily_minutes[event_day] += activity.duration_minutes
        daily_counts[event_day] += 1
        return event

    return None


def _round_up(value: datetime, minutes: int) -> datetime:
    rounded = value.replace(second=0, microsecond=0)
    if value.second or value.microsecond:
        rounded += timedelta(minutes=1)

    remainder = rounded.minute % minutes
    if remainder:
        rounded += timedelta(minutes=minutes - remainder)
    return rounded
