from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256

from ai_scout.models.resources import ResourceCandidate, ResourceKind


class ActivityKind(str, Enum):
    READ = "read"
    WATCH = "watch"
    INSPECT_REPO = "inspect_repo"
    TRY_LOCALLY = "try_locally"
    SUMMARIZE = "summarize"
    REVIEW = "review"


def default_activity_kind_for_resource(kind: ResourceKind) -> ActivityKind:
    if kind is ResourceKind.GITHUB_REPO:
        return ActivityKind.INSPECT_REPO
    if kind is ResourceKind.VIDEO:
        return ActivityKind.WATCH
    if kind in {ResourceKind.ARTICLE, ResourceKind.PAPER}:
        return ActivityKind.READ
    return ActivityKind.REVIEW


@dataclass(frozen=True)
class LearningActivity:
    """A local calendar-ready activity derived from a candidate resource."""

    resource_id: str
    title: str
    kind: ActivityKind
    duration_minutes: int
    priority_score: float = 0.0
    reason: str | None = None
    run_id: str | None = None
    activity_id: str | None = None

    def __post_init__(self) -> None:
        title = " ".join(self.title.strip().split())
        if not title:
            raise ValueError("title cannot be empty")
        if self.duration_minutes <= 0:
            raise ValueError("duration_minutes must be positive")
        if self.priority_score < 0.0 or self.priority_score > 1.0:
            raise ValueError("priority_score must be between 0.0 and 1.0")

        kind = self.kind if isinstance(self.kind, ActivityKind) else ActivityKind(str(self.kind))
        reason = None if self.reason is None else " ".join(self.reason.strip().split()) or None
        run_id = None if self.run_id is None else " ".join(self.run_id.strip().split()) or None
        activity_id = self.activity_id
        if activity_id is None:
            payload = (
                f"{self.resource_id}:{kind.value}:{self.duration_minutes}:"
                f"{run_id or ''}"
            )
            activity_id = "act_" + sha256(payload.encode("utf-8")).hexdigest()[:20]
        else:
            activity_id = " ".join(activity_id.strip().split())
            if not activity_id:
                raise ValueError("activity_id cannot be empty")

        object.__setattr__(self, "title", title)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "run_id", run_id)
        object.__setattr__(self, "activity_id", activity_id)

    @classmethod
    def from_candidate(
        cls,
        candidate: ResourceCandidate,
        *,
        priority_score: float,
        duration_minutes: int | None = None,
        kind: ActivityKind | None = None,
        reason: str | None = None,
        run_id: str | None = None,
    ) -> LearningActivity:
        resource = candidate.resource
        return cls(
            resource_id=resource.resource_id or "",
            title=resource.title,
            kind=kind or default_activity_kind_for_resource(resource.kind),
            duration_minutes=duration_minutes or candidate.effort_minutes,
            priority_score=priority_score,
            reason=reason,
            run_id=run_id,
        )
