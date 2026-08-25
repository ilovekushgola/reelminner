"""Typed Job domain model for Reelminner Phase 2.

This module is pure domain logic. It depends only on the standard library so it
can be imported by the persistence layer, the JobManager, and (eventually) the
desktop UI without pulling in the scraping engine.

The engine (``scraper.py`` / ``service.py``) remains the source of truth for
*scraping*. A ``Job`` only describes *orchestration* state.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from proxies import NetworkMode


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return "job_" + uuid.uuid4().hex[:12]


class JobStatus(str, Enum):
    """Explicit lifecycle states for a scrape job."""

    CREATED = "created"
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"

    @classmethod
    def terminal_states(cls) -> frozenset["JobStatus"]:
        return frozenset(
            {cls.COMPLETED, cls.FAILED, cls.STOPPED, cls.INTERRUPTED}
        )


# Legal transitions. Any transition not listed here is rejected.
LEGAL_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.CREATED: frozenset({JobStatus.QUEUED, JobStatus.STARTING}),
    JobStatus.QUEUED: frozenset({JobStatus.STARTING, JobStatus.STOPPED}),
    JobStatus.STARTING: frozenset(
        {JobStatus.RUNNING, JobStatus.STOPPED, JobStatus.FAILED}
    ),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.PAUSED,
            JobStatus.STOPPED,
            JobStatus.COMPLETED,
            JobStatus.FAILED,
        }
    ),
    JobStatus.PAUSED: frozenset(
        {JobStatus.RUNNING, JobStatus.STOPPED, JobStatus.FAILED}
    ),
    JobStatus.STOPPED: frozenset({JobStatus.CREATED}),
    JobStatus.COMPLETED: frozenset(),
    JobStatus.FAILED: frozenset({JobStatus.CREATED}),
    JobStatus.INTERRUPTED: frozenset({JobStatus.CREATED}),
}


class IllegalTransitionError(Exception):
    """Raised when a job is moved to a state it cannot legally enter."""


@dataclass
class JobConfig:
    """Configuration captured when a job is created / resumed."""

    urls: list[str] = field(default_factory=list)
    workers: int = 3
    delay: float = 2.0
    headless: bool = False
    with_profiles: bool = True
    # URLs not yet processed. Used as the resume cursor after a pause/crash.
    pending_urls: list[str] = field(default_factory=list)
    # Phase 3.5: network mode + fixed proxy selection.
    network_mode: NetworkMode = NetworkMode.DIRECT
    proxy_id: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "urls": self.urls,
                "workers": self.workers,
                "delay": self.delay,
                "headless": self.headless,
                "with_profiles": self.with_profiles,
                "pending_urls": self.pending_urls,
                "network_mode": self.network_mode.value,
                "proxy_id": self.proxy_id,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, text: str) -> "JobConfig":
        if not text:
            return cls()
        data = json.loads(text)
        raw_mode = data.get("network_mode", NetworkMode.DIRECT.value)
        try:
            network_mode = NetworkMode(str(raw_mode))
        except ValueError:
            network_mode = NetworkMode.DIRECT
        return cls(
            urls=list(data.get("urls", [])),
            workers=int(data.get("workers", 3)),
            delay=float(data.get("delay", 2.0)),
            headless=bool(data.get("headless", False)),
            with_profiles=bool(data.get("with_profiles", True)),
            pending_urls=list(data.get("pending_urls", [])),
            network_mode=network_mode,
            proxy_id=data.get("proxy_id"),
        )


@dataclass
class Job:
    """A single scrape job and its lifecycle / statistics."""

    id: str = field(default_factory=_new_id)
    created_at: str = field(default_factory=_now_iso)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    updated_at: str = field(default_factory=_now_iso)
    status: JobStatus = JobStatus.CREATED
    config: JobConfig = field(default_factory=JobConfig)
    session_id: Optional[str] = None

    total_items: int = 0
    processed_items: int = 0
    successful_items: int = 0
    failed_items: int = 0
    blocked_items: int = 0
    rate_limited_items: int = 0

    result_location: Optional[str] = None
    error_summary: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def is_terminal(self) -> bool:
        return self.status in JobStatus.terminal_states()

    def can_transition_to(self, new: JobStatus) -> bool:
        return new in LEGAL_TRANSITIONS.get(self.status, frozenset())

    def transition_to(self, new: JobStatus) -> None:
        if new == self.status:
            return
        if not self.can_transition_to(new):
            raise IllegalTransitionError(
                f"Illegal transition: {self.status.value} -> {new.value}"
            )
        self.status = new
        now = _now_iso()
        self.updated_at = now
        if new in (JobStatus.RUNNING,) and self.started_at is None:
            self.started_at = now
        if new in JobStatus.terminal_states() and self.completed_at is None:
            self.completed_at = now

    # ------------------------------------------------------------------ #
    # Statistics
    # ------------------------------------------------------------------ #
    def record_result(self, status: str) -> None:
        """Update running counters from one reel's scrape status."""
        self.processed_items += 1
        self.total_items = max(self.total_items, self.processed_items)
        s = (status or "ok").lower()
        if s == "ok":
            self.successful_items += 1
        elif "rate_limited" in s:
            self.rate_limited_items += 1
        elif s in ("session_expired", "unavailable", "error: structure_change"):
            # Instagram blocked the reel / page structure broke.
            self.blocked_items += 1
        else:
            self.failed_items += 1

    def reset_stats(self) -> None:
        self.total_items = 0
        self.processed_items = 0
        self.successful_items = 0
        self.failed_items = 0
        self.blocked_items = 0
        self.rate_limited_items = 0

    # ------------------------------------------------------------------ #
    # Persistence helpers
    # ------------------------------------------------------------------ #
    def to_db_row(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "updated_at": self.updated_at,
            "status": self.status.value,
            "config_json": self.config.to_json(),
            "session_id": self.session_id,
            "total_items": self.total_items,
            "processed_items": self.processed_items,
            "successful_items": self.successful_items,
            "failed_items": self.failed_items,
            "blocked_items": self.blocked_items,
            "rate_limited_items": self.rate_limited_items,
            "result_location": self.result_location,
            "error_summary": self.error_summary,
        }

    @classmethod
    def from_db_row(cls, row: dict) -> "Job":
        job = cls(
            id=row["id"],
            created_at=row["created_at"],
            started_at=row.get("started_at"),
            completed_at=row.get("completed_at"),
            updated_at=row.get("updated_at", row["created_at"]),
            status=JobStatus(row["status"]),
            config=JobConfig.from_json(row.get("config_json", "")),
            session_id=row.get("session_id"),
            total_items=int(row.get("total_items", 0)),
            processed_items=int(row.get("processed_items", 0)),
            successful_items=int(row.get("successful_items", 0)),
            failed_items=int(row.get("failed_items", 0)),
            blocked_items=int(row.get("blocked_items", 0)),
            rate_limited_items=int(row.get("rate_limited_items", 0)),
            result_location=row.get("result_location"),
            error_summary=row.get("error_summary"),
        )
        return job
