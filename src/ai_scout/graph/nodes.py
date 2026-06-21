"""LangGraph-compatible node functions for the AI Scout run lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ai_scout.agents import (
    AgentResult,
    AuditAgent,
    CalendarExecutionAgent,
    DeduplicationAgent,
    DiscoveryAgent,
    InspectionAgent,
    MCPGateway,
    MemoryReportHandoffAgent,
    MemoryStore,
    PlanningAgent,
    RankingAgent,
    ReportSink,
    RetryPolicy,
)
from ai_scout.agents.types import error_entry, log_entry

from .state import ScoutState, ensure_state


@dataclass
class GraphDependencies:
    mcp: MCPGateway
    memory_store: MemoryStore | None = None
    report_sink: ReportSink | None = None
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)


NodeFn = Callable[[ScoutState, GraphDependencies], ScoutState]


def load_profile_and_policy_node(state: ScoutState, deps: GraphDependencies) -> ScoutState:
    del deps
    state = ensure_state(state)
    config = state["config"]
    if not state["profile"]:
        state["profile"] = dict(config.get("profile") or {})
    if not state["policy"]:
        state["policy"] = dict(config.get("policy") or {})
    _extend(
        state,
        log=[
            log_entry(
                "load_profile_policy",
                "loaded",
                "Profile and policy loaded from provided state/config",
                profile_keys=sorted(state["profile"].keys()),
                policy_keys=sorted(state["policy"].keys()),
            )
        ],
    )
    return state


def load_memory_node(state: ScoutState, deps: GraphDependencies) -> ScoutState:
    state = ensure_state(state)
    if deps.memory_store is None:
        state["memory"] = {"seen_resource_ids": [], "seen_urls": [], "seen_fingerprints": []}
        _extend(state, log=[log_entry("load_memory", "skipped", "No memory store provided")])
        return state

    try:
        snapshot = deps.memory_store.load_snapshot(state["run_id"])
    except Exception as exc:  # pragma: no cover - memory implementation-specific.
        state["memory"] = {"seen_resource_ids": [], "seen_urls": [], "seen_fingerprints": []}
        _extend(
            state,
            errors=[
                error_entry(
                    "load_memory",
                    "Memory snapshot load failed",
                    code="memory_load_failed",
                    error_type=exc.__class__.__name__,
                    error=str(exc),
                )
            ],
        )
    else:
        state["memory"] = dict(snapshot)
        _extend(
            state,
            log=[
                log_entry(
                    "load_memory",
                    "loaded",
                    "Memory snapshot loaded",
                    seen_ids=len(state["memory"].get("seen_resource_ids", [])),
                    seen_urls=len(state["memory"].get("seen_urls", [])),
                )
            ],
        )
    return state


def discover_resources_node(state: ScoutState, deps: GraphDependencies) -> ScoutState:
    state = ensure_state(state)
    config = state["config"]
    request = {
        "run_id": state["run_id"],
        "profile": state["profile"],
        "tools": config.get("discovery_tools") or config.get("source_tools"),
        "max_results": state["policy"].get("max_discovery_results", config.get("max_results", 10)),
    }
    result = DiscoveryAgent(deps.mcp, deps.retry_policy).run(request)
    state["candidates"] = result.items
    _extend(state, log=result.log, errors=result.errors, side_effects=result.side_effects)
    return state


def inspect_resources_node(state: ScoutState, deps: GraphDependencies) -> ScoutState:
    state = ensure_state(state)
    request = {
        "tool_name": state["config"].get("inspection_tool", "content.inspect"),
        "requested_fields": ["summary", "signals", "estimated_minutes"],
    }
    result = InspectionAgent(deps.mcp, deps.retry_policy).run(state["candidates"], request)
    state["inspections"] = result.items
    _extend(state, log=result.log, errors=result.errors, side_effects=result.side_effects)
    return state


def deduplicate_resources_node(state: ScoutState, deps: GraphDependencies) -> ScoutState:
    del deps
    state = ensure_state(state)
    result = DeduplicationAgent().run(state["inspections"], state["memory"])
    state["deduplicated"] = result.items
    _extend(state, log=result.log, errors=result.errors, side_effects=result.side_effects)
    return state


def rank_resources_node(state: ScoutState, deps: GraphDependencies) -> ScoutState:
    del deps
    state = ensure_state(state)
    result = RankingAgent().run(state["deduplicated"], state["policy"])
    state["ranked"] = result.items
    _extend(state, log=result.log, errors=result.errors, side_effects=result.side_effects)
    return state


def build_learning_plan_node(state: ScoutState, deps: GraphDependencies) -> ScoutState:
    del deps
    state = ensure_state(state)
    result = PlanningAgent().run(state["ranked"], state["policy"], run_id=state["run_id"])
    state["learning_plan"] = result.items
    _extend(state, log=result.log, errors=result.errors, side_effects=result.side_effects)
    return state


def read_calendar_availability_node(state: ScoutState, deps: GraphDependencies) -> ScoutState:
    state = ensure_state(state)
    config = state["config"]
    request = {
        "run_id": state["run_id"],
        "tool_name": config.get("availability_tool", "calendar.read_availability"),
        "arguments": config.get("availability_query", {}),
    }
    result = CalendarExecutionAgent(deps.mcp, deps.retry_policy).read_availability(request)
    state["availability"] = result.items
    _extend(state, log=result.log, errors=result.errors, side_effects=result.side_effects)
    return state


def write_calendar_events_node(state: ScoutState, deps: GraphDependencies) -> ScoutState:
    state = ensure_state(state)
    config = state["config"]
    policy = state["policy"]
    if not _calendar_writes_allowed(policy, str(state.get("mode") or config.get("mode") or "")):
        result = _calendar_write_dry_run(state["learning_plan"])
        state["calendar_events"] = result.items
        _extend(state, log=result.log, errors=result.errors, side_effects=result.side_effects)
        return state

    request = {
        "run_id": state["run_id"],
        "tool_name": config.get("create_event_tool", "calendar.create_event"),
    }
    result = CalendarExecutionAgent(deps.mcp, deps.retry_policy).write_events(
        state["learning_plan"], state["availability"], request
    )
    state["calendar_events"] = result.items
    _extend(state, log=result.log, errors=result.errors, side_effects=result.side_effects)
    return state


def write_memory_and_reports_node(state: ScoutState, deps: GraphDependencies) -> ScoutState:
    state = ensure_state(state)
    result = MemoryReportHandoffAgent(
        memory_store=deps.memory_store,
        report_sink=deps.report_sink,
    ).run(
        run_id=state["run_id"],
        ranked_items=state["ranked"],
        learning_plan=state["learning_plan"],
        calendar_events=state["calendar_events"],
        errors=state["errors"],
    )
    state["handoff"] = result.items
    _extend(state, log=result.log, errors=result.errors, side_effects=result.side_effects)
    return state


def audit_run_node(state: ScoutState, deps: GraphDependencies) -> ScoutState:
    del deps
    state = ensure_state(state)
    result = AuditAgent().run(
        deduplicated_items=state["deduplicated"],
        calendar_events=state["calendar_events"],
        side_effects=state["side_effects"],
        errors=state["errors"],
        log=state["log"],
    )
    state["audit"] = result.items[0] if result.items else {}
    _extend(state, log=result.log, errors=result.errors, side_effects=result.side_effects)
    return state


NODE_SEQUENCE: list[tuple[str, NodeFn]] = [
    ("load_profile_and_policy", load_profile_and_policy_node),
    ("load_memory", load_memory_node),
    ("discover_resources", discover_resources_node),
    ("inspect_resources", inspect_resources_node),
    ("deduplicate_resources", deduplicate_resources_node),
    ("rank_resources", rank_resources_node),
    ("build_learning_plan", build_learning_plan_node),
    ("read_calendar_availability", read_calendar_availability_node),
    ("write_calendar_events", write_calendar_events_node),
    ("write_memory_and_reports", write_memory_and_reports_node),
    ("audit_run", audit_run_node),
]


def _extend(
    state: ScoutState,
    *,
    log: list[dict[str, Any]] | None = None,
    errors: list[dict[str, Any]] | None = None,
    side_effects: list[dict[str, Any]] | None = None,
) -> None:
    state.setdefault("log", []).extend(log or [])
    state.setdefault("errors", []).extend(errors or [])
    state.setdefault("side_effects", []).extend(side_effects or [])


def _calendar_writes_allowed(policy: dict[str, Any], mode: str) -> bool:
    if not mode:
        return True
    permissions = policy.get("permissions")
    if isinstance(permissions, dict):
        mode_permissions = permissions.get(mode)
        if isinstance(mode_permissions, dict):
            return bool(mode_permissions.get("calendar_writes_via_mcp", mode == "autonomous"))
    return mode == "autonomous"


def _calendar_write_dry_run(learning_plan: list[dict[str, Any]]) -> AgentResult:
    result = AgentResult()
    for activity in learning_plan:
        result.items.append(
            {
                "activity_id": activity.get("id"),
                "resource_id": activity.get("resource_id"),
                "status": "dry_run_skipped",
                "event_id": "",
                "idempotency_key": activity.get("id"),
                "title": activity.get("title"),
            }
        )
    result.log.append(
        log_entry(
            "calendar_execution",
            "calendar_writes_skipped",
            "Calendar writes skipped by current mode/policy",
            count=len(result.items),
        )
    )
    return result
