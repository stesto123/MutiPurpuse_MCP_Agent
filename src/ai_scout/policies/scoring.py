from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

from ai_scout.models import LearningProfile, ResourceCandidate
from ai_scout.policies.deduplication import identity_keys_for_resource

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.\-]*")


@dataclass(frozen=True)
class ScoreWeights:
    interest: float = 0.25
    source_quality: float = 0.15
    novelty: float = 0.20
    effort: float = 0.15
    local_applicability: float = 0.15
    freshness: float = 0.10

    def __post_init__(self) -> None:
        if any(value < 0.0 for value in self.as_tuple()):
            raise ValueError("score weights cannot be negative")
        if sum(self.as_tuple()) <= 0.0:
            raise ValueError("at least one score weight must be positive")

    def as_tuple(self) -> tuple[float, float, float, float, float, float]:
        return (
            self.interest,
            self.source_quality,
            self.novelty,
            self.effort,
            self.local_applicability,
            self.freshness,
        )


@dataclass(frozen=True)
class ScoreBreakdown:
    interest: float
    source_quality: float
    novelty: float
    effort: float
    local_applicability: float
    freshness: float
    final_score: float
    reasons: tuple[str, ...] = ()

    @property
    def factor_scores(self) -> dict[str, float]:
        return {
            "interest": self.interest,
            "source_quality": self.source_quality,
            "novelty": self.novelty,
            "effort": self.effort,
            "local_applicability": self.local_applicability,
            "freshness": self.freshness,
        }


@dataclass(frozen=True)
class ScoredCandidate:
    candidate: ResourceCandidate
    score: ScoreBreakdown


def score_candidate(
    candidate: ResourceCandidate,
    profile: LearningProfile,
    *,
    now: datetime | None = None,
    weights: ScoreWeights = ScoreWeights(),
    seen_resource_ids: tuple[str, ...] = (),
    seen_identity_keys: tuple[str, ...] = (),
) -> ScoreBreakdown:
    """Score a candidate deterministically from model fields and policy inputs."""

    reference_time = now or candidate.discovered_at
    interest_score, matched_interests = _interest_score(candidate, profile)
    novelty_score = _novelty_score(candidate, seen_resource_ids, seen_identity_keys)
    effort_score = _effort_score(candidate.effort_minutes, profile)
    freshness_score = _freshness_score(candidate, profile, reference_time)

    factor_values = (
        interest_score,
        candidate.source_quality,
        novelty_score,
        effort_score,
        candidate.local_applicability,
        freshness_score,
    )
    weight_values = weights.as_tuple()
    weight_total = sum(weight_values)
    final_score = sum(
        factor * weight for factor, weight in zip(factor_values, weight_values)
    ) / weight_total

    reasons = _score_reasons(
        candidate=candidate,
        matched_interests=matched_interests,
        novelty_score=novelty_score,
        effort_score=effort_score,
        freshness_score=freshness_score,
    )
    return ScoreBreakdown(
        interest=round(interest_score, 6),
        source_quality=round(candidate.source_quality, 6),
        novelty=round(novelty_score, 6),
        effort=round(effort_score, 6),
        local_applicability=round(candidate.local_applicability, 6),
        freshness=round(freshness_score, 6),
        final_score=round(final_score, 6),
        reasons=reasons,
    )


def rank_candidates(
    candidates: tuple[ResourceCandidate, ...],
    profile: LearningProfile,
    *,
    now: datetime | None = None,
    weights: ScoreWeights = ScoreWeights(),
    seen_resource_ids: tuple[str, ...] = (),
    seen_identity_keys: tuple[str, ...] = (),
) -> tuple[ScoredCandidate, ...]:
    scored = tuple(
        ScoredCandidate(
            candidate=candidate,
            score=score_candidate(
                candidate,
                profile,
                now=now,
                weights=weights,
                seen_resource_ids=seen_resource_ids,
                seen_identity_keys=seen_identity_keys,
            ),
        )
        for candidate in candidates
    )
    return tuple(
        sorted(
            scored,
            key=lambda item: (
                -item.score.final_score,
                item.candidate.effort_minutes,
                item.candidate.resource.title.casefold(),
                item.candidate.resource.resource_id,
            ),
        )
    )


def _interest_score(
    candidate: ResourceCandidate, profile: LearningProfile
) -> tuple[float, tuple[str, ...]]:
    resource = candidate.resource
    searchable_text = " ".join(
        value
        for value in (
            resource.title,
            resource.summary or "",
            " ".join(resource.topics),
            " ".join(candidate.tags),
            resource.kind.value.replace("_", " "),
        )
        if value
    ).casefold()
    searchable_tokens = set(_tokens(searchable_text))

    if any(blocked in searchable_text for blocked in profile.blocked_terms):
        return 0.0, ()

    matched: list[str] = []
    for interest in profile.interests:
        interest_tokens = tuple(_tokens(interest))
        if interest in searchable_text or (
            interest_tokens and set(interest_tokens).issubset(searchable_tokens)
        ):
            matched.append(interest)

    if profile.interests:
        interest_match_score = len(matched) / len(profile.interests)
    else:
        interest_match_score = 0.5

    if profile.preferred_resource_kinds:
        kind_score = 1.0 if resource.kind in profile.preferred_resource_kinds else 0.25
        combined = 0.8 * interest_match_score + 0.2 * kind_score
    else:
        combined = interest_match_score
    return _clamp(combined), tuple(matched)


def _novelty_score(
    candidate: ResourceCandidate,
    seen_resource_ids: Iterable[str],
    seen_identity_keys: Iterable[str],
) -> float:
    seen_ids = {resource_id.strip() for resource_id in seen_resource_ids if resource_id.strip()}
    if candidate.resource.resource_id in seen_ids:
        return 0.0

    seen_keys = {key.strip() for key in seen_identity_keys if key.strip()}
    if seen_keys.intersection(identity_keys_for_resource(candidate.resource)):
        return 0.0
    return candidate.novelty_hint if candidate.novelty_hint is not None else 1.0


def _effort_score(effort_minutes: int, profile: LearningProfile) -> float:
    preferred = profile.preferred_effort_minutes
    maximum = profile.max_effort_minutes
    if effort_minutes <= preferred:
        return 1.0
    if effort_minutes > maximum:
        return 0.0
    if maximum == preferred:
        return 0.0
    overshoot = (effort_minutes - preferred) / (maximum - preferred)
    return _clamp(1.0 - (0.8 * overshoot))


def _freshness_score(
    candidate: ResourceCandidate, profile: LearningProfile, now: datetime
) -> float:
    published_at = candidate.resource.published_at
    if published_at is None:
        return 0.5

    age_days = max(0.0, _age_days(published_at, now))
    return _clamp(1.0 / (1.0 + (age_days / profile.freshness_window_days)))


def _age_days(start: datetime, end: datetime) -> float:
    if start.tzinfo is not None and end.tzinfo is not None:
        delta = end.astimezone(timezone.utc) - start.astimezone(timezone.utc)
    else:
        delta = end.replace(tzinfo=None) - start.replace(tzinfo=None)
    return delta.total_seconds() / 86400


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(_TOKEN_RE.findall(value.casefold()))


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def _score_reasons(
    *,
    candidate: ResourceCandidate,
    matched_interests: tuple[str, ...],
    novelty_score: float,
    effort_score: float,
    freshness_score: float,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if matched_interests:
        reasons.append("matched interests: " + ", ".join(matched_interests))
    if novelty_score == 0.0:
        reasons.append("previously seen")
    if effort_score == 0.0:
        reasons.append("outside effort budget")
    if candidate.local_applicability >= 0.75:
        reasons.append("high local applicability")
    if freshness_score >= 0.85:
        reasons.append("fresh resource")
    return tuple(reasons)
