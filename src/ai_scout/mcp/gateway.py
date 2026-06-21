from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Union

from .client import MCPClient
from .models import Capability, MCPRegistryError, ToolCallResult
from .registry import MCPToolRegistry


class MCPGateway:
    """High-level AI Scout capabilities backed only by generic MCP tool calls."""

    def __init__(self, client: MCPClient, registry: MCPToolRegistry) -> None:
        self._client = client
        self._registry = registry

    async def discovery_search(
        self,
        query: str,
        *,
        limit: int = 10,
        source_types: Sequence[str] | None = None,
        filters: Mapping[str, Any] | None = None,
        timeout_s: float | None = None,
    ) -> ToolCallResult:
        arguments = {
            "query": query,
            "limit": limit,
            "source_types": list(source_types or ()),
            "filters": dict(filters or {}),
        }
        return await self._call_capability(Capability.DISCOVERY_SEARCH, arguments, timeout_s=timeout_s)

    async def inspect_github(
        self,
        repository: str,
        *,
        resource_type: str = "repository",
        identifier: Union[int, str] | None = None,
        ref: str | None = None,
        timeout_s: float | None = None,
    ) -> ToolCallResult:
        arguments = {
            "repository": repository,
            "resource_type": resource_type,
            "identifier": identifier,
            "ref": ref,
        }
        return await self._call_capability(Capability.GITHUB_INSPECT, arguments, timeout_s=timeout_s)

    async def get_video_metadata(
        self,
        url: str,
        *,
        include_transcript: bool = False,
        timeout_s: float | None = None,
    ) -> ToolCallResult:
        arguments = {
            "url": url,
            "include_transcript": include_transcript,
        }
        return await self._call_capability(Capability.VIDEO_METADATA, arguments, timeout_s=timeout_s)

    async def get_article_metadata(
        self,
        url: str,
        *,
        timeout_s: float | None = None,
    ) -> ToolCallResult:
        return await self._call_capability(Capability.ARTICLE_METADATA, {"url": url}, timeout_s=timeout_s)

    async def read_calendar(
        self,
        *,
        start: Any,
        end: Any,
        calendar_id: str | None = None,
        timeout_s: float | None = None,
    ) -> ToolCallResult:
        arguments = {
            "start": _isoformat_or_value(start),
            "end": _isoformat_or_value(end),
            "calendar_id": calendar_id,
        }
        return await self._call_capability(Capability.CALENDAR_READ, arguments, timeout_s=timeout_s)

    async def write_calendar_event(
        self,
        event: Mapping[str, Any],
        *,
        idempotency_key: str,
        calendar_id: str | None = None,
        timeout_s: float | None = None,
    ) -> ToolCallResult:
        arguments = {
            "event": dict(event),
            "idempotency_key": idempotency_key,
            "calendar_id": calendar_id,
        }
        return await self._call_capability(Capability.CALENDAR_WRITE, arguments, timeout_s=timeout_s)

    async def write_filesystem(
        self,
        path: str,
        contents: str,
        *,
        purpose: str = "runtime_state",
        metadata: Mapping[str, Any] | None = None,
        timeout_s: float | None = None,
    ) -> ToolCallResult:
        arguments = {
            "path": path,
            "contents": contents,
            "purpose": purpose,
            "metadata": dict(metadata or {}),
        }
        return await self._call_capability(Capability.FILESYSTEM_WRITE, arguments, timeout_s=timeout_s)

    async def write_report(
        self,
        path: str,
        contents: str,
        *,
        run_id: str,
        report_format: str = "markdown",
        metadata: Mapping[str, Any] | None = None,
        timeout_s: float | None = None,
    ) -> ToolCallResult:
        arguments = {
            "path": path,
            "contents": contents,
            "run_id": run_id,
            "format": report_format,
            "metadata": dict(metadata or {}),
        }
        return await self._call_capability(Capability.REPORT_WRITE, arguments, timeout_s=timeout_s)

    async def _call_capability(
        self,
        capability: Union[Capability, str],
        arguments: Mapping[str, Any],
        *,
        timeout_s: float | None = None,
    ) -> ToolCallResult:
        capability_value = capability.value if isinstance(capability, Capability) else str(capability)
        try:
            binding = self._registry.resolve_capability(capability)
            self._registry.validate_tool_call(binding.server, binding.tool, arguments)
        except MCPRegistryError as exc:
            return ToolCallResult.failure(
                exc.server or "registry",
                exc.tool or capability_value,
                exc.code,
                exc.message,
                details=exc.details,
            )

        result = await self._client.call_tool(
            binding.server,
            binding.tool,
            arguments,
            timeout_s=timeout_s if timeout_s is not None else binding.timeout_s,
        )
        if not result.ok:
            return result

        try:
            self._registry.validate_tool_output(binding.server, binding.tool, result.data or {})
        except MCPRegistryError as exc:
            return ToolCallResult.failure(
                binding.server,
                binding.tool,
                exc.code,
                exc.message,
                details=exc.details,
                elapsed_s=result.elapsed_s,
            )
        return result


def _isoformat_or_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
