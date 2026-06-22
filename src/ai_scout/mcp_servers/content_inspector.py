"""Built-in local MCP content inspector.

The inspector treats resource text as untrusted data. It does not fetch URLs or
execute instructions from summaries; it only normalizes resource metadata into
the structured inspection shape consumed by the AI Scout graph.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def inspect_resource(
    resource: Mapping[str, Any],
    requested_fields: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Inspect a discovered resource using deterministic metadata heuristics."""

    del requested_fields
    if not isinstance(resource, Mapping):
        raise ValueError("resource must be a mapping")

    metadata = _mapping(resource.get("metadata"))
    title = _text(resource.get("title") or resource.get("name") or "Untitled resource")
    summary = _text(resource.get("summary") or resource.get("description") or "")
    url = _text(resource.get("url") or resource.get("uri") or resource.get("link") or "")
    source = _text(resource.get("source") or "unknown")
    kind = _text(metadata.get("kind") or resource.get("kind") or _kind_from_url(url, title))
    tags = _strings(metadata.get("tags") or resource.get("tags") or ())

    searchable = " ".join([title, summary, url, source, kind, " ".join(tags)]).casefold()
    estimated_minutes = _estimated_minutes(kind, searchable)
    signals = {
        "relevance": _score_relevance(searchable),
        "novelty": 0.78,
        "source_trust": _score_source_trust(url, source),
        "local_applicability": _score_local_applicability(searchable),
    }

    return {
        "content_summary": _content_summary(title, summary, kind),
        "signals": signals,
        "estimated_minutes": estimated_minutes,
        "metadata": {
            "inspection_strategy": "metadata_heuristic_v1",
            "source": source,
            "kind": kind or "generic",
        },
    }


def inspect(
    resource: dict[str, Any],
    requested_fields: list[str] | None = None,
) -> dict[str, Any]:
    """Inspect one resource and return summary, scoring signals, and effort."""

    return inspect_resource(resource, requested_fields)


def main() -> int:
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on optional runtime package.
        raise RuntimeError("Install the 'mcp' package to run this MCP server.") from exc

    server = FastMCP("AI Scout Content Inspector")
    server.tool()(inspect)
    server.run()
    return 0


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [_text(value)] if _text(value) else []
    if isinstance(value, Sequence):
        return [cleaned for item in value if (cleaned := _text(item))]
    return []


def _kind_from_url(url: str, title: str) -> str:
    combined = f"{url} {title}".casefold()
    if "github.com" in combined or "repo" in combined:
        return "github_repo"
    if "video" in combined or "youtube" in combined or "youtu.be" in combined:
        return "video"
    if "paper" in combined or "arxiv" in combined:
        return "paper"
    if url:
        return "article"
    return "generic"


def _estimated_minutes(kind: str, searchable: str) -> int:
    normalized = kind.casefold()
    if normalized == "github_repo" or "github.com" in searchable:
        return 60
    if normalized == "video" or "video" in searchable:
        return 45
    if normalized == "paper" or "arxiv" in searchable:
        return 75
    return 30


def _score_relevance(searchable: str) -> float:
    terms = ("ai", "agent", "mcp", "model context protocol", "langgraph", "eval", "automation")
    matches = sum(1 for term in terms if term in searchable)
    return _bounded(0.55 + min(matches, 4) * 0.1)


def _score_source_trust(url: str, source: str) -> float:
    combined = f"{url} {source}".casefold()
    if "github.com" in combined:
        return 0.74
    if "docs" in combined or "arxiv" in combined:
        return 0.78
    if "example.test" in combined or "built-in-local" in combined:
        return 0.68
    return 0.62


def _score_local_applicability(searchable: str) -> float:
    local_terms = ("local", "repo", "github", "mcp", "automation", "langgraph", "eval")
    matches = sum(1 for term in local_terms if term in searchable)
    return _bounded(0.5 + min(matches, 4) * 0.1)


def _content_summary(title: str, summary: str, kind: str) -> str:
    if summary:
        return summary
    kind_text = kind.replace("_", " ") if kind else "resource"
    return f"Metadata-only inspection for {kind_text}: {title}."


def _bounded(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


if __name__ == "__main__":
    raise SystemExit(main())

