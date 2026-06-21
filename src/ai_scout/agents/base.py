"""Small shared helpers for specialist agents."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .types import JsonDict, MCPGateway, RetryPolicy, error_entry, log_entry, redact_sensitive


def call_tool_with_retries(
    gateway: MCPGateway,
    *,
    tool_name: str,
    arguments: Mapping[str, Any],
    stage: str,
    retry_policy: RetryPolicy,
) -> tuple[JsonDict | None, list[JsonDict], list[JsonDict]]:
    """Call an MCP tool with bounded retries and explicit retry logging."""

    log: list[JsonDict] = []
    errors: list[JsonDict] = []
    attempts = list(retry_policy.attempts())

    for attempt in attempts:
        log.append(
            log_entry(
                stage,
                "tool_call_started",
                f"Calling MCP tool {tool_name}",
                tool_name=tool_name,
                attempt=attempt,
                arguments=redact_sensitive(dict(arguments)),
            )
        )
        try:
            response = gateway.call_tool(tool_name, dict(arguments))
        except Exception as exc:  # pragma: no cover - exact exception is gateway-specific.
            retryable = attempt < attempts[-1]
            log.append(
                log_entry(
                    stage,
                    "tool_call_failed",
                    f"MCP tool {tool_name} failed",
                    tool_name=tool_name,
                    attempt=attempt,
                    retryable=retryable,
                    error_type=exc.__class__.__name__,
                    error=str(exc),
                )
            )
            if not retryable:
                errors.append(
                    error_entry(
                        stage,
                        f"MCP tool {tool_name} failed after {attempt} attempt(s)",
                        retryable=False,
                        code="mcp_tool_failed",
                        tool_name=tool_name,
                        attempt=attempt,
                        error_type=exc.__class__.__name__,
                        error=str(exc),
                    )
                )
            continue

        if not isinstance(response, Mapping):
            message = f"MCP tool {tool_name} returned a non-mapping response"
            errors.append(
                error_entry(
                    stage,
                    message,
                    retryable=False,
                    code="invalid_tool_response",
                    tool_name=tool_name,
                    attempt=attempt,
                    response_type=type(response).__name__,
                )
            )
            log.append(log_entry(stage, "tool_call_invalid", message, tool_name=tool_name))
            return None, log, errors

        log.append(
            log_entry(
                stage,
                "tool_call_succeeded",
                f"MCP tool {tool_name} succeeded",
                tool_name=tool_name,
                attempt=attempt,
            )
        )
        return dict(response), log, errors

    return None, log, errors
