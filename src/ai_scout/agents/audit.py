"""Audit specialist agent."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .types import AgentResult, JsonDict, log_entry


class AuditAgent:
    """Verify the first autonomous phase stayed observable and policy-safe."""

    stage = "audit"

    def run(
        self,
        *,
        deduplicated_items: Sequence[Mapping[str, Any]],
        calendar_events: Sequence[Mapping[str, Any]],
        side_effects: Sequence[Mapping[str, Any]],
        errors: Sequence[Mapping[str, Any]],
        log: Sequence[Mapping[str, Any]],
    ) -> AgentResult:
        result = AgentResult()
        duplicate_ids = {
            str(item.get("resource_id"))
            for item in deduplicated_items
            if item.get("is_duplicate") and item.get("resource_id")
        }
        scheduled_duplicate_ids = {
            str(event.get("resource_id"))
            for event in calendar_events
            if event.get("resource_id") in duplicate_ids and event.get("status") != "skipped_no_availability"
        }
        idempotency_keys = [
            str(effect.get("idempotency_key"))
            for effect in side_effects
            if effect.get("idempotency_key")
        ]
        duplicate_side_effect_keys = sorted(
            key for key in set(idempotency_keys) if idempotency_keys.count(key) > 1
        )
        failed_events = [event for event in calendar_events if event.get("status") == "failed"]
        checks = [
            {
                "name": "no_duplicate_calendar_events",
                "passed": not scheduled_duplicate_ids,
                "details": {"resource_ids": sorted(scheduled_duplicate_ids)},
            },
            {
                "name": "idempotent_side_effects",
                "passed": not duplicate_side_effect_keys,
                "details": {"duplicate_keys": duplicate_side_effect_keys},
            },
            {
                "name": "side_effects_logged",
                "passed": all(effect.get("type") and effect.get("status") for effect in side_effects)
                and (not side_effects or bool(log)),
                "details": {"side_effects": len(side_effects), "log_entries": len(log)},
            },
            {
                "name": "calendar_failures_explicit",
                "passed": all(event.get("idempotency_key") for event in failed_events),
                "details": {"failed_events": len(failed_events)},
            },
        ]
        passed = all(check["passed"] for check in checks)
        status = "passed" if passed and not errors else "passed_with_warnings" if passed else "failed"
        audit: JsonDict = {
            "status": status,
            "checks": checks,
            "error_count": len(errors),
            "side_effect_count": len(side_effects),
        }
        result.items.append(audit)
        result.log.append(
            log_entry(
                self.stage,
                "run_audited",
                "Audit completed",
                status=status,
                checks=len(checks),
                errors=len(errors),
            )
        )
        return result
