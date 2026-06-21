from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ai_scout.models import Resource, ResourceCandidate

TRACKING_QUERY_KEYS = frozenset(
    {
        "dclid",
        "fbclid",
        "gclid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "msclkid",
        "ref",
        "ref_src",
        "spm",
        "utm",
        "utm_campaign",
        "utm_content",
        "utm_medium",
        "utm_source",
        "utm_term",
    }
)

_PUNCTUATION_RE = re.compile(r"[^\w\s+#.]+", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class DuplicateDecision:
    kept_resource_id: str
    duplicate_resource_id: str
    duplicate_key: str


@dataclass(frozen=True)
class DeduplicationResult:
    unique: tuple[ResourceCandidate, ...]
    duplicates: tuple[DuplicateDecision, ...]


def normalize_url(url: str | None) -> str | None:
    """Normalize a URL for identity comparisons without fetching it."""

    if url is None:
        return None
    raw = url.strip()
    if not raw:
        return None
    if raw.startswith("www.") or (
        "://" not in raw and re.match(r"^[^/\s]+\.[^/\s]+", raw)
    ):
        raw = "https://" + raw

    split = urlsplit(raw)
    scheme = split.scheme.casefold() if split.scheme else "https"
    host = (split.hostname or "").casefold()
    if not host and split.path:
        return _normalize_freeform_url(raw)

    try:
        port = split.port
    except ValueError:
        port = None
    include_port = port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    )
    netloc = host if not include_port else f"{host}:{port}"

    path = re.sub(r"/{2,}", "/", split.path or "")
    path = path.rstrip("/")
    if host in {"github.com", "www.github.com"}:
        path = _normalize_github_path(path)

    query_items = [
        (key, value)
        for key, value in parse_qsl(split.query, keep_blank_values=True)
        if key.casefold() not in TRACKING_QUERY_KEYS and not key.casefold().startswith("utm_")
    ]
    query = urlencode(sorted(query_items), doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def _normalize_freeform_url(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip().casefold()
    return value.rstrip("/")


def _normalize_github_path(path: str) -> str:
    if not path:
        return path
    cleaned = path.rstrip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    parts = [part for part in cleaned.split("/") if part]
    if len(parts) >= 2:
        parts[0] = parts[0].casefold()
        parts[1] = parts[1].casefold()
    return "/" + "/".join(parts)


def normalize_title(title: str | None) -> str | None:
    if title is None:
        return None
    normalized = unicodedata.normalize("NFKC", title).casefold()
    normalized = normalized.replace("&", " and ")
    normalized = _PUNCTUATION_RE.sub(" ", normalized)
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized or None


def identity_keys_for_resource(resource: Resource) -> tuple[str, ...]:
    keys: list[str] = [f"id:{resource.resource_id}"]
    normalized_url = normalize_url(resource.url)
    normalized_title = normalize_title(resource.title)
    if normalized_url is not None:
        keys.append(f"url:{normalized_url}")
    if normalized_title is not None:
        keys.append(f"title:{normalized_title}")
    return tuple(keys)


def build_seen_identity_keys(
    resources: tuple[Resource, ...] = (),
    *,
    resource_ids: tuple[str, ...] = (),
    urls: tuple[str, ...] = (),
    titles: tuple[str, ...] = (),
    identity_keys: tuple[str, ...] = (),
) -> frozenset[str]:
    keys: set[str] = set(identity_keys)
    for resource in resources:
        keys.update(identity_keys_for_resource(resource))
    for resource_id in resource_ids:
        cleaned = resource_id.strip()
        if cleaned:
            keys.add(f"id:{cleaned}")
    for url in urls:
        normalized = normalize_url(url)
        if normalized is not None:
            keys.add(f"url:{normalized}")
    for title in titles:
        normalized = normalize_title(title)
        if normalized is not None:
            keys.add(f"title:{normalized}")
    return frozenset(keys)


def deduplicate_candidates_with_report(
    candidates: tuple[ResourceCandidate, ...],
) -> DeduplicationResult:
    unique: list[ResourceCandidate] = []
    duplicates: list[DuplicateDecision] = []
    seen: dict[str, ResourceCandidate] = {}

    for candidate in candidates:
        duplicate_key = next(
            (key for key in identity_keys_for_resource(candidate.resource) if key in seen),
            None,
        )
        if duplicate_key is not None:
            kept = seen[duplicate_key]
            duplicates.append(
                DuplicateDecision(
                    kept_resource_id=kept.resource.resource_id or "",
                    duplicate_resource_id=candidate.resource.resource_id or "",
                    duplicate_key=duplicate_key,
                )
            )
            continue

        unique.append(candidate)
        for key in identity_keys_for_resource(candidate.resource):
            seen[key] = candidate

    return DeduplicationResult(unique=tuple(unique), duplicates=tuple(duplicates))


def deduplicate_candidates(
    candidates: tuple[ResourceCandidate, ...],
) -> tuple[ResourceCandidate, ...]:
    return deduplicate_candidates_with_report(candidates).unique


def filter_seen_candidates(
    candidates: tuple[ResourceCandidate, ...],
    *,
    seen_resources: tuple[Resource, ...] = (),
    seen_resource_ids: tuple[str, ...] = (),
    seen_urls: tuple[str, ...] = (),
    seen_titles: tuple[str, ...] = (),
    seen_identity_keys: tuple[str, ...] = (),
) -> tuple[ResourceCandidate, ...]:
    seen = build_seen_identity_keys(
        seen_resources,
        resource_ids=seen_resource_ids,
        urls=seen_urls,
        titles=seen_titles,
        identity_keys=seen_identity_keys,
    )
    return tuple(
        candidate
        for candidate in candidates
        if not seen.intersection(identity_keys_for_resource(candidate.resource))
    )


def filter_seen_resources(
    resources: tuple[Resource, ...],
    *,
    seen_resources: tuple[Resource, ...] = (),
    seen_resource_ids: tuple[str, ...] = (),
    seen_urls: tuple[str, ...] = (),
    seen_titles: tuple[str, ...] = (),
    seen_identity_keys: tuple[str, ...] = (),
) -> tuple[Resource, ...]:
    seen = build_seen_identity_keys(
        seen_resources,
        resource_ids=seen_resource_ids,
        urls=seen_urls,
        titles=seen_titles,
        identity_keys=seen_identity_keys,
    )
    return tuple(
        resource
        for resource in resources
        if not seen.intersection(identity_keys_for_resource(resource))
    )
