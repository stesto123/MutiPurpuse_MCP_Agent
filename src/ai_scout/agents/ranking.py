"""Ranking specialist agent."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .types import AgentResult, JsonDict, get_resource, log_entry


class RankingAgent:
    """Score non-duplicate inspected resources using explicit weighted signals."""

    stage = "ranking"

    default_weights = {
        "relevance": 0.45,
        "novelty": 0.25,
        "source_trust": 0.20,
        "effort_fit": 0.10,
    }

    def run(
        self,
        items: Sequence[Mapping[str, Any]],
        policy: Mapping[str, Any] | None = None,
    ) -> AgentResult:
        policy = policy or {}
        weights = dict(self.default_weights)
        weights.update(dict(policy.get("ranking_weights") or {}))
        min_score = float(policy.get("min_score", 0.0))
        result = AgentResult()

        for item in items:
            if item.get("is_duplicate"):
                continue
            resource = get_resource(item)
            signals = dict(item.get("signals") or {})
            components = _score_components(signals, item)
            score = round(sum(components[name] * float(weights.get(name, 0)) for name in weights), 4)
            if score < min_score:
                continue

            ranked: JsonDict = dict(item)
            ranked["resource"] = resource
            ranked["resource_id"] = resource["id"]
            ranked["score"] = score
            ranked["rank_components"] = components
            ranked["rank_rationale"] = {
                "weights": weights,
                "summary": (
                    "Score combines relevance, novelty, source trust, and effort fit "
                    "from inspected signals."
                ),
            }
            result.items.append(ranked)

        result.items.sort(
            key=lambda item: (
                -float(item.get("score", 0.0)),
                str(get_resource(item).get("title") or ""),
            )
        )
        for index, item in enumerate(result.items, start=1):
            item["rank"] = index

        result.log.append(
            log_entry(
                self.stage,
                "resources_ranked",
                "Ranking produced ordered resources",
                count=len(result.items),
            )
        )
        return result


def _bounded(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, min(1.0, number))


def _score_components(signals: Mapping[str, Any], item: Mapping[str, Any]) -> JsonDict:
    estimated = item.get("estimated_minutes") or signals.get("estimated_minutes")
    try:
        estimated_minutes = float(estimated if estimated is not None else 45.0)
    except (TypeError, ValueError):
        estimated_minutes = 45.0

    effort_fit = 1.0 if estimated_minutes <= 45 else max(0.1, 1 - ((estimated_minutes - 45) / 120))
    return {
        "relevance": _bounded(signals.get("relevance"), 0.5),
        "novelty": _bounded(signals.get("novelty"), 0.7),
        "source_trust": _bounded(signals.get("source_trust"), 0.6),
        "effort_fit": round(max(0.0, min(1.0, effort_fit)), 4),
    }
