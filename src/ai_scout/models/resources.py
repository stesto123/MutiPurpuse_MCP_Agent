from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from hashlib import sha256
from types import MappingProxyType
from typing import Union

JsonScalar = Union[str, int, float, bool, None]


class ResourceKind(str, Enum):
    """Resource categories the scout can rank and schedule."""

    GITHUB_REPO = "github_repo"
    ARTICLE = "article"
    VIDEO = "video"
    PAPER = "paper"
    GENERIC = "generic"


def _clean_required_text(value: str, field_name: str) -> str:
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        raise ValueError(f"{field_name} cannot be empty")
    return cleaned


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.strip().split())
    return cleaned or None


def _clean_text_tuple(values: Iterable[str], *, lower: bool = False) -> tuple[str, ...]:
    seen: set[str] = set()
    cleaned_values: list[str] = []
    for value in values:
        cleaned = " ".join(value.strip().split())
        if lower:
            cleaned = cleaned.casefold()
        if cleaned and cleaned not in seen:
            cleaned_values.append(cleaned)
            seen.add(cleaned)
    return tuple(cleaned_values)


def _unit_interval(value: float, field_name: str) -> float:
    normalized = float(value)
    if normalized < 0.0 or normalized > 1.0:
        raise ValueError(f"{field_name} must be between 0.0 and 1.0")
    return normalized


def make_resource_id(kind: ResourceKind | str, title: str, url: str | None = None) -> str:
    """Build a stable local ID from public resource identity fields."""

    resource_kind = kind if isinstance(kind, ResourceKind) else ResourceKind(str(kind))
    identity = _clean_optional_text(url) or _clean_required_text(title, "title")
    payload = f"{resource_kind.value}:{identity.casefold()}"
    return "res_" + sha256(payload.encode("utf-8")).hexdigest()[:20]


@dataclass(frozen=True)
class Resource:
    """A scoutable AI learning resource from any supported source."""

    title: str
    kind: ResourceKind = ResourceKind.GENERIC
    url: str | None = None
    source_name: str | None = None
    summary: str | None = None
    topics: tuple[str, ...] = ()
    authors: tuple[str, ...] = ()
    published_at: datetime | None = None
    metadata: Mapping[str, JsonScalar] = field(default_factory=dict)
    resource_id: str | None = None

    def __post_init__(self) -> None:
        kind = self.kind if isinstance(self.kind, ResourceKind) else ResourceKind(str(self.kind))
        title = _clean_required_text(self.title, "title")
        url = _clean_optional_text(self.url)
        source_name = _clean_optional_text(self.source_name)
        summary = _clean_optional_text(self.summary)
        resource_id = _clean_optional_text(self.resource_id) or make_resource_id(kind, title, url)

        metadata: dict[str, JsonScalar] = {}
        for key, value in self.metadata.items():
            cleaned_key = _clean_required_text(str(key), "metadata key")
            if not isinstance(value, (str, int, float, bool)) and value is not None:
                raise TypeError("metadata values must be JSON scalar values")
            metadata[cleaned_key] = value

        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "source_name", source_name)
        object.__setattr__(self, "summary", summary)
        object.__setattr__(self, "topics", _clean_text_tuple(self.topics, lower=True))
        object.__setattr__(self, "authors", _clean_text_tuple(self.authors))
        object.__setattr__(self, "metadata", MappingProxyType(metadata))
        object.__setattr__(self, "resource_id", resource_id)


@dataclass(frozen=True)
class ResourceCandidate:
    """A discovered resource plus ranking hints from the discovery boundary."""

    resource: Resource
    discovered_at: datetime
    discovery_source: str = "unknown"
    source_quality: float = 0.5
    effort_minutes: int = 30
    local_applicability: float = 0.5
    novelty_hint: float | None = None
    rationale: str | None = None
    evidence: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    candidate_id: str | None = None

    def __post_init__(self) -> None:
        if self.effort_minutes <= 0:
            raise ValueError("effort_minutes must be positive")

        source_quality = _unit_interval(self.source_quality, "source_quality")
        local_applicability = _unit_interval(
            self.local_applicability, "local_applicability"
        )
        novelty_hint = (
            None
            if self.novelty_hint is None
            else _unit_interval(self.novelty_hint, "novelty_hint")
        )
        discovery_source = _clean_required_text(self.discovery_source, "discovery_source")
        rationale = _clean_optional_text(self.rationale)
        candidate_id = _clean_optional_text(self.candidate_id)
        if candidate_id is None:
            payload = f"{self.resource.resource_id}:{self.discovered_at.isoformat()}"
            candidate_id = "cand_" + sha256(payload.encode("utf-8")).hexdigest()[:20]

        object.__setattr__(self, "source_quality", source_quality)
        object.__setattr__(self, "local_applicability", local_applicability)
        object.__setattr__(self, "novelty_hint", novelty_hint)
        object.__setattr__(self, "discovery_source", discovery_source)
        object.__setattr__(self, "rationale", rationale)
        object.__setattr__(self, "evidence", _clean_text_tuple(self.evidence))
        object.__setattr__(self, "tags", _clean_text_tuple(self.tags, lower=True))
        object.__setattr__(self, "candidate_id", candidate_id)
