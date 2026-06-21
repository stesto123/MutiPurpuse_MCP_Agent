from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REDACTED = "[REDACTED]"
TRUNCATED = "[TRUNCATED]"

SENSITIVE_KEY_PARTS = (
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "client_secret",
    "cookie",
    "credential",
    "oauth",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "token",
)

SENSITIVE_QUERY_KEYS = (
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "code",
    "client_secret",
    "key",
    "oauth_token",
    "password",
    "refresh_token",
    "secret",
    "signature",
    "sig",
    "token",
)

SECRET_TEXT_RE = re.compile(
    r"(?i)\b("
    r"access_token|api_key|apikey|authorization|client_secret|password|"
    r"refresh_token|secret|token"
    r")\s*[:=]\s*([^\s,;&]+)"
)


def is_sensitive_key(key: object) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def redact_text(value: str, max_string_length: int = 500) -> str:
    redacted = SECRET_TEXT_RE.sub(lambda match: "%s=%s" % (match.group(1), REDACTED), value)
    redacted = redact_url(redacted)
    if len(redacted) > max_string_length:
        return redacted[:max_string_length] + "... " + TRUNCATED
    return redacted


def redact_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value

    if not parsed.scheme or not parsed.netloc:
        return value

    changed = False
    netloc = parsed.netloc
    if parsed.username or parsed.password:
        host = parsed.hostname or ""
        if parsed.port:
            host = "%s:%s" % (host, parsed.port)
        netloc = host
        changed = True

    query_pairs = []
    for key, item_value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower() in SENSITIVE_QUERY_KEYS:
            query_pairs.append((key, REDACTED))
            changed = True
        else:
            query_pairs.append((key, item_value))

    if not changed:
        return value

    query = urlencode(query_pairs, doseq=True)
    return urlunsplit((parsed.scheme, netloc, parsed.path, query, parsed.fragment))


def redact_value(
    value: Any,
    explicit_paths: Iterable[str] = (),
    *,
    max_depth: int = 8,
    max_string_length: int = 500,
) -> Any:
    path_patterns = tuple(_split_path(path) for path in explicit_paths)
    return _redact_value(
        value,
        path=(),
        path_patterns=path_patterns,
        max_depth=max_depth,
        max_string_length=max_string_length,
    )


def _redact_value(
    value: Any,
    *,
    path: Tuple[str, ...],
    path_patterns: Sequence[Tuple[str, ...]],
    max_depth: int,
    max_string_length: int,
) -> Any:
    if _matches_any_path(path, path_patterns):
        return REDACTED

    if max_depth < 0:
        return TRUNCATED

    if isinstance(value, Mapping):
        redacted = {}
        for key, item_value in value.items():
            key_string = str(key)
            if is_sensitive_key(key_string):
                redacted[key_string] = REDACTED
            else:
                redacted[key_string] = _redact_value(
                    item_value,
                    path=path + (key_string,),
                    path_patterns=path_patterns,
                    max_depth=max_depth - 1,
                    max_string_length=max_string_length,
                )
        return redacted

    if isinstance(value, (list, tuple)):
        return [
            _redact_value(
                item,
                path=path + (str(index),),
                path_patterns=path_patterns,
                max_depth=max_depth - 1,
                max_string_length=max_string_length,
            )
            for index, item in enumerate(value)
        ]

    if isinstance(value, str):
        return redact_text(value, max_string_length=max_string_length)

    return value


def _split_path(path: str) -> Tuple[str, ...]:
    return tuple(part for part in path.split(".") if part)


def _matches_any_path(path: Tuple[str, ...], patterns: Sequence[Tuple[str, ...]]) -> bool:
    return any(_path_matches(path, pattern) for pattern in patterns)


def _path_matches(path: Tuple[str, ...], pattern: Tuple[str, ...]) -> bool:
    if not pattern or len(path) != len(pattern):
        return False
    return all(pattern_part == "*" or pattern_part == path_part for path_part, pattern_part in zip(path, pattern))
