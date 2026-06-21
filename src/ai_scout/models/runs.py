from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from hashlib import sha256


class RunStatus(str, Enum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


def make_run_id(started_at: datetime, label: str = "local") -> str:
    payload = f"{label}:{started_at.isoformat()}"
    return "run_" + sha256(payload.encode("utf-8")).hexdigest()[:20]


def _clean_text_tuple(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    cleaned_values: list[str] = []
    for value in values:
        cleaned = " ".join(value.strip().split())
        if cleaned and cleaned not in seen:
            cleaned_values.append(cleaned)
            seen.add(cleaned)
    return tuple(cleaned_values)


@dataclass(frozen=True)
class ScoutRun:
    """Auditable summary state for one local scout execution."""

    started_at: datetime
    run_id: str | None = None
    status: RunStatus = RunStatus.STARTED
    finished_at: datetime | None = None
    candidate_count: int = 0
    selected_resource_ids: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("finished_at cannot be before started_at")
        if self.candidate_count < 0:
            raise ValueError("candidate_count cannot be negative")

        status = self.status if isinstance(self.status, RunStatus) else RunStatus(str(self.status))
        run_id = self.run_id
        if run_id is None:
            run_id = make_run_id(self.started_at)
        else:
            run_id = " ".join(run_id.strip().split())
            if not run_id:
                raise ValueError("run_id cannot be empty")

        object.__setattr__(self, "run_id", run_id)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "selected_resource_ids", _clean_text_tuple(self.selected_resource_ids))
        object.__setattr__(self, "notes", _clean_text_tuple(self.notes))
