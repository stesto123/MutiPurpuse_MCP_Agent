from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


class ReportWriter:
    def __init__(self, reports_dir: Path, runs_dir: Path):
        self.reports_dir = reports_dir
        self.runs_dir = runs_dir
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def write(self, run_id: str, state: Mapping[str, Any]) -> Dict[str, Path]:
        markdown_path = self.reports_dir / f"{run_id}.md"
        json_path = self.runs_dir / f"{run_id}.json"
        markdown_path.write_text(render_markdown_report(run_id, state), encoding="utf-8")
        json_path.write_text(
            json.dumps(_json_safe(state), ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return {"markdown": markdown_path, "json": json_path}

    def write_run_report(self, run_id: str, report: Mapping[str, Any]) -> Mapping[str, Any]:
        written = self.write(run_id, report)
        return {
            "status": "written",
            "artifact": str(written["markdown"]),
            "markdown": str(written["markdown"]),
            "json": str(written["json"]),
        }


def write_run_reports(
    reports_dir: Path,
    runs_dir: Path,
    run_id: str,
    state: Mapping[str, Any],
) -> Dict[str, Path]:
    return ReportWriter(reports_dir=reports_dir, runs_dir=runs_dir).write(run_id, state)


def render_markdown_report(run_id: str, state: Mapping[str, Any]) -> str:
    created_at = datetime.now(timezone.utc).isoformat()
    lines = [
        f"# AI Scout Run {run_id}",
        "",
        f"- Created: `{created_at}`",
        f"- Mode: `{state.get('mode', 'unknown')}`",
        f"- Status: `{state.get('status', 'unknown')}`",
        "",
    ]
    errors = state.get("errors") or []
    if errors:
        lines.extend(["## Errors", ""])
        for error in _as_iterable(errors):
            lines.append(f"- {error}")
        lines.append("")

    selected = (
        state.get("selected_resources")
        or state.get("ranked_resources")
        or state.get("ranked")
        or []
    )
    if selected:
        lines.extend(["## Selected Resources", ""])
        for index, resource in enumerate(_as_iterable(selected), start=1):
            resource_map = _to_mapping(resource)
            title = _resource_title(resource_map)
            url = _resource_url(resource_map)
            score = resource_map.get("score") or resource_map.get("final_score")
            score_text = f" score={score}" if score is not None else ""
            lines.append(f"{index}. {title}{score_text}")
            if url:
                lines.append(f"   {url}")
        lines.append("")

    activities = (
        state.get("planned_activities")
        or state.get("activities")
        or state.get("learning_plan")
        or []
    )
    if activities:
        lines.extend(["## Planned Activities", ""])
        for activity in _as_iterable(activities):
            activity_map = _to_mapping(activity)
            title = activity_map.get("title") or activity_map.get("summary") or "Activity"
            duration = activity_map.get("duration_minutes")
            duration_text = f" ({duration} min)" if duration else ""
            lines.append(f"- {title}{duration_text}")
        lines.append("")

    events = state.get("calendar_events") or state.get("created_events") or []
    if events:
        lines.extend(["## Calendar Side Effects", ""])
        for event in _as_iterable(events):
            event_map = _to_mapping(event)
            title = event_map.get("title") or event_map.get("summary") or "Calendar event"
            status = event_map.get("status") or "planned"
            lines.append(f"- `{status}` {title}")
        lines.append("")

    audit = state.get("audit") or {}
    if audit:
        lines.extend(["## Audit", "", "```json"])
        lines.append(json.dumps(_json_safe(audit), ensure_ascii=True, indent=2, sort_keys=True))
        lines.extend(["```", ""])

    return "\n".join(lines)


def _as_iterable(value: Any) -> Iterable[Any]:
    if isinstance(value, (str, bytes)):
        return [value]
    try:
        return list(value)
    except TypeError:
        return [value]


def _to_mapping(value: Any) -> Mapping[str, Any]:
    if is_dataclass(value):
        return asdict(value)  # type: ignore[arg-type]
    if isinstance(value, Mapping):
        return value
    return {"value": value}


def _resource_title(resource_map: Mapping[str, Any]) -> str:
    nested_resource = _to_mapping(resource_map.get("resource") or {})
    return str(
        resource_map.get("title")
        or resource_map.get("name")
        or nested_resource.get("title")
        or nested_resource.get("name")
        or "Untitled"
    )


def _resource_url(resource_map: Mapping[str, Any]) -> str:
    nested_resource = _to_mapping(resource_map.get("resource") or {})
    return str(resource_map.get("url") or nested_resource.get("url") or "")


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return _json_safe(asdict(value))  # type: ignore[arg-type]
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value
