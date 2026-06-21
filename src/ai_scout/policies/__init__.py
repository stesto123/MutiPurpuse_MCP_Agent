from ai_scout.policies.deduplication import (
    DeduplicationResult,
    DuplicateDecision,
    build_seen_identity_keys,
    deduplicate_candidates,
    deduplicate_candidates_with_report,
    filter_seen_candidates,
    filter_seen_resources,
    identity_keys_for_resource,
    normalize_title,
    normalize_url,
)
from ai_scout.policies.scoring import (
    ScoreBreakdown,
    ScoredCandidate,
    ScoreWeights,
    rank_candidates,
    score_candidate,
)

__all__ = [
    "DeduplicationResult",
    "DuplicateDecision",
    "ScoreBreakdown",
    "ScoreWeights",
    "ScoredCandidate",
    "build_seen_identity_keys",
    "deduplicate_candidates",
    "deduplicate_candidates_with_report",
    "filter_seen_candidates",
    "filter_seen_resources",
    "identity_keys_for_resource",
    "normalize_title",
    "normalize_url",
    "rank_candidates",
    "score_candidate",
]
