from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Dict, Tuple, Union

from .models import ErrorCode, MCPRegistryError, ToolCallResult
from .redaction import redact_text, redact_value
from .registry import DEFAULT_TIMEOUT_S, MCPToolRegistry

ToolHandlerResult = Union[Mapping[str, Any], ToolCallResult]
ToolHandler = Callable[[Mapping[str, Any]], Union[ToolHandlerResult, Awaitable[ToolHandlerResult]]]


@dataclass(frozen=True)
class RecordedToolCall:
    server: str
    tool: str
    arguments: Mapping[str, Any]
    timeout_s: float


class FakeMCPClient:
    """In-memory MCP client for unit tests and dry-run local development."""

    def __init__(self, registry: MCPToolRegistry | None = None) -> None:
        self._registry = registry
        self._handlers: Dict[Tuple[str, str], ToolHandler] = {}
        self._calls: list[RecordedToolCall] = []

    @property
    def calls(self) -> Tuple[RecordedToolCall, ...]:
        return tuple(self._calls)

    def register_tool(self, server: str, tool: str, handler: ToolHandler) -> None:
        self._handlers[(server, tool)] = handler

    async def call_tool(
        self,
        server: str,
        tool: str,
        arguments: Mapping[str, Any],
        *,
        timeout_s: float | None = None,
    ) -> ToolCallResult:
        started = time.monotonic()
        effective_timeout = timeout_s

        if effective_timeout is not None and effective_timeout <= 0:
            return ToolCallResult.failure(
                server,
                tool,
                ErrorCode.VALIDATION_ERROR,
                "MCP tool timeout must be positive.",
            )

        try:
            if self._registry is not None:
                self._registry.validate_tool_call(server, tool, arguments)
                if effective_timeout is None:
                    effective_timeout = self._registry.timeout_for(server, tool)
                safe_arguments = self._registry.redact_arguments(server, tool, arguments)
            else:
                effective_timeout = effective_timeout or DEFAULT_TIMEOUT_S
                safe_arguments = redact_value(arguments)
        except MCPRegistryError as exc:
            return exc.to_result(server, tool)

        self._calls.append(
            RecordedToolCall(
                server=server,
                tool=tool,
                arguments=safe_arguments,
                timeout_s=effective_timeout,
            )
        )

        handler = self._handlers.get((server, tool))
        if handler is None:
            return ToolCallResult.failure(
                server,
                tool,
                ErrorCode.NOT_REGISTERED,
                "No fake MCP handler registered for %s.%s." % (server, tool),
                elapsed_s=_elapsed(started),
            )

        try:
            raw_result = await asyncio.wait_for(
                self._invoke(handler, arguments),
                timeout=effective_timeout,
            )
        except asyncio.TimeoutError:
            return ToolCallResult.failure(
                server,
                tool,
                ErrorCode.TIMEOUT,
                "MCP tool call timed out after %.3f seconds." % effective_timeout,
                retryable=True,
                elapsed_s=_elapsed(started),
            )
        except Exception as exc:  # pragma: no cover - exact exception type is handler-defined.
            return ToolCallResult.failure(
                server,
                tool,
                ErrorCode.TOOL_ERROR,
                "%s: %s" % (exc.__class__.__name__, redact_text(str(exc))),
                details={"exception_type": exc.__class__.__name__},
                elapsed_s=_elapsed(started),
            )

        elapsed_s = _elapsed(started)
        return self._normalize_result(server, tool, raw_result, elapsed_s)

    async def _invoke(self, handler: ToolHandler, arguments: Mapping[str, Any]) -> ToolHandlerResult:
        result = handler(dict(arguments))
        if inspect.isawaitable(result):
            return await result
        return result

    def _normalize_result(
        self,
        server: str,
        tool: str,
        raw_result: ToolHandlerResult,
        elapsed_s: float,
    ) -> ToolCallResult:
        if isinstance(raw_result, ToolCallResult):
            if not raw_result.ok:
                return raw_result
            output = raw_result.data or {}
        else:
            output = raw_result

        if not isinstance(output, Mapping):
            return ToolCallResult.failure(
                server,
                tool,
                ErrorCode.OUTPUT_VALIDATION_ERROR,
                "MCP fake handler output must be a mapping.",
                elapsed_s=elapsed_s,
            )

        if self._registry is not None:
            try:
                self._registry.validate_tool_output(server, tool, output)
            except MCPRegistryError as exc:
                return ToolCallResult.failure(
                    server,
                    tool,
                    exc.code,
                    exc.message,
                    details=exc.details,
                    elapsed_s=elapsed_s,
                )

        return ToolCallResult.success(server, tool, output, elapsed_s=elapsed_s)


def _elapsed(started: float) -> float:
    return time.monotonic() - started
