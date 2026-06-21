from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class Capability(str, Enum):
    """High-level application capabilities backed by configured MCP tools."""

    DISCOVERY_SEARCH = "discovery.search"
    GITHUB_INSPECT = "github.inspect"
    VIDEO_METADATA = "content.video_metadata"
    ARTICLE_METADATA = "content.article_metadata"
    CALENDAR_READ = "calendar.read"
    CALENDAR_WRITE = "calendar.write"
    FILESYSTEM_WRITE = "filesystem.write"
    REPORT_WRITE = "report.write"


class ErrorCode(str, Enum):
    INVALID_CONFIG = "invalid_config"
    SERVER_NOT_FOUND = "server_not_found"
    TOOL_NOT_ALLOWED = "tool_not_allowed"
    VALIDATION_ERROR = "validation_error"
    OUTPUT_VALIDATION_ERROR = "output_validation_error"
    NOT_REGISTERED = "not_registered"
    TIMEOUT = "timeout"
    TOOL_ERROR = "tool_error"


@dataclass(frozen=True)
class MCPErrorDetail:
    code: ErrorCode
    message: str
    server: str | None = None
    tool: str | None = None
    retryable: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "server": self.server,
            "tool": self.tool,
            "retryable": self.retryable,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class ToolCallResult:
    """Structured result returned by all MCP boundary calls."""

    ok: bool
    server: str
    tool: str
    data: Mapping[str, Any] | None = None
    error: MCPErrorDetail | None = None
    elapsed_s: float | None = None

    @classmethod
    def success(
        cls,
        server: str,
        tool: str,
        data: Mapping[str, Any],
        elapsed_s: float | None = None,
    ) -> ToolCallResult:
        return cls(
            ok=True,
            server=server,
            tool=tool,
            data=dict(data),
            error=None,
            elapsed_s=elapsed_s,
        )

    @classmethod
    def failure(
        cls,
        server: str,
        tool: str,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool = False,
        details: Mapping[str, Any] | None = None,
        elapsed_s: float | None = None,
    ) -> ToolCallResult:
        return cls(
            ok=False,
            server=server,
            tool=tool,
            data=None,
            error=MCPErrorDetail(
                code=code,
                message=message,
                server=server,
                tool=tool,
                retryable=retryable,
                details=dict(details or {}),
            ),
            elapsed_s=elapsed_s,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "server": self.server,
            "tool": self.tool,
            "data": dict(self.data or {}),
            "error": self.error.to_dict() if self.error else None,
            "elapsed_s": self.elapsed_s,
        }


class MCPRegistryError(ValueError):
    """Validation error raised before a tool call leaves the MCP boundary."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        server: str | None = None,
        tool: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.server = server
        self.tool = tool
        self.details = dict(details or {})

    def to_result(self, server: str, tool: str) -> ToolCallResult:
        return ToolCallResult.failure(
            server=server,
            tool=tool,
            code=self.code,
            message=self.message,
            details=self.details,
        )
