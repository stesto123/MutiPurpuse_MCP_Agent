"""Graph construction with an optional LangGraph backend and a clean fallback."""

from __future__ import annotations

from typing import Any

from ai_scout.config import AppConfig
from ai_scout.mcp import (
    LocalDryRunMCPGateway,
    MCPToolRegistry,
    StdioMCPClient,
    SyncMCPToolGateway,
)

from .nodes import NODE_SEQUENCE, GraphDependencies
from .state import ScoutState, ensure_state, new_state


class SequentialScoutGraph:
    """Fallback runner exposing the same basic ``invoke`` API as LangGraph."""

    def __init__(self, deps: GraphDependencies) -> None:
        self.deps = deps

    def invoke(self, input_state: ScoutState | dict[str, Any]) -> ScoutState:
        state = ensure_state(input_state)
        for name, node in NODE_SEQUENCE:
            state = node(state, self.deps)
            state["last_node"] = name
        return state


def build_scout_graph(
    deps: GraphDependencies,
    *,
    prefer_langgraph: bool = True,
) -> Any:
    """Build a LangGraph app when available, otherwise return the fallback runner."""

    if prefer_langgraph:
        graph = _build_langgraph(deps)
        if graph is not None:
            return graph
    return SequentialScoutGraph(deps)


def build_graph(deps: GraphDependencies, *, prefer_langgraph: bool = True) -> Any:
    """Compatibility alias for callers that expect a generic graph builder."""

    return build_scout_graph(deps, prefer_langgraph=prefer_langgraph)


def run_scout(
    initial_state: ScoutState | dict[str, Any],
    deps: GraphDependencies,
    *,
    prefer_langgraph: bool = True,
) -> ScoutState:
    graph = build_scout_graph(deps, prefer_langgraph=prefer_langgraph)
    return graph.invoke(initial_state)


def run_ai_scout(
    *,
    config: AppConfig,
    run_id: str,
    memory: Any | None = None,
    report_sink: Any | None = None,
    mcp_gateway: Any | None = None,
    prefer_langgraph: bool = True,
) -> ScoutState:
    """Run one AI Scout cycle from the CLI/runtime boundary.

    The default gateway is a deterministic local MCP-shaped gateway. Real MCP
    servers can be injected by replacing ``mcp_gateway`` with an implementation
    of the specialist-agent ``call_tool`` protocol.
    """

    gateway = mcp_gateway or _default_gateway(config)
    deps = GraphDependencies(
        mcp=gateway,
        memory_store=memory,
        report_sink=report_sink,
    )
    profile = _normalize_profile(config.profile)
    policy = _normalize_policy(config.policy, profile=profile)
    state = new_state(
        run_id=run_id,
        config={
            "profile": profile,
            "policy": policy,
            "sources": dict(config.sources),
            "mcp": dict(config.mcp),
            "mode": config.mode,
            "source_tools": _source_tools_from_sources(config.sources),
        },
        profile=profile,
        policy=policy,
    )
    state["mode"] = config.mode
    return run_scout(state, deps, prefer_langgraph=prefer_langgraph)


def _normalize_profile(profile: Any) -> dict[str, Any]:
    normalized = dict(profile or {})
    topics = list(normalized.get("topics") or normalized.get("interests") or [])
    if not topics:
        learning_goals = normalized.get("learning_goals")
        if isinstance(learning_goals, list):
            for goal in learning_goals:
                if isinstance(goal, dict):
                    label = goal.get("label") or goal.get("id")
                    if label:
                        topics.append(str(label))
    normalized["topics"] = topics
    availability = normalized.get("availability")
    if isinstance(availability, dict) and "default_session_minutes" in availability:
        normalized.setdefault("default_session_minutes", availability["default_session_minutes"])
    return normalized


def _normalize_policy(policy: Any, *, profile: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(policy or {})
    scoring = normalized.get("scoring")
    if isinstance(scoring, dict):
        thresholds = scoring.get("thresholds")
        if isinstance(thresholds, dict):
            normalized.setdefault("min_score", thresholds.get("minimum_score_to_report", 0.0))
        weights = scoring.get("weights")
        if isinstance(weights, dict):
            normalized.setdefault(
                "ranking_weights",
                {
                    "relevance": weights.get("relevance", 0.45),
                    "novelty": weights.get("novelty", 0.25),
                    "source_trust": weights.get("credibility", weights.get("source_trust", 0.2)),
                    "effort_fit": weights.get("time_fit", weights.get("actionability", 0.1)),
                },
            )
    autonomy = normalized.get("autonomy")
    if isinstance(autonomy, dict):
        normalized.setdefault("max_activities", autonomy.get("max_calendar_writes_per_run", 3))
    if "default_duration_minutes" not in normalized and profile.get("default_session_minutes"):
        normalized["default_duration_minutes"] = profile["default_session_minutes"]
    return normalized


def _default_gateway(config: AppConfig) -> Any:
    if _has_enabled_mcp_server(config.mcp):
        registry = MCPToolRegistry.from_mapping(config.mcp)
        return SyncMCPToolGateway(StdioMCPClient(registry), registry)
    return LocalDryRunMCPGateway(mode=config.mode)


def _has_enabled_mcp_server(mcp_config: Any) -> bool:
    if not isinstance(mcp_config, dict):
        return False
    servers = mcp_config.get("servers")
    if isinstance(servers, dict):
        return any(bool(server.get("enabled", True)) for server in servers.values() if isinstance(server, dict))
    if isinstance(servers, list):
        return any(bool(server.get("enabled", True)) for server in servers if isinstance(server, dict))
    return False


def _source_tools_from_sources(sources: Any) -> list[dict[str, Any]]:
    if not isinstance(sources, dict):
        return []
    source_entries = sources.get("sources")
    if not isinstance(source_entries, list):
        return []
    tools: list[dict[str, Any]] = []
    for source in source_entries:
        if not isinstance(source, dict) or not source.get("enabled"):
            continue
        server = source.get("mcp_server_id")
        tool = source.get("mcp_tool_name")
        if not server or not tool:
            continue
        arguments = {
            key: value
            for key, value in source.items()
            if key
            not in {
                "enabled",
                "mcp_server_id",
                "mcp_tool_name",
                "label",
                "tags",
            }
        }
        tools.append(
            {
                "tool_name": f"{server}.{tool}",
                "source": source.get("id") or f"{server}.{tool}",
                "arguments": arguments,
            }
        )
    return tools


def _build_langgraph(deps: GraphDependencies) -> Any | None:
    try:
        from langgraph.graph import END, StateGraph
    except ImportError:
        return None

    builder = StateGraph(ScoutState)
    first_node = NODE_SEQUENCE[0][0]

    for name, node in NODE_SEQUENCE:
        builder.add_node(name, _langgraph_node(name, node, deps))

    builder.set_entry_point(first_node)
    for (name, _node), (next_name, _next_node) in zip(NODE_SEQUENCE, NODE_SEQUENCE[1:]):
        builder.add_edge(name, next_name)
    builder.add_edge(NODE_SEQUENCE[-1][0], END)
    return builder.compile()


def _langgraph_node(name: str, node: Any, deps: GraphDependencies) -> Any:
    def wrapped(state: ScoutState | dict[str, Any]) -> ScoutState:
        next_state = node(ensure_state(state), deps)
        next_state["last_node"] = name
        return next_state

    return wrapped
