"""Memory and report handoff specialist agent."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .types import (
    AgentResult,
    JsonDict,
    MemoryStore,
    ReportSink,
    error_entry,
    get_resource,
    log_entry,
)


class MemoryReportHandoffAgent:
    """Hand off audited run data to injected memory and reporting boundaries."""

    stage = "handoff"

    def __init__(
        self,
        *,
        memory_store: MemoryStore | None = None,
        report_sink: ReportSink | None = None,
    ) -> None:
        self.memory_store = memory_store
        self.report_sink = report_sink

    def run(
        self,
        *,
        run_id: str,
        ranked_items: Sequence[Mapping[str, Any]],
        learning_plan: Sequence[Mapping[str, Any]],
        calendar_events: Sequence[Mapping[str, Any]],
        errors: Sequence[Mapping[str, Any]],
    ) -> AgentResult:
        result = AgentResult()
        memory_records = _memory_records(ranked_items, calendar_events)
        report = _report(run_id, ranked_items, learning_plan, calendar_events, errors)

        if self.memory_store is None:
            result.log.append(
                log_entry(self.stage, "memory_skipped", "No memory store dependency was provided")
            )
        else:
            try:
                write_result = self.memory_store.write_records(run_id, memory_records)
            except Exception as exc:  # pragma: no cover - store-specific exact failure.
                result.errors.append(
                    error_entry(
                        self.stage,
                        "Memory write failed",
                        code="memory_write_failed",
                        error_type=exc.__class__.__name__,
                        error=str(exc),
                    )
                )
            else:
                result.items.append({"type": "memory", "result": dict(write_result)})
                result.side_effects.append(
                    {
                        "type": "memory_write",
                        "status": str(write_result.get("status") or "written"),
                        "records": len(memory_records),
                    }
                )
                result.log.append(
                    log_entry(
                        self.stage,
                        "memory_written",
                        "Memory records handed off",
                        records=len(memory_records),
                    )
                )

        if self.report_sink is None:
            result.log.append(
                log_entry(self.stage, "report_skipped", "No report sink dependency was provided")
            )
        else:
            try:
                report_result = self.report_sink.write_run_report(run_id, report)
            except Exception as exc:  # pragma: no cover - sink-specific exact failure.
                result.errors.append(
                    error_entry(
                        self.stage,
                        "Report write failed",
                        code="report_write_failed",
                        error_type=exc.__class__.__name__,
                        error=str(exc),
                    )
                )
            else:
                result.items.append({"type": "report", "result": dict(report_result)})
                result.side_effects.append(
                    {
                        "type": "report_write",
                        "status": str(report_result.get("status") or "written"),
                        "artifact": report_result.get("artifact") or report_result.get("path") or "",
                    }
                )
                result.log.append(log_entry(self.stage, "report_written", "Run report handed off"))

        return result


def _memory_records(
    ranked_items: Sequence[Mapping[str, Any]],
    calendar_events: Sequence[Mapping[str, Any]],
) -> list[JsonDict]:
    calendar_by_resource = {
        str(event.get("resource_id")): event for event in calendar_events if event.get("resource_id")
    }
    records: list[JsonDict] = []
    for item in ranked_items:
        resource = get_resource(item)
        event = calendar_by_resource.get(str(resource["id"]), {})
        records.append(
            {
                "resource_id": resource["id"],
                "title": resource.get("title"),
                "url": resource.get("url", ""),
                "source": resource.get("source"),
                "score": item.get("score"),
                "rank": item.get("rank"),
                "calendar_status": event.get("status", "not_scheduled"),
                "calendar_event_id": event.get("event_id", ""),
            }
        )
    return records


def _report(
    run_id: str,
    ranked_items: Sequence[Mapping[str, Any]],
    learning_plan: Sequence[Mapping[str, Any]],
    calendar_events: Sequence[Mapping[str, Any]],
    errors: Sequence[Mapping[str, Any]],
) -> JsonDict:
    return {
        "run_id": run_id,
        "ranked_count": len(ranked_items),
        "planned_count": len(learning_plan),
        "calendar_event_count": len(calendar_events),
        "error_count": len(errors),
        "ranked_resources": [
            {
                "resource_id": get_resource(item)["id"],
                "title": get_resource(item).get("title"),
                "score": item.get("score"),
                "rank": item.get("rank"),
            }
            for item in ranked_items
        ],
        "calendar_events": [dict(event) for event in calendar_events],
        "errors": [dict(error) for error in errors],
    }
