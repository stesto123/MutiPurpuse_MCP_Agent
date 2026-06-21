"""Shared state shape for AI Scout graph execution."""

from __future__ import annotations

from typing import Any, TypedDict


class ScoutState(TypedDict, total=False):
    run_id: str
    mode: str
    config: dict[str, Any]
    profile: dict[str, Any]
    policy: dict[str, Any]
    memory: dict[str, Any]
    candidates: list[dict[str, Any]]
    inspections: list[dict[str, Any]]
    deduplicated: list[dict[str, Any]]
    ranked: list[dict[str, Any]]
    learning_plan: list[dict[str, Any]]
    availability: list[dict[str, Any]]
    calendar_events: list[dict[str, Any]]
    handoff: list[dict[str, Any]]
    audit: dict[str, Any]
    errors: list[dict[str, Any]]
    log: list[dict[str, Any]]
    side_effects: list[dict[str, Any]]
    last_node: str


def new_state(
    *,
    run_id: str = "manual-run",
    config: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
) -> ScoutState:
    return {
        "run_id": run_id,
        "config": dict(config or {}),
        "profile": dict(profile or {}),
        "policy": dict(policy or {}),
        "memory": {},
        "candidates": [],
        "inspections": [],
        "deduplicated": [],
        "ranked": [],
        "learning_plan": [],
        "availability": [],
        "calendar_events": [],
        "handoff": [],
        "audit": {},
        "errors": [],
        "log": [],
        "side_effects": [],
    }


def ensure_state(state: ScoutState | dict[str, Any]) -> ScoutState:
    base: dict[str, Any] = dict(new_state())
    base.update(dict(state))
    for key in (
        "candidates",
        "inspections",
        "deduplicated",
        "ranked",
        "learning_plan",
        "availability",
        "calendar_events",
        "handoff",
        "errors",
        "log",
        "side_effects",
    ):
        value = base.get(key) or []
        base[key] = list(value) if isinstance(value, list) else []
    for key in ("config", "profile", "policy", "memory", "audit"):
        value = base.get(key) or {}
        base[key] = dict(value) if isinstance(value, dict) else {}
    base["run_id"] = str(base.get("run_id") or "manual-run")
    return base  # type: ignore[return-value]
