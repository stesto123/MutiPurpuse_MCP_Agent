"""Shared typed structures and dependency interfaces for scout agents."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from typing import Any, Protocol

JsonDict = dict[str, Any]


class MCPGateway(Protocol):
    """Dependency-injected gateway for all external tool access."""

    def call_tool(self, tool_name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        """Call an MCP-exposed tool and return its structured response."""


class MemoryStore(Protocol):
    """Dependency-injected local memory boundary."""

    def load_snapshot(self, run_id: str) -> Mapping[str, Any]:
        """Return known resource IDs, URLs, and other dedupe hints."""

    def write_records(
        self, run_id: str, records: Sequence[Mapping[str, Any]]
    ) -> Mapping[str, Any]:
        """Persist run records and return a structured write result."""


class ReportSink(Protocol):
    """Dependency-injected reporting boundary."""

    def write_run_report(self, run_id: str, report: Mapping[str, Any]) -> Mapping[str, Any]:
        """Persist a run report and return a structured write result."""


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 2

    def attempts(self) -> range:
        return range(1, max(1, self.max_attempts) + 1)


@dataclass
class AgentResult:
    items: list[JsonDict] = field(default_factory=list)
    errors: list[JsonDict] = field(default_factory=list)
    log: list[JsonDict] = field(default_factory=list)
    side_effects: list[JsonDict] = field(default_factory=list)
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return asdict(self)


SENSITIVE_KEY_PARTS = ("token", "secret", "password", "credential", "authorization")


def redact_sensitive(value: Any) -> Any:
    """Redact sensitive-looking values while preserving useful structure."""

    if isinstance(value, Mapping):
        redacted: JsonDict = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if any(part in key_text for part in SENSITIVE_KEY_PARTS):
                redacted[str(key)] = "[redacted]"
            else:
                redacted[str(key)] = redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive(item) for item in value)
    return value


def stable_id(prefix: str, *parts: object) -> str:
    normalized = "\x1f".join("" if part is None else str(part).strip().lower() for part in parts)
    digest = sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def log_entry(stage: str, event: str, message: str, **details: Any) -> JsonDict:
    entry: JsonDict = {"stage": stage, "event": event, "message": message}
    if details:
        entry["details"] = redact_sensitive(details)
    return entry


def error_entry(
    stage: str,
    message: str,
    *,
    retryable: bool = False,
    code: str = "agent_error",
    **details: Any,
) -> JsonDict:
    entry: JsonDict = {
        "stage": stage,
        "code": code,
        "message": message,
        "retryable": retryable,
    }
    if details:
        entry["details"] = redact_sensitive(details)
    return entry


def coerce_resource(raw: Mapping[str, Any], *, default_source: str) -> JsonDict:
    """Normalize a tool-provided resource into the scout resource shape."""

    source = str(raw.get("source") or default_source)
    title = str(raw.get("title") or raw.get("name") or "Untitled resource")
    url = raw.get("url") or raw.get("uri") or raw.get("link")
    summary = raw.get("summary") or raw.get("description") or ""
    resource_id = raw.get("id") or raw.get("resource_id")
    if not resource_id:
        resource_id = stable_id("resource", source, url, title)

    known_keys = {
        "id",
        "resource_id",
        "source",
        "title",
        "name",
        "url",
        "uri",
        "link",
        "summary",
        "description",
        "metadata",
    }
    metadata = dict(raw.get("metadata") or {})
    for key, value in raw.items():
        if key not in known_keys:
            metadata.setdefault(str(key), value)

    resource: JsonDict = {
        "id": str(resource_id),
        "source": source,
        "title": title,
        "url": str(url) if url is not None else "",
        "summary": str(summary),
        "metadata": redact_sensitive(metadata),
    }
    return resource


def get_resource(item: Mapping[str, Any]) -> JsonDict:
    resource = item.get("resource")
    if isinstance(resource, Mapping):
        return dict(resource)
    return coerce_resource(item, default_source=str(item.get("source") or "unknown"))
