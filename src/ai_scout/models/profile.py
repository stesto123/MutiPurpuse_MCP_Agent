from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ai_scout.models.resources import ResourceKind


def _clean_terms(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    cleaned_values: list[str] = []
    for value in values:
        cleaned = " ".join(value.casefold().strip().split())
        if cleaned and cleaned not in seen:
            cleaned_values.append(cleaned)
            seen.add(cleaned)
    return tuple(cleaned_values)


@dataclass(frozen=True)
class LearningProfile:
    """User-independent preferences used for local ranking decisions."""

    interests: tuple[str, ...] = ()
    preferred_resource_kinds: tuple[ResourceKind, ...] = ()
    blocked_terms: tuple[str, ...] = ()
    preferred_effort_minutes: int = 45
    max_effort_minutes: int = 120
    freshness_window_days: int = 60

    def __post_init__(self) -> None:
        if self.preferred_effort_minutes <= 0:
            raise ValueError("preferred_effort_minutes must be positive")
        if self.max_effort_minutes <= 0:
            raise ValueError("max_effort_minutes must be positive")
        if self.freshness_window_days <= 0:
            raise ValueError("freshness_window_days must be positive")

        kinds = tuple(
            kind if isinstance(kind, ResourceKind) else ResourceKind(str(kind))
            for kind in self.preferred_resource_kinds
        )
        object.__setattr__(self, "interests", _clean_terms(self.interests))
        object.__setattr__(self, "blocked_terms", _clean_terms(self.blocked_terms))
        object.__setattr__(self, "preferred_resource_kinds", kinds)
