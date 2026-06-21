from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set


class MemoryStoreError(RuntimeError):
    """Raised when local memory cannot be read or written."""


class JsonlMemoryStore:
    """Append-only JSONL memory for phase 1.

    This deliberately keeps the first implementation transparent and easy to
    audit. SQLite can replace it later without changing the higher-level graph
    contracts.
    """

    def __init__(self, memory_dir: Path):
        self.memory_dir = memory_dir
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    @property
    def resources_path(self) -> Path:
        return self.memory_dir / "resources.jsonl"

    @property
    def events_path(self) -> Path:
        return self.memory_dir / "calendar_events.jsonl"

    @property
    def runs_path(self) -> Path:
        return self.memory_dir / "runs.jsonl"

    def append_resource(self, record: Mapping[str, Any]) -> None:
        self._append(self.resources_path, record)

    def append_event(self, record: Mapping[str, Any]) -> None:
        self._append(self.events_path, record)

    def append_run(self, record: Mapping[str, Any]) -> None:
        self._append(self.runs_path, record)

    def seen_resource_keys(self) -> Set[str]:
        keys: Set[str] = set()
        for record in self.iter_jsonl(self.resources_path):
            for key_name in ("id", "dedupe_key", "url"):
                value = record.get(key_name)
                if value:
                    keys.add(str(value))
        return keys

    def created_calendar_event_ids(self) -> Set[str]:
        ids: Set[str] = set()
        for record in self.iter_jsonl(self.events_path):
            event_id = record.get("calendar_event_id") or record.get("id")
            if event_id:
                ids.add(str(event_id))
        return ids

    def load_snapshot(self, run_id: str) -> Mapping[str, Any]:
        """Return the memory shape expected by graph specialist agents."""

        del run_id
        resources = list(self.iter_jsonl(self.resources_path))
        return {
            "seen_resource_ids": [
                str(record["resource_id"])
                for record in resources
                if record.get("resource_id")
            ],
            "seen_urls": [str(record["url"]) for record in resources if record.get("url")],
            "seen_fingerprints": [
                str(record["dedupe_key"])
                for record in resources
                if record.get("dedupe_key")
            ],
        }

    def write_records(
        self,
        run_id: str,
        records: Iterable[Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        count = 0
        for record in records:
            payload = dict(record)
            payload.setdefault("run_id", run_id)
            self.append_resource(payload)
            if payload.get("calendar_event_id"):
                self.append_event(payload)
            count += 1
        return {"status": "written", "count": count}

    def iter_jsonl(self, path: Path) -> Iterable[Dict[str, Any]]:
        if not path.exists():
            return []
        rows: List[Dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        loaded = json.loads(stripped)
                    except json.JSONDecodeError as exc:
                        raise MemoryStoreError(
                            f"Invalid JSONL in {path} at line {line_number}: {exc}"
                        ) from exc
                    if isinstance(loaded, dict):
                        rows.append(loaded)
            return rows
        except OSError as exc:
            raise MemoryStoreError(f"Unable to read memory file {path}: {exc}") from exc

    def _append(self, path: Path, record: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _json_safe_record(record)
        payload.setdefault("recorded_at", datetime.now(timezone.utc).isoformat())
        try:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=True, sort_keys=True))
                handle.write("\n")
        except OSError as exc:
            raise MemoryStoreError(f"Unable to append memory file {path}: {exc}") from exc


def _json_safe_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    return {str(key): _json_safe_value(value) for key, value in record.items()}


def _json_safe_value(value: Any) -> Any:
    if is_dataclass(value):
        return _json_safe_value(asdict(value))  # type: ignore[arg-type]
    if isinstance(value, Mapping):
        return {str(k): _json_safe_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value


def stable_run_id(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    return current.strftime("%Y%m%dT%H%M%SZ")


class PolicyMemoryStore:
    """Read/write policy wrapper for graph memory handoff."""

    def __init__(self, store: JsonlMemoryStore, *, allow_writes: bool) -> None:
        self.store = store
        self.allow_writes = allow_writes

    def load_snapshot(self, run_id: str) -> Mapping[str, Any]:
        return self.store.load_snapshot(run_id)

    def write_records(
        self,
        run_id: str,
        records: Iterable[Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        materialized = list(records)
        if not self.allow_writes:
            return {
                "status": "dry_run_skipped",
                "count": 0,
                "would_write_count": len(materialized),
            }
        return self.store.write_records(run_id, materialized)
