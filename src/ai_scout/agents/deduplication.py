"""Deduplication specialist agent."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .types import AgentResult, JsonDict, get_resource, log_entry, stable_id


class DeduplicationAgent:
    """Mark current and memory-known duplicate resources."""

    stage = "deduplication"

    def run(
        self,
        items: Sequence[Mapping[str, Any]],
        memory_snapshot: Mapping[str, Any] | None = None,
    ) -> AgentResult:
        memory_snapshot = memory_snapshot or {}
        seen_ids = {str(value) for value in memory_snapshot.get("seen_resource_ids", [])}
        seen_urls = {_canonical_url(str(value)) for value in memory_snapshot.get("seen_urls", [])}
        seen_fingerprints = {
            str(value) for value in memory_snapshot.get("seen_fingerprints", [])
        }
        current_keys: dict[str, str] = {}
        result = AgentResult()

        for item in items:
            resource = get_resource(item)
            resource_id = str(resource["id"])
            url_key = _canonical_url(str(resource.get("url") or ""))
            fingerprint = _fingerprint(resource)
            duplicate_of = ""
            reason = "unique"

            if resource_id in seen_ids:
                duplicate_of = resource_id
                reason = "memory_resource_id"
            elif url_key and url_key in seen_urls:
                duplicate_of = stable_id("memory_url", url_key)
                reason = "memory_url"
            elif fingerprint in seen_fingerprints:
                duplicate_of = stable_id("memory_fingerprint", fingerprint)
                reason = "memory_fingerprint"
            elif url_key and url_key in current_keys:
                duplicate_of = current_keys[url_key]
                reason = "current_url"
            elif fingerprint in current_keys:
                duplicate_of = current_keys[fingerprint]
                reason = "current_fingerprint"

            deduped: JsonDict = dict(item)
            deduped["resource"] = resource
            deduped["resource_id"] = resource_id
            deduped["dedupe_key"] = url_key or fingerprint
            deduped["is_duplicate"] = bool(duplicate_of)
            deduped["duplicate_of"] = duplicate_of
            deduped["dedupe_reason"] = reason
            result.items.append(deduped)

            if not duplicate_of:
                if url_key:
                    current_keys[url_key] = resource_id
                current_keys[fingerprint] = resource_id

        result.log.append(
            log_entry(
                self.stage,
                "resources_deduplicated",
                "Deduplication marked duplicates",
                total=len(result.items),
                duplicates=sum(1 for item in result.items if item.get("is_duplicate")),
            )
        )
        return result


def _canonical_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower() or "https"
    host = parts.netloc.lower()
    path = parts.path.rstrip("/")
    return urlunsplit((scheme, host, path, "", ""))


def _fingerprint(resource: Mapping[str, Any]) -> str:
    source = str(resource.get("source") or "")
    title = str(resource.get("title") or "")
    url = _canonical_url(str(resource.get("url") or ""))
    return stable_id("fingerprint", source, url, title)
