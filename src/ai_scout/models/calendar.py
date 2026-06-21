from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256

from ai_scout.models.activities import LearningActivity


def _clean_label(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.strip().split())
    return cleaned or None


def _validate_datetime_pair(start: datetime, end: datetime) -> None:
    if end <= start:
        raise ValueError("end must be after start")
    if (start.tzinfo is None) != (end.tzinfo is None):
        raise ValueError("start and end must both be timezone-aware or both be naive")


@dataclass(frozen=True)
class CalendarWindow:
    """An available local planning window supplied by a boundary layer."""

    start: datetime
    end: datetime
    label: str | None = None

    def __post_init__(self) -> None:
        _validate_datetime_pair(self.start, self.end)
        object.__setattr__(self, "label", _clean_label(self.label))

    @property
    def duration_minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


@dataclass(frozen=True)
class SchedulingPolicy:
    """Calendar planning constraints without any external calendar coupling."""

    min_activity_minutes: int = 15
    max_activity_minutes: int = 120
    buffer_minutes: int = 10
    max_daily_minutes: int = 180
    max_activities_per_day: int = 3
    round_to_minutes: int = 5
    allowed_weekdays: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6)

    def __post_init__(self) -> None:
        if self.min_activity_minutes <= 0:
            raise ValueError("min_activity_minutes must be positive")
        if self.max_activity_minutes < self.min_activity_minutes:
            raise ValueError("max_activity_minutes must be at least min_activity_minutes")
        if self.buffer_minutes < 0:
            raise ValueError("buffer_minutes cannot be negative")
        if self.max_daily_minutes < self.min_activity_minutes:
            raise ValueError("max_daily_minutes must be at least min_activity_minutes")
        if self.max_activities_per_day <= 0:
            raise ValueError("max_activities_per_day must be positive")
        if self.round_to_minutes <= 0 or self.round_to_minutes > 60:
            raise ValueError("round_to_minutes must be between 1 and 60")

        weekdays = tuple(dict.fromkeys(int(day) for day in self.allowed_weekdays))
        if not weekdays or any(day < 0 or day > 6 for day in weekdays):
            raise ValueError("allowed_weekdays must contain values from 0 to 6")
        object.__setattr__(self, "allowed_weekdays", weekdays)


def make_calendar_idempotency_key(activity_id: str, start: datetime) -> str:
    payload = f"{activity_id}:{start.isoformat()}"
    return "cal_" + sha256(payload.encode("utf-8")).hexdigest()[:20]


@dataclass(frozen=True)
class CalendarEventDraft:
    """A planned event draft to be handed to an MCP calendar boundary later."""

    activity: LearningActivity
    start: datetime
    end: datetime
    window_label: str | None = None
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        _validate_datetime_pair(self.start, self.end)
        expected_minutes = int((self.end - self.start).total_seconds() // 60)
        if expected_minutes != self.activity.duration_minutes:
            raise ValueError("event duration must match activity duration")

        key = self.idempotency_key
        if key is None:
            key = make_calendar_idempotency_key(self.activity.activity_id or "", self.start)
        else:
            key = " ".join(key.strip().split())
            if not key:
                raise ValueError("idempotency_key cannot be empty")

        object.__setattr__(self, "window_label", _clean_label(self.window_label))
        object.__setattr__(self, "idempotency_key", key)


@dataclass(frozen=True)
class UnscheduledActivity:
    activity: LearningActivity
    reason: str

    def __post_init__(self) -> None:
        reason = " ".join(self.reason.strip().split())
        if not reason:
            raise ValueError("reason cannot be empty")
        object.__setattr__(self, "reason", reason)


@dataclass(frozen=True)
class CalendarPlan:
    events: tuple[CalendarEventDraft, ...]
    unscheduled: tuple[UnscheduledActivity, ...]
    policy: SchedulingPolicy

    @property
    def planned_activity_ids(self) -> tuple[str, ...]:
        return tuple(event.activity.activity_id or "" for event in self.events)

    @property
    def total_planned_minutes(self) -> int:
        return sum(event.activity.duration_minutes for event in self.events)

    def planned_minutes_by_day(self) -> dict[date, int]:
        totals: dict[date, int] = {}
        for event in self.events:
            day = event.start.date()
            totals[day] = totals.get(day, 0) + event.activity.duration_minutes
        return totals


def ensure_calendar_windows(windows: Iterable[CalendarWindow]) -> tuple[CalendarWindow, ...]:
    return tuple(sorted(windows, key=lambda window: (window.start, window.end)))
