"""Built-in MCP server for low-risk web feed discovery.

This is the first external-read MCP server intended for real use. It fetches
RSS/Atom XML feeds over HTTP(S), parses metadata, and returns resources in the
shape consumed by AI Scout. It does not execute fetched content and does not
follow instructions contained in feed entries.
"""

from __future__ import annotations

import html
import re
from collections.abc import Sequence
from hashlib import sha256
from typing import Any
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree

DEFAULT_TIMEOUT_S = 10
MAX_FEED_BYTES = 2_000_000
USER_AGENT = "ai-scout-agent/0.1 (+https://example.local/ai-scout)"
HTML_TAG_RE = re.compile(r"<[^>]+>")


def fetch_feed(
    locator: str,
    *,
    id: str | None = None,
    kind: str | None = None,
    max_results: int | None = None,
    max_items_per_run: int | None = None,
    topics: Sequence[Any] | None = None,
    source_id: str | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """Fetch an RSS/Atom feed and return scoutable resources."""

    url = _validate_url(locator)
    source = source_id or id or url
    feed_bytes = _fetch_bytes(url, timeout_s=timeout_s)
    resources = parse_feed_bytes(
        feed_bytes,
        feed_url=url,
        max_results=_positive_int(max_items_per_run or max_results, default=10),
        topics=topics or (),
        source_id=source,
        kind=kind or "article",
    )
    return {"resources": resources, "source": source}


def parse_feed_bytes(
    feed_bytes: bytes,
    *,
    feed_url: str,
    max_results: int,
    topics: Sequence[Any] = (),
    source_id: str | None = None,
    kind: str = "article",
) -> list[dict[str, Any]]:
    root = ElementTree.fromstring(feed_bytes)
    entries = _rss_items(root) or _atom_entries(root)
    del topics
    resources: list[dict[str, Any]] = []

    for entry in entries:
        title = _entry_text(entry, ("title",)) or "Untitled feed item"
        link = _entry_link(entry, feed_url)
        summary = _entry_text(entry, ("description", "summary", "subtitle", "content", "encoded"))

        published = _entry_text(entry, ("pubDate", "published", "updated", "date"))
        resource_id = _stable_resource_id(source_id or feed_url, link or title)
        resources.append(
            {
                "id": resource_id,
                "source": source_id or feed_url,
                "title": title,
                "url": link,
                "summary": summary,
                "kind": kind,
                "metadata": {
                    "feed_url": feed_url,
                    "published_at": published,
                    "content_is_untrusted": True,
                },
            }
        )
        if len(resources) >= max_results:
            break

    return resources


def main() -> int:
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on optional runtime package.
        raise RuntimeError("Install the 'mcp' package to run this MCP server.") from exc

    server = FastMCP("AI Scout Web Feed")
    server.tool()(fetch_feed)
    server.run()
    return 0


def _validate_url(locator: str) -> str:
    url = str(locator or "").strip()
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("locator must be an absolute http(s) URL")
    return url


def _fetch_bytes(url: str, *, timeout_s: float) -> bytes:
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout_s) as response:  # noqa: S310
        return response.read(MAX_FEED_BYTES + 1)[:MAX_FEED_BYTES]


def _rss_items(root: ElementTree.Element) -> list[ElementTree.Element]:
    return [
        element
        for element in root.iter()
        if _local_name(element.tag) == "item"
    ]


def _atom_entries(root: ElementTree.Element) -> list[ElementTree.Element]:
    return [
        element
        for element in root.iter()
        if _local_name(element.tag) == "entry"
    ]


def _entry_text(entry: ElementTree.Element, names: Sequence[str]) -> str:
    wanted = {name.casefold() for name in names}
    for child in entry.iter():
        if child is entry:
            continue
        if _local_name(child.tag).casefold() not in wanted:
            continue
        if child.text:
            return _clean_text(child.text)
    return ""


def _entry_link(entry: ElementTree.Element, feed_url: str) -> str:
    for child in entry.iter():
        if _local_name(child.tag) != "link":
            continue
        href = str(child.attrib.get("href") or "").strip()
        if href:
            return urljoin(feed_url, href)
        if child.text:
            return urljoin(feed_url, _clean_text(child.text))
    return ""


def _clean_text(value: str) -> str:
    without_tags = HTML_TAG_RE.sub(" ", value)
    unescaped = html.unescape(without_tags)
    return " ".join(unescaped.strip().split())


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _stable_resource_id(source: str, identity: str) -> str:
    digest = sha256(f"{source}\x1f{identity}".encode()).hexdigest()[:16]
    return f"feed_{digest}"


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value if value is not None else default)
    except (TypeError, ValueError):
        return default
    return max(1, parsed)


if __name__ == "__main__":
    raise SystemExit(main())
