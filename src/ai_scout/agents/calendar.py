"""Calendar execution specialist agent."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .base import call_tool_with_retries
from .types import AgentResult, JsonDict, MCPGateway, RetryPolicy, error_entry, log_entry, stable_id


class CalendarExecutionAgent:
    """Read availability and request idempotent calendar event side effects via MCP."""

    availability_stage = "calendar_availability"
    execution_stage = "calendar_execution"

    def __init__(
        self,
        gateway: MCPGateway,
        retry_policy: RetryPolicy | None = None,
        *,
        availability_tool: str = "calendar.read_availability",
        create_event_tool: str = "calendar.create_event",
    ) -> None:
        self.gateway = gateway
        self.retry_policy = retry_policy or RetryPolicy()
        self.availability_tool = availability_tool
        self.create_event_tool = create_event_tool

    def read_availability(self, request: Mapping[str, Any] | None = None) -> AgentResult:
        request = request or {}
        tool_name = str(request.get("tool_name") or self.availability_tool)
        arguments = dict(request.get("arguments") or {})
        if "run_id" in request:
            arguments.setdefault("run_id", request["run_id"])

        result = AgentResult()
        response, log, errors = call_tool_with_retries(
            self.gateway,
            tool_name=tool_name,
            arguments=arguments,
            stage=self.availability_stage,
            retry_policy=self.retry_policy,
        )
        result.log.extend(log)
        result.errors.extend(errors)

        if response is not None:
            slots = response.get("slots") or response.get("availability") or []
            if isinstance(slots, Sequence) and not isinstance(slots, (str, bytes)):
                result.items.extend(dict(slot) for slot in slots if isinstance(slot, Mapping))
            else:
                result.errors.append(
                    error_entry(
                        self.availability_stage,
                        "Availability response did not contain a list of slots",
                        code="invalid_availability_response",
                    )
                )

        result.log.append(
            log_entry(
                self.availability_stage,
                "availability_read",
                "Calendar availability read completed",
                slots=len(result.items),
            )
        )
        return result

    def write_events(
        self,
        activities: Sequence[Mapping[str, Any]],
        availability_slots: Sequence[Mapping[str, Any]],
        request: Mapping[str, Any] | None = None,
    ) -> AgentResult:
        request = request or {}
        tool_name = str(request.get("tool_name") or self.create_event_tool)
        run_id = str(request.get("run_id") or "manual-run")
        result = AgentResult()

        for index, activity in enumerate(activities):
            slot = dict(availability_slots[index]) if index < len(availability_slots) else {}
            idempotency_key = stable_id("calendar", run_id, activity.get("id"), activity.get("resource_id"))
            if not slot:
                result.items.append(
                    {
                        "activity_id": activity.get("id"),
                        "resource_id": activity.get("resource_id"),
                        "status": "skipped_no_availability",
                        "idempotency_key": idempotency_key,
                    }
                )
                result.log.append(
                    log_entry(
                        self.execution_stage,
                        "event_skipped",
                        "Calendar event skipped because no availability slot was present",
                        activity_id=activity.get("id"),
                    )
                )
                continue

            event_request = _event_request(activity, slot, run_id, idempotency_key)
            response, log, errors = call_tool_with_retries(
                self.gateway,
                tool_name=tool_name,
                arguments=event_request,
                stage=self.execution_stage,
                retry_policy=self.retry_policy,
            )
            result.log.extend(log)
            result.errors.extend(errors)

            if response is None:
                result.items.append(
                    {
                        "activity_id": activity.get("id"),
                        "resource_id": activity.get("resource_id"),
                        "status": "failed",
                        "idempotency_key": idempotency_key,
                    }
                )
                continue

            event_result: JsonDict = {
                "activity_id": activity.get("id"),
                "resource_id": activity.get("resource_id"),
                "status": str(response.get("status") or "created"),
                "event_id": str(response.get("event_id") or response.get("id") or ""),
                "idempotency_key": idempotency_key,
                "start": event_request.get("start"),
                "end": event_request.get("end"),
            }
            result.items.append(event_result)
            result.side_effects.append(
                {
                    "type": "calendar_event",
                    "status": event_result["status"],
                    "idempotency_key": idempotency_key,
                    "resource_id": activity.get("resource_id"),
                    "event_id": event_result["event_id"],
                }
            )

        result.log.append(
            log_entry(
                self.execution_stage,
                "calendar_events_written",
                "Calendar event write requests completed",
                count=len(result.items),
                side_effects=len(result.side_effects),
            )
        )
        return result


def _event_request(
    activity: Mapping[str, Any],
    slot: Mapping[str, Any],
    run_id: str,
    idempotency_key: str,
) -> JsonDict:
    return {
        "run_id": run_id,
        "idempotency_key": idempotency_key,
        "activity_id": activity.get("id"),
        "resource_id": activity.get("resource_id"),
        "title": activity.get("title"),
        "description": activity.get("description", ""),
        "duration_minutes": activity.get("duration_minutes"),
        "start": slot.get("start"),
        "end": slot.get("end"),
        "metadata": dict(activity.get("metadata") or {}),
    }
