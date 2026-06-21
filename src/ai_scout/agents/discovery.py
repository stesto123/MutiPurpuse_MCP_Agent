"""Discovery specialist agent."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .base import call_tool_with_retries
from .types import (
    AgentResult,
    JsonDict,
    MCPGateway,
    RetryPolicy,
    coerce_resource,
    error_entry,
    log_entry,
)


class DiscoveryAgent:
    """Find candidate resources through MCP-backed source tools."""

    stage = "discovery"

    def __init__(
        self,
        gateway: MCPGateway,
        retry_policy: RetryPolicy | None = None,
        *,
        default_tool: str = "sources.discover",
    ) -> None:
        self.gateway = gateway
        self.retry_policy = retry_policy or RetryPolicy()
        self.default_tool = default_tool

    def run(self, request: Mapping[str, Any]) -> AgentResult:
        tools = _tool_specs(request.get("tools"), self.default_tool)
        result = AgentResult()

        for spec in tools:
            tool_name = str(spec.get("tool_name") or self.default_tool)
            arguments = dict(spec.get("arguments") or {})
            profile = request.get("profile")
            if isinstance(profile, Mapping) and "topics" in profile:
                arguments.setdefault("topics", list(profile.get("topics") or []))
            if "max_results" in request:
                arguments.setdefault("max_results", request["max_results"])

            response, log, errors = call_tool_with_retries(
                self.gateway,
                tool_name=tool_name,
                arguments=arguments,
                stage=self.stage,
                retry_policy=self.retry_policy,
            )
            result.log.extend(log)
            result.errors.extend(errors)
            if response is None:
                continue

            raw_items = response.get("resources") or response.get("items") or []
            if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
                result.errors.append(
                    error_entry(
                        self.stage,
                        f"MCP tool {tool_name} returned resources in an unsupported shape",
                        code="invalid_discovery_items",
                        tool_name=tool_name,
                    )
                )
                continue

            default_source = str(spec.get("source") or response.get("source") or tool_name)
            for raw in raw_items:
                if not isinstance(raw, Mapping):
                    result.errors.append(
                        error_entry(
                            self.stage,
                            "Skipping non-mapping discovery item",
                            code="invalid_discovery_item",
                            tool_name=tool_name,
                        )
                    )
                    continue
                result.items.append(coerce_resource(raw, default_source=default_source))

        result.log.append(
            log_entry(
                self.stage,
                "resources_discovered",
                "Discovery produced candidate resources",
                count=len(result.items),
            )
        )
        result.metadata["candidate_count"] = len(result.items)
        return result


def _tool_specs(raw: Any, default_tool: str) -> list[JsonDict]:
    if raw is None:
        return [{"tool_name": default_tool, "arguments": {}}]
    if isinstance(raw, Mapping):
        return [dict(raw)]
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        specs: list[JsonDict] = []
        for item in raw:
            if isinstance(item, str):
                specs.append({"tool_name": item, "arguments": {}})
            elif isinstance(item, Mapping):
                specs.append(dict(item))
        return specs or [{"tool_name": default_tool, "arguments": {}}]
    return [{"tool_name": default_tool, "arguments": {}}]
