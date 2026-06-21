from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

from .models import Capability, ErrorCode, MCPRegistryError
from .redaction import redact_value

DEFAULT_TIMEOUT_S = 30.0


@dataclass(frozen=True)
class ToolBinding:
    capability: str
    server: str
    tool: str
    timeout_s: float


@dataclass(frozen=True)
class ToolSpec:
    name: str
    server: str
    enabled: bool = True
    timeout_s: float | None = None
    description: str = ""
    capabilities: Tuple[str, ...] = ()
    required_inputs: Tuple[str, ...] = ()
    required_outputs: Tuple[str, ...] = ()
    redact_inputs: Tuple[str, ...] = ()
    redact_outputs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ServerSpec:
    name: str
    enabled: bool = True
    transport: Mapping[str, Any] = field(default_factory=dict)
    default_timeout_s: float = DEFAULT_TIMEOUT_S
    tools: Mapping[str, ToolSpec] = field(default_factory=dict)


class MCPToolRegistry:
    """Config-driven registry and allowlist for MCP servers and tools."""

    def __init__(
        self,
        servers: Mapping[str, ServerSpec],
        capability_bindings: Mapping[str, Tuple[str, str]],
    ) -> None:
        self._servers = dict(servers)
        self._capability_bindings = dict(capability_bindings)

    @classmethod
    def empty(cls) -> MCPToolRegistry:
        return cls({}, {})

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> MCPToolRegistry:
        config_path = Path(path)
        contents = config_path.read_text(encoding="utf-8")
        suffix = config_path.suffix.lower()

        if suffix == ".json":
            return cls.from_mapping(json.loads(contents))

        if suffix in (".yaml", ".yml"):
            try:
                import yaml  # type: ignore
            except ImportError:
                from ai_scout.config.loader import _load_simple_yaml_mapping

                loaded = _load_simple_yaml_mapping(contents)
            else:
                loaded = yaml.safe_load(contents)
            return cls.from_mapping(loaded or {})

        raise MCPRegistryError(
            ErrorCode.INVALID_CONFIG,
            "Unsupported MCP config format: %s" % config_path.name,
        )

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any]) -> MCPToolRegistry:
        if not isinstance(config, Mapping):
            raise MCPRegistryError(ErrorCode.INVALID_CONFIG, "MCP registry config must be a mapping.")

        servers = _parse_servers(config.get("servers", []))
        capability_bindings = _parse_capabilities(config.get("capabilities", {}), servers)

        for server in servers.values():
            for tool in server.tools.values():
                for capability in tool.capabilities:
                    _add_capability_binding(capability_bindings, capability, server.name, tool.name)

        _validate_capability_bindings(capability_bindings, servers)
        return cls(servers, capability_bindings)

    @property
    def servers(self) -> Mapping[str, ServerSpec]:
        return dict(self._servers)

    def get_server(self, server_name: str) -> ServerSpec:
        server = self._servers.get(server_name)
        if server is None:
            raise MCPRegistryError(
                ErrorCode.SERVER_NOT_FOUND,
                "MCP server is not configured: %s" % server_name,
                server=server_name,
            )
        if not server.enabled:
            raise MCPRegistryError(
                ErrorCode.TOOL_NOT_ALLOWED,
                "MCP server is disabled: %s" % server_name,
                server=server_name,
            )
        return server

    def require_tool(self, server_name: str, tool_name: str) -> ToolSpec:
        server = self.get_server(server_name)
        tool = server.tools.get(tool_name)
        if tool is None:
            raise MCPRegistryError(
                ErrorCode.TOOL_NOT_ALLOWED,
                "MCP tool is not allowed for server %s: %s" % (server_name, tool_name),
                server=server_name,
                tool=tool_name,
            )
        if not tool.enabled:
            raise MCPRegistryError(
                ErrorCode.TOOL_NOT_ALLOWED,
                "MCP tool is disabled for server %s: %s" % (server_name, tool_name),
                server=server_name,
                tool=tool_name,
            )
        return tool

    def resolve_capability(self, capability: Union[Capability, str]) -> ToolBinding:
        capability_value = _capability_value(capability)
        binding = self._capability_bindings.get(capability_value)
        if binding is None:
            raise MCPRegistryError(
                ErrorCode.TOOL_NOT_ALLOWED,
                "No MCP tool configured for capability: %s" % capability_value,
                details={"capability": capability_value},
            )
        server_name, tool_name = binding
        self.require_tool(server_name, tool_name)
        return ToolBinding(
            capability=capability_value,
            server=server_name,
            tool=tool_name,
            timeout_s=self.timeout_for(server_name, tool_name),
        )

    def timeout_for(self, server_name: str, tool_name: str) -> float:
        server = self.get_server(server_name)
        tool = self.require_tool(server_name, tool_name)
        return tool.timeout_s if tool.timeout_s is not None else server.default_timeout_s

    def validate_tool_call(
        self,
        server_name: str,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> ToolSpec:
        tool = self.require_tool(server_name, tool_name)
        if not isinstance(arguments, Mapping):
            raise MCPRegistryError(
                ErrorCode.VALIDATION_ERROR,
                "MCP tool arguments must be a mapping.",
                server=server_name,
                tool=tool_name,
            )
        _assert_jsonable(arguments, "arguments", server_name, tool_name)
        _require_paths(arguments, tool.required_inputs, "arguments", server_name, tool_name)
        return tool

    def validate_tool_output(
        self,
        server_name: str,
        tool_name: str,
        output: Mapping[str, Any],
    ) -> None:
        tool = self.require_tool(server_name, tool_name)
        if not isinstance(output, Mapping):
            raise MCPRegistryError(
                ErrorCode.OUTPUT_VALIDATION_ERROR,
                "MCP tool output must be a mapping.",
                server=server_name,
                tool=tool_name,
            )
        _assert_jsonable(output, "output", server_name, tool_name, ErrorCode.OUTPUT_VALIDATION_ERROR)
        _require_paths(
            output,
            tool.required_outputs,
            "output",
            server_name,
            tool_name,
            ErrorCode.OUTPUT_VALIDATION_ERROR,
        )

    def redact_arguments(
        self,
        server_name: str,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Any:
        tool = self.require_tool(server_name, tool_name)
        return redact_value(arguments, tool.redact_inputs)

    def redact_output(
        self,
        server_name: str,
        tool_name: str,
        output: Mapping[str, Any],
    ) -> Any:
        tool = self.require_tool(server_name, tool_name)
        return redact_value(output, tool.redact_outputs)


def _parse_servers(raw_servers: Any) -> Dict[str, ServerSpec]:
    servers: Dict[str, ServerSpec] = {}
    for raw_server in _iter_named_configs(raw_servers, "server"):
        name = _required_name(raw_server, "server")
        if name in servers:
            raise MCPRegistryError(ErrorCode.INVALID_CONFIG, "Duplicate MCP server: %s" % name)

        default_timeout_s = _positive_float(
            raw_server.get("default_timeout_s", raw_server.get("timeout_s", DEFAULT_TIMEOUT_S)),
            "default_timeout_s",
            name,
        )
        tools = _parse_tools(name, raw_server.get("tools", []))
        servers[name] = ServerSpec(
            name=name,
            enabled=bool(raw_server.get("enabled", True)),
            transport=dict(raw_server.get("transport", {})),
            default_timeout_s=default_timeout_s,
            tools=tools,
        )

    return servers


def _parse_tools(server_name: str, raw_tools: Any) -> Dict[str, ToolSpec]:
    tools: Dict[str, ToolSpec] = {}
    for raw_tool in _iter_named_configs(raw_tools, "tool"):
        name = _required_name(raw_tool, "tool")
        if name in tools:
            raise MCPRegistryError(
                ErrorCode.INVALID_CONFIG,
                "Duplicate MCP tool for server %s: %s" % (server_name, name),
                server=server_name,
                tool=name,
            )

        allow = bool(raw_tool.get("allow", True))
        enabled = bool(raw_tool.get("enabled", True)) and allow
        timeout_s = raw_tool.get("timeout_s")
        capabilities = _string_tuple(raw_tool.get("capabilities", ()))
        if raw_tool.get("capability"):
            capabilities = capabilities + (_string(raw_tool["capability"], "capability"),)

        tools[name] = ToolSpec(
            name=name,
            server=server_name,
            enabled=enabled,
            timeout_s=_positive_float(timeout_s, "timeout_s", name) if timeout_s is not None else None,
            description=str(raw_tool.get("description", "")),
            capabilities=capabilities,
            required_inputs=_string_tuple(raw_tool.get("required_inputs", ())),
            required_outputs=_string_tuple(raw_tool.get("required_outputs", ())),
            redact_inputs=_string_tuple(raw_tool.get("redact_inputs", ())),
            redact_outputs=_string_tuple(raw_tool.get("redact_outputs", ())),
        )

    return tools


def _parse_capabilities(
    raw_capabilities: Any,
    servers: Mapping[str, ServerSpec],
) -> Dict[str, Tuple[str, str]]:
    capability_bindings: Dict[str, Tuple[str, str]] = {}
    if not raw_capabilities:
        return capability_bindings
    if not isinstance(raw_capabilities, Mapping):
        raise MCPRegistryError(ErrorCode.INVALID_CONFIG, "MCP capabilities config must be a mapping.")

    for capability, raw_binding in raw_capabilities.items():
        capability_value = _string(capability, "capability")
        server_name, tool_name = _parse_binding(raw_binding)
        _add_capability_binding(capability_bindings, capability_value, server_name, tool_name)

    _validate_capability_bindings(capability_bindings, servers)
    return capability_bindings


def _parse_binding(raw_binding: Any) -> Tuple[str, str]:
    if isinstance(raw_binding, str):
        parts = raw_binding.split(".")
        if len(parts) != 2 or not all(parts):
            raise MCPRegistryError(
                ErrorCode.INVALID_CONFIG,
                "String capability bindings must use 'server.tool' format.",
            )
        return parts[0], parts[1]

    if isinstance(raw_binding, Mapping):
        return (
            _string(raw_binding.get("server"), "capability server"),
            _string(raw_binding.get("tool"), "capability tool"),
        )

    raise MCPRegistryError(ErrorCode.INVALID_CONFIG, "Invalid MCP capability binding.")


def _add_capability_binding(
    capability_bindings: Dict[str, Tuple[str, str]],
    capability: str,
    server_name: str,
    tool_name: str,
) -> None:
    existing = capability_bindings.get(capability)
    if existing is not None and existing != (server_name, tool_name):
        raise MCPRegistryError(
            ErrorCode.INVALID_CONFIG,
            "MCP capability is bound to multiple tools: %s" % capability,
            details={"capability": capability, "existing": existing, "new": (server_name, tool_name)},
        )
    capability_bindings[capability] = (server_name, tool_name)


def _validate_capability_bindings(
    capability_bindings: Mapping[str, Tuple[str, str]],
    servers: Mapping[str, ServerSpec],
) -> None:
    for capability, binding in capability_bindings.items():
        server_name, tool_name = binding
        server = servers.get(server_name)
        if server is None:
            raise MCPRegistryError(
                ErrorCode.INVALID_CONFIG,
                "Capability %s references unknown MCP server: %s" % (capability, server_name),
                server=server_name,
                tool=tool_name,
            )
        tool = server.tools.get(tool_name)
        if tool is None:
            raise MCPRegistryError(
                ErrorCode.INVALID_CONFIG,
                "Capability %s references unknown MCP tool: %s.%s" % (capability, server_name, tool_name),
                server=server_name,
                tool=tool_name,
            )
        if not server.enabled or not tool.enabled:
            raise MCPRegistryError(
                ErrorCode.INVALID_CONFIG,
                "Capability %s references a disabled MCP tool: %s.%s" % (capability, server_name, tool_name),
                server=server_name,
                tool=tool_name,
            )


def _iter_named_configs(raw_value: Any, item_name: str) -> Iterable[Mapping[str, Any]]:
    if raw_value is None:
        return ()

    if isinstance(raw_value, Mapping):
        configs: List[Mapping[str, Any]] = []
        for name, value in raw_value.items():
            if not isinstance(value, Mapping):
                raise MCPRegistryError(ErrorCode.INVALID_CONFIG, "MCP %s config must be a mapping." % item_name)
            config = dict(value)
            config.setdefault("name", name)
            configs.append(config)
        return tuple(configs)

    if isinstance(raw_value, Sequence) and not isinstance(raw_value, (str, bytes, bytearray)):
        for item in raw_value:
            if not isinstance(item, Mapping):
                raise MCPRegistryError(ErrorCode.INVALID_CONFIG, "MCP %s config must be a mapping." % item_name)
        return tuple(raw_value)

    raise MCPRegistryError(ErrorCode.INVALID_CONFIG, "MCP %ss config must be a list or mapping." % item_name)


def _required_name(config: Mapping[str, Any], item_name: str) -> str:
    return _string(config.get("name"), "%s name" % item_name)


def _string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MCPRegistryError(ErrorCode.INVALID_CONFIG, "MCP %s must be a non-empty string." % field_name)
    return value.strip()


def _string_tuple(value: Any) -> Tuple[str, ...]:
    if value in (None, ""):
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise MCPRegistryError(ErrorCode.INVALID_CONFIG, "Expected a string or list of strings.")
    return tuple(_string(item, "list item") for item in value)


def _positive_float(value: Any, field_name: str, owner: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise MCPRegistryError(
            ErrorCode.INVALID_CONFIG,
            "MCP %s for %s must be a positive number." % (field_name, owner),
        ) from exc
    if parsed <= 0:
        raise MCPRegistryError(
            ErrorCode.INVALID_CONFIG,
            "MCP %s for %s must be a positive number." % (field_name, owner),
        )
    return parsed


def _capability_value(capability: Union[Capability, str]) -> str:
    if isinstance(capability, Capability):
        return capability.value
    return _string(capability, "capability")


def _assert_jsonable(
    value: Mapping[str, Any],
    label: str,
    server_name: str,
    tool_name: str,
    code: ErrorCode = ErrorCode.VALIDATION_ERROR,
) -> None:
    try:
        json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise MCPRegistryError(
            code,
            "MCP tool %s must be JSON-serializable." % label,
            server=server_name,
            tool=tool_name,
        ) from exc


def _require_paths(
    value: Mapping[str, Any],
    paths: Sequence[str],
    label: str,
    server_name: str,
    tool_name: str,
    code: ErrorCode = ErrorCode.VALIDATION_ERROR,
) -> None:
    missing = [path for path in paths if not _has_path(value, path)]
    if missing:
        raise MCPRegistryError(
            code,
            "MCP tool %s missing required %s fields: %s" % (tool_name, label, ", ".join(missing)),
            server=server_name,
            tool=tool_name,
            details={"missing": missing},
        )


def _has_path(value: Any, path: str) -> bool:
    parts = tuple(part for part in path.split(".") if part)
    if not parts:
        return True
    return _has_path_parts(value, parts)


def _has_path_parts(value: Any, parts: Tuple[str, ...]) -> bool:
    if not parts:
        return True

    current, rest = parts[0], parts[1:]
    if isinstance(value, Mapping):
        if current == "*":
            return any(_has_path_parts(item, rest) for item in value.values())
        return current in value and _has_path_parts(value[current], rest)

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if current == "*":
            return any(_has_path_parts(item, rest) for item in value)
        try:
            index = int(current)
        except ValueError:
            return False
        return 0 <= index < len(value) and _has_path_parts(value[index], rest)

    return False
