"""Learning plan specialist agent."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .types import AgentResult, JsonDict, get_resource, log_entry, stable_id


class PlanningAgent:
    """Turn ranked resources into learning activities."""

    stage = "planning"

    def run(
        self,
        ranked_items: Sequence[Mapping[str, Any]],
        policy: Mapping[str, Any] | None = None,
        *,
        run_id: str = "manual-run",
    ) -> AgentResult:
        policy = policy or {}
        max_activities = int(policy.get("max_activities", 3))
        default_duration = int(policy.get("default_duration_minutes", 45))
        result = AgentResult()

        for item in list(ranked_items)[:max_activities]:
            resource = get_resource(item)
            duration = item.get("estimated_minutes") or default_duration
            try:
                duration_minutes = int(duration)
            except (TypeError, ValueError):
                duration_minutes = default_duration

            activity: JsonDict = {
                "id": stable_id("activity", run_id, resource["id"]),
                "run_id": run_id,
                "resource_id": resource["id"],
                "title": f"Review: {resource.get('title', 'Untitled resource')}",
                "description": str(item.get("content_summary") or resource.get("summary") or ""),
                "duration_minutes": max(15, duration_minutes),
                "priority": int(item.get("rank") or len(result.items) + 1),
                "score": item.get("score"),
                "status": "planned",
                "metadata": {
                    "source": resource.get("source"),
                    "url": resource.get("url", ""),
                },
            }
            result.items.append(activity)

        result.log.append(
            log_entry(
                self.stage,
                "learning_plan_built",
                "Planning produced learning activities",
                count=len(result.items),
            )
        )
        return result
