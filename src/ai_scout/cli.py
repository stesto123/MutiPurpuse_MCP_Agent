from __future__ import annotations

import argparse
import json
import logging
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ai_scout.config import RuntimePaths, default_runtime_paths, load_app_config
from ai_scout.memory import JsonlMemoryStore, PolicyMemoryStore, stable_run_id
from ai_scout.observability import configure_logging
from ai_scout.reporting import ReportWriter

LOG = logging.getLogger(__name__)


def main(argv: list | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level)

    if args.command == "init-local":
        return init_local(args)
    if args.command == "run":
        return run_once(args)
    if args.command == "show-paths":
        return show_paths(args)
    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-scout",
        description="Local-first autonomous AI technology scouting agent.",
    )
    parser.add_argument("--log-level", default="INFO", help="Python logging level.")
    subcommands = parser.add_subparsers(dest="command")

    run = subcommands.add_parser("run", help="Run one AI Scout cycle.")
    run.add_argument(
        "--mode",
        choices=["observe", "dry_run", "assist", "autonomous"],
        default=None,
        help="Override configured operating mode.",
    )
    run.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help="Directory containing local profile.yaml, policy.yaml, sources.yaml, mcp.yaml.",
    )
    run.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Directory for local memory, run JSON, and reports.",
    )

    init = subcommands.add_parser("init-local", help="Create local config/data directories.")
    init.add_argument("--config-dir", type=Path, default=None)
    init.add_argument("--data-dir", type=Path, default=None)

    paths = subcommands.add_parser("show-paths", help="Print resolved local paths.")
    paths.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser


def init_local(args: argparse.Namespace) -> int:
    paths = _runtime_paths(args.config_dir, args.data_dir)
    paths.ensure()
    print(f"Config directory: {paths.config_dir}")
    print(f"Data directory: {paths.data_dir}")
    print("Create local profile.yaml, policy.yaml, sources.yaml, and mcp.yaml there.")
    return 0


def show_paths(args: argparse.Namespace) -> int:
    paths = default_runtime_paths()
    payload = {
        "config_dir": str(paths.config_dir),
        "data_dir": str(paths.data_dir),
        "memory_dir": str(paths.memory_dir),
        "reports_dir": str(paths.reports_dir),
        "runs_dir": str(paths.runs_dir),
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")
    return 0


def run_once(args: argparse.Namespace) -> int:
    paths = _runtime_paths(args.config_dir, args.data_dir)
    paths.ensure()
    config = load_app_config(paths.config_dir, mode=args.mode, allow_missing=True)
    _assert_autonomous_confirmation(config.raw.get("policy", {}), config.mode)
    run_id = stable_run_id()
    base_memory = JsonlMemoryStore(paths.memory_dir)
    memory = PolicyMemoryStore(
        base_memory,
        allow_writes=_memory_writes_allowed(config.raw.get("policy", {}), config.mode),
    )
    reporter = ReportWriter(paths.reports_dir, paths.runs_dir)

    try:
        from ai_scout.graph.runner import run_ai_scout
    except ImportError as exc:
        raise RuntimeError("Graph runner is not available") from exc

    LOG.info("Starting AI Scout run %s in mode=%s", run_id, config.mode)
    state = run_ai_scout(
        config=config,
        run_id=run_id,
        memory=memory,
    )
    state_map = _to_mapping(state)
    state_map.setdefault("mode", config.mode)
    state_map.setdefault("run_id", run_id)
    state_map.setdefault("status", "completed")
    if _memory_writes_allowed(config.raw.get("policy", {}), config.mode):
        base_memory.append_run({"run_id": run_id, "mode": config.mode, "status": state_map["status"]})
    paths_written = reporter.write(run_id, state_map)
    print(f"Run ID: {run_id}")
    print(f"Markdown report: {paths_written['markdown']}")
    print(f"Run JSON: {paths_written['json']}")
    return 0


def _runtime_paths(config_dir: Path | None, data_dir: Path | None) -> RuntimePaths:
    paths = default_runtime_paths()
    if config_dir is None and data_dir is None:
        return paths
    return type(paths)(
        config_dir=(config_dir or paths.config_dir).expanduser(),
        data_dir=(data_dir or paths.data_dir).expanduser(),
    )


def _to_mapping(value: Any) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, Mapping):
        return dict(value)
    return {"result": value}


def _memory_writes_allowed(policy: Mapping[str, Any], mode: str) -> bool:
    permissions = policy.get("permissions")
    if isinstance(permissions, Mapping):
        mode_permissions = permissions.get(mode)
        if isinstance(mode_permissions, Mapping):
            return bool(mode_permissions.get("local_memory_writes", mode == "autonomous"))
    return mode == "autonomous"


def _assert_autonomous_confirmation(policy: Mapping[str, Any], mode: str) -> None:
    if mode != "autonomous":
        return
    autonomy = policy.get("autonomy")
    require_confirmation = True
    env_var = "AI_SCOUT_AUTONOMOUS_CONFIRM"
    expected_value = "I_UNDERSTAND_AUTONOMOUS_SIDE_EFFECTS"
    if isinstance(autonomy, Mapping):
        require_confirmation = bool(
            autonomy.get("require_explicit_autonomous_confirmation", True)
        )
        env_var = str(autonomy.get("confirmation_env_var") or env_var)
        expected_value = str(autonomy.get("confirmation_value") or expected_value)
    if require_confirmation and os.environ.get(env_var) != expected_value:
        raise RuntimeError(
            "Autonomous mode requires explicit confirmation. "
            f"Set {env_var}={expected_value!r} in your local environment."
        )
