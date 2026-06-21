"""Inspection specialist agent."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .base import call_tool_with_retries
from .types import AgentResult, MCPGateway, RetryPolicy, get_resource, log_entry


class InspectionAgent:
    """Inspect resource candidates through an MCP gateway."""

    stage = "inspection"

    def __init__(
        self,
        gateway: MCPGateway,
        retry_policy: RetryPolicy | None = None,
        *,
        default_tool: str = "content.inspect",
    ) -> None:
        self.gateway = gateway
        self.retry_policy = retry_policy or RetryPolicy()
        self.default_tool = default_tool

    def run(
        self,
        resources: Sequence[Mapping[str, Any]],
        request: Mapping[str, Any] | None = None,
    ) -> AgentResult:
        request = request or {}
        tool_name = str(request.get("tool_name") or self.default_tool)
        result = AgentResult()

        for item in resources:
            resource = get_resource(item)
            arguments = {
                "resource": resource,
                "requested_fields": request.get(
                    "requested_fields", ["summary", "signals", "estimated_minutes"]
                ),
            }
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
                result.items.append(
                    {
                        "resource": resource,
                        "resource_id": resource["id"],
                        "status": "failed",
                        "content_summary": resource.get("summary", ""),
                        "signals": {},
                        "metadata": {"inspection_tool": tool_name},
                    }
                )
                continue

            result.items.append(
                {
                    "resource": resource,
                    "resource_id": resource["id"],
                    "status": "inspected",
                    "content_summary": str(
                        response.get("content_summary")
                        or response.get("summary")
                        or resource.get("summary", "")
                    ),
                    "signals": dict(response.get("signals") or {}),
                    "estimated_minutes": response.get("estimated_minutes"),
                    "metadata": dict(response.get("metadata") or {}),
                }
            )

        result.log.append(
            log_entry(
                self.stage,
                "resources_inspected",
                "Inspection completed for candidate resources",
                count=len(result.items),
                failures=sum(1 for item in result.items if item.get("status") == "failed"),
            )
        )
        return result
