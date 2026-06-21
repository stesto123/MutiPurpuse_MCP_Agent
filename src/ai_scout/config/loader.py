from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict


class ConfigError(RuntimeError):
    """Raised when configuration cannot be loaded or validated."""


@dataclass(frozen=True)
class RuntimePaths:
    """Local runtime paths for safe public-repo operation."""

    config_dir: Path
    data_dir: Path

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"

    @property
    def memory_dir(self) -> Path:
        return self.data_dir / "memory"

    def ensure(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.memory_dir.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class AppConfig:
    """Merged runtime configuration.

    The shape intentionally remains broad for phase 1 so specialist modules can
    consume their own sections without hard-coding personal values.
    """

    mode: str = "dry_run"
    profile: Mapping[str, Any] = field(default_factory=dict)
    policy: Mapping[str, Any] = field(default_factory=dict)
    sources: Mapping[str, Any] = field(default_factory=dict)
    mcp: Mapping[str, Any] = field(default_factory=dict)
    raw: Mapping[str, Any] = field(default_factory=dict)

    @property
    def autonomous(self) -> bool:
        return self.mode == "autonomous"

    @property
    def dry_run(self) -> bool:
        return self.mode != "autonomous"


def default_runtime_paths() -> RuntimePaths:
    config_dir = Path(os.environ.get("AI_SCOUT_CONFIG_DIR", "~/.config/ai-scout")).expanduser()
    data_dir = Path(os.environ.get("AI_SCOUT_DATA_DIR", "~/.local/share/ai-scout")).expanduser()
    return RuntimePaths(config_dir=config_dir, data_dir=data_dir)


def load_app_config(
    config_dir: Path | None = None,
    *,
    mode: str | None = None,
    allow_missing: bool = True,
) -> AppConfig:
    paths = default_runtime_paths()
    root = (config_dir or paths.config_dir).expanduser()
    profile = _load_optional_mapping(root / "profile.yaml", allow_missing=allow_missing)
    policy = _load_optional_mapping(root / "policy.yaml", allow_missing=allow_missing)
    sources = _load_optional_mapping(root / "sources.yaml", allow_missing=allow_missing)
    mcp = _load_optional_mapping(root / "mcp.yaml", allow_missing=allow_missing)

    selected_mode = (
        mode
        or os.environ.get("AI_SCOUT_MODE")
        or str(policy.get("mode") or profile.get("mode") or "dry_run")
    )
    if selected_mode not in {"observe", "dry_run", "assist", "autonomous"}:
        raise ConfigError(
            "mode must be one of observe, dry_run, assist, autonomous "
            f"(got {selected_mode!r})"
        )

    raw: Dict[str, Any] = {
        "profile": dict(profile),
        "policy": dict(policy),
        "sources": dict(sources),
        "mcp": dict(mcp),
    }
    return AppConfig(
        mode=selected_mode,
        profile=profile,
        policy=policy,
        sources=sources,
        mcp=mcp,
        raw=raw,
    )


def _load_optional_mapping(path: Path, *, allow_missing: bool) -> Mapping[str, Any]:
    if not path.exists():
        if allow_missing:
            return {}
        raise ConfigError(f"Missing config file: {path}")
    data = _load_mapping(path)
    if not isinstance(data, Mapping):
        raise ConfigError(f"Config file must contain a mapping: {path}")
    return data


def _load_mapping(path: Path) -> Mapping[str, Any]:
    suffix = path.suffix.lower()
    try:
        if suffix == ".json":
            return json.loads(path.read_text(encoding="utf-8"))
        if suffix in {".yaml", ".yml"}:
            text = path.read_text(encoding="utf-8")
            try:
                import yaml  # type: ignore
            except ImportError:
                return _load_simple_yaml_mapping(text)
            loaded = yaml.safe_load(text)
            return loaded or {}
    except OSError as exc:
        raise ConfigError(f"Unable to read config file {path}: {exc}") from exc
    except Exception as exc:
        if isinstance(exc, ConfigError):
            raise
        raise ConfigError(f"Unable to parse config file {path}: {exc}") from exc
    raise ConfigError(f"Unsupported config format for {path}; use .yaml, .yml, or .json")


def _load_simple_yaml_mapping(text: str) -> Mapping[str, Any]:
    """Parse a small YAML subset when PyYAML is unavailable.

    This supports the public example configs: nested mappings, lists, booleans,
    nulls, quoted strings, and numeric scalars. PyYAML remains the preferred
    parser for full YAML support.
    """

    lines = []
    for raw in text.splitlines():
        stripped_line = _strip_comment(raw).rstrip()
        if not stripped_line.strip():
            continue
        indent = len(stripped_line) - len(stripped_line.lstrip(" "))
        lines.append((indent, stripped_line.lstrip(" ")))
    if not lines:
        return {}
    parsed, index = _parse_yaml_block(lines, 0, lines[0][0])
    if index != len(lines):
        raise ConfigError("Unable to parse all YAML lines with the fallback parser")
    if not isinstance(parsed, Mapping):
        raise ConfigError("YAML config root must be a mapping")
    return parsed


def _parse_yaml_block(lines: list, index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index
    current_indent, content = lines[index]
    if current_indent < indent:
        return {}, index
    if content.startswith("- "):
        return _parse_yaml_list(lines, index, current_indent)
    return _parse_yaml_mapping(lines, index, current_indent)


def _parse_yaml_mapping(lines: list, index: int, indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        current_indent, content = lines[index]
        if current_indent < indent:
            break
        if current_indent > indent:
            raise ConfigError(f"Unexpected indentation near: {content}")
        if content.startswith("- "):
            break
        key, value_text = _split_yaml_key_value(content)
        index += 1
        if value_text == "":
            if index < len(lines) and lines[index][0] > current_indent:
                value, index = _parse_yaml_block(lines, index, lines[index][0])
            else:
                value = {}
        else:
            value = _parse_yaml_scalar(value_text)
        result[key] = value
    return result, index


def _parse_yaml_list(lines: list, index: int, indent: int) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines):
        current_indent, content = lines[index]
        if current_indent < indent:
            break
        if current_indent != indent or not content.startswith("- "):
            break
        item_text = content[2:].strip()
        index += 1

        if item_text == "":
            if index < len(lines) and lines[index][0] > current_indent:
                item, index = _parse_yaml_block(lines, index, lines[index][0])
            else:
                item = None
        elif _looks_like_key_value(item_text):
            key, value_text = _split_yaml_key_value(item_text)
            item_map: dict[str, Any] = {
                key: _parse_yaml_scalar(value_text) if value_text else {}
            }
            if index < len(lines) and lines[index][0] > current_indent:
                child, index = _parse_yaml_block(lines, index, lines[index][0])
                if isinstance(child, Mapping):
                    item_map.update(child)
                else:
                    item_map[key] = child
            item = item_map
        else:
            item = _parse_yaml_scalar(item_text)
        result.append(item)
    return result, index


def _split_yaml_key_value(content: str) -> tuple[str, str]:
    if ":" not in content:
        raise ConfigError(f"Expected YAML key/value pair near: {content}")
    key, value = content.split(":", 1)
    key = key.strip()
    if not key:
        raise ConfigError(f"Expected non-empty YAML key near: {content}")
    return key, value.strip()


def _looks_like_key_value(content: str) -> bool:
    if ":" not in content:
        return False
    first = content[0]
    return first not in {"'", '"'}


def _parse_yaml_scalar(value: str) -> Any:
    if value == "":
        return ""
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    lowered = value.casefold()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none", "~"}:
        return None
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _strip_comment(line: str) -> str:
    quote: str | None = None
    escaped = False
    chars = []
    for char in line:
        if escaped:
            chars.append(char)
            escaped = False
            continue
        if char == "\\" and quote == '"':
            chars.append(char)
            escaped = True
            continue
        if char in {"'", '"'}:
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
            chars.append(char)
            continue
        if char == "#" and quote is None:
            break
        chars.append(char)
    return "".join(chars)
