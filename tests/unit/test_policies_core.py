from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ai_scout.models import LearningProfile, Resource, ResourceCandidate, ResourceKind  # noqa: E402
from ai_scout.policies import (  # noqa: E402
    build_seen_identity_keys,
    deduplicate_candidates,
    deduplicate_candidates_with_report,
    filter_seen_candidates,
    normalize_title,
    normalize_url,
    rank_candidates,
    score_candidate,
)

NOW = datetime(2026, 6, 21, tzinfo=timezone.utc)


def _candidate(
    title: str,
    *,
    url: str | None = None,
    kind: ResourceKind = ResourceKind.ARTICLE,
    topics: tuple[str, ...] = (),
    published_days_ago: int | None = 1,
    source_quality: float = 0.7,
    effort_minutes: int = 30,
    local_applicability: float = 0.7,
    novelty_hint: float | None = None,
) -> ResourceCandidate:
    published_at = (
        None
        if published_days_ago is None
        else NOW - timedelta(days=published_days_ago)
    )
    return ResourceCandidate(
        resource=Resource(
            title=title,
            kind=kind,
            url=url,
            topics=topics,
            published_at=published_at,
        ),
        discovered_at=NOW,
        source_quality=source_quality,
        effort_minutes=effort_minutes,
        local_applicability=local_applicability,
        novelty_hint=novelty_hint,
    )


class PoliciesCoreTests(TestCase):
    def test_url_and_title_normalization_are_tracking_safe(self) -> None:
        self.assertEqual(
            normalize_url("HTTPS://github.com/OpenAI/Example.git?utm_source=newsletter#readme"),
            "https://github.com/openai/example",
        )
        self.assertEqual(
            normalize_url("https://example.com/a/?b=2&utm_medium=x&a=1"),
            "https://example.com/a?a=1&b=2",
        )
        self.assertEqual(
            normalize_title("  Practical MCP: Agents & Tools! "),
            "practical mcp agents and tools",
        )

    def test_deduplicate_candidates_uses_url_then_title_identity(self) -> None:
        first = _candidate(
            "LangGraph Scout",
            url="https://example.com/scout?utm_source=feed",
            kind=ResourceKind.GITHUB_REPO,
        )
        duplicate_url = _candidate(
            "LangGraph Scout Mirror",
            url="https://example.com/scout",
            kind=ResourceKind.GITHUB_REPO,
        )
        duplicate_title = _candidate(
            "  LangGraph Scout!!! ",
            url="https://mirror.example/scout",
            kind=ResourceKind.GITHUB_REPO,
        )
        unique = _candidate("Different Resource", url="https://example.com/different")

        result = deduplicate_candidates_with_report(
            (first, duplicate_url, duplicate_title, unique)
        )

        self.assertEqual(
            deduplicate_candidates((first, duplicate_url, duplicate_title, unique)),
            (first, unique),
        )
        self.assertEqual(len(result.duplicates), 2)
        self.assertEqual(result.duplicates[0].duplicate_key, "url:https://example.com/scout")
        self.assertEqual(result.duplicates[1].duplicate_key, "title:langgraph scout")

    def test_filter_seen_candidates_accepts_seen_urls_titles_and_ids(self) -> None:
        seen_by_url = _candidate("Seen URL", url="https://example.com/seen?utm_campaign=x")
        seen_by_title = _candidate("Seen Title", url="https://example.com/old")
        unseen = _candidate("Unseen", url="https://example.com/new")

        filtered = filter_seen_candidates(
            (seen_by_url, seen_by_title, unseen),
            seen_urls=("https://example.com/seen",),
            seen_titles=("seen title",),
        )

        self.assertEqual(filtered, (unseen,))

    def test_score_candidate_prefers_relevant_fresh_applicable_resources(self) -> None:
        profile = LearningProfile(
            interests=("mcp agents", "langgraph"),
            preferred_resource_kinds=(ResourceKind.GITHUB_REPO,),
            preferred_effort_minutes=45,
            max_effort_minutes=90,
        )
        relevant = _candidate(
            "LangGraph MCP Agent",
            url="https://github.com/example/agent",
            kind=ResourceKind.GITHUB_REPO,
            topics=("mcp agents", "langgraph"),
            published_days_ago=2,
            source_quality=0.9,
            effort_minutes=45,
            local_applicability=0.95,
        )
        stale_irrelevant = _candidate(
            "Old prompt collection",
            url="https://example.com/prompts",
            kind=ResourceKind.ARTICLE,
            topics=("prompting",),
            published_days_ago=300,
            source_quality=0.5,
            effort_minutes=100,
            local_applicability=0.3,
        )

        relevant_score = score_candidate(relevant, profile, now=NOW)
        stale_score = score_candidate(stale_irrelevant, profile, now=NOW)
        ranked = rank_candidates((stale_irrelevant, relevant), profile, now=NOW)

        self.assertGreater(relevant_score.final_score, stale_score.final_score)
        self.assertEqual(relevant_score.interest, 1.0)
        self.assertIn("matched interests: mcp agents, langgraph", relevant_score.reasons)
        self.assertIs(ranked[0].candidate, relevant)

    def test_seen_identity_lowers_novelty_to_zero(self) -> None:
        candidate = _candidate(
            "Already Learned",
            url="https://example.com/already",
            novelty_hint=1.0,
        )
        profile = LearningProfile(interests=("learned",))
        seen_keys = build_seen_identity_keys(urls=("https://example.com/already?utm_source=x",))

        score = score_candidate(candidate, profile, now=NOW, seen_identity_keys=tuple(seen_keys))

        self.assertEqual(score.novelty, 0.0)
        self.assertIn("previously seen", score.reasons)
