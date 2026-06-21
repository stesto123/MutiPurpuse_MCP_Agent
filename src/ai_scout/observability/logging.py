from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|refresh[_-]?token|client[_-]?secret)=([^&\\s]+)"),
    re.compile(r"(?i)(Bearer\\s+)[A-Za-z0-9._\\-]+"),
]


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def redact_secrets(value: Any) -> Any:
    if isinstance(value, str):
        redacted = value
        for pattern in SECRET_PATTERNS:
            if "Bearer" in pattern.pattern:
                redacted = pattern.sub(r"\\1[REDACTED]", redacted)
            else:
                redacted = pattern.sub(r"\\1=[REDACTED]", redacted)
        return redacted
    if isinstance(value, Mapping):
        return {
            key: "[REDACTED]" if _looks_secret(str(key)) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item) for item in value)
    return value


def _looks_secret(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in ("secret", "token", "api_key", "apikey", "password"))

