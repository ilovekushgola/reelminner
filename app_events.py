"""Application-level event layer for Reelminner Phase 2.

Builds on the engine's ``events.py`` primitives:

    Scraper (engine)
        -> ScraperService
            -> ApplicationEventBus  (implements EventSink)
                -> ApplicationEventBus listeners
                    -> Future Desktop UI / Logs / MCP

The bus is the single ``EventSink`` handed to ``ScraperService``, so every
engine ``ScraperEvent`` flows through it. The bus translates those into
application events tagged with the *active job id* and also lets the
``JobManager`` emit lifecycle events (JOB_CREATED, JOB_PAUSED, ...).

It is intentionally decoupled from Tkinter / any UI framework.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from events import EventKind, EventSink, ScraperEvent

# ----------------------------------------------------------------------------
# Application event kinds
# ----------------------------------------------------------------------------
class AppEventKind(str, Enum):
    JOB_CREATED = "job_created"
    JOB_STARTED = "job_started"
    JOB_PROGRESS = "job_progress"
    ROW_PROCESSED = "row_processed"
    JOB_PAUSED = "job_paused"
    JOB_RESUMED = "job_resumed"
    JOB_STOPPED = "job_stopped"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    SESSION_CREATED = "session_created"
    SESSION_UPDATED = "session_updated"
    SESSION_TESTED = "session_tested"
    SESSION_FAILED = "session_failed"
    SETTINGS_UPDATED = "settings_updated"
    RESULTS_AVAILABLE = "results_available"
    PROXY_CREATED = "proxy_created"
    PROXY_UPDATED = "proxy_updated"
    PROXY_TESTED = "proxy_tested"
    PROXY_ENABLED = "proxy_enabled"
    PROXY_DISABLED = "proxy_disabled"
    PROXY_FAILED = "proxy_failed"
    PERFORMANCE_MONITOR_STARTED = "performance_monitor_started"
    PERFORMANCE_MONITOR_STOPPED = "performance_monitor_stopped"
    PERFORMANCE_WARNING = "performance_warning"
    PERFORMANCE_RECOMMENDATION_AVAILABLE = "performance_recommendation_available"
    JOB_PERFORMANCE_RECORDED = "job_performance_recorded"
    WARNING = "warning"
    ERROR = "error"
    LOG = "log"
    STATUS = "status"


@dataclass
class ApplicationEvent:
    """A single application-level event with job context."""

    kind: AppEventKind
    job_id: Optional[str]
    payload: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind.value,
            "job_id": self.job_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }


AppListener = Callable[[ApplicationEvent], None]


class ApplicationEventBus(EventSink):
    """Fan-out bus. Implements ``EventSink`` so the engine can push into it."""

    def __init__(self) -> None:
        self._listeners: list[AppListener] = []
        self._active_job: Optional[str] = None

    # -- subscription ------------------------------------------------------
    def subscribe(self, listener: AppListener) -> AppListener:
        self._listeners.append(listener)
        return listener

    def unsubscribe(self, listener: AppListener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    # -- active job context ------------------------------------------------
    def set_active_job(self, job_id: Optional[str]) -> None:
        self._active_job = job_id

    def clear_active_job(self) -> None:
        self._active_job = None

    # -- EventSink: engine -> application ---------------------------------
    def emit(self, event: ScraperEvent) -> None:  # type: ignore[override]
        """Receive a ScraperEvent from the engine and re-dispatch it."""
        kind = self._translate(event)
        if kind is None:
            return
        self._dispatch(
            ApplicationEvent(kind, self._active_job, dict(event.payload))
        )

    # -- application-level emit (JobManager lifecycle) ---------------------
    def emit_app(
        self,
        kind: AppEventKind,
        job_id: Optional[str],
        payload: Optional[dict] = None,
    ) -> None:
        self._dispatch(ApplicationEvent(kind, job_id, payload or {}))

    # -- dispatch ----------------------------------------------------------
    def _dispatch(self, app_event: ApplicationEvent) -> None:
        for fn in list(self._listeners):
            try:
                fn(app_event)
            except Exception:  # a bad listener must not break the pipeline
                pass

    @staticmethod
    def _translate(event: ScraperEvent) -> Optional[AppEventKind]:
        k = event.kind
        if k is EventKind.PROGRESS:
            return AppEventKind.JOB_PROGRESS
        if k is EventKind.ROW:
            return AppEventKind.ROW_PROCESSED
        if k is EventKind.ERROR:
            return AppEventKind.ERROR
        if k is EventKind.STATUS:
            return AppEventKind.STATUS
        if k is EventKind.LOG:
            msg = str(event.payload.get("message", ""))
            if msg.startswith(("[x]", "[!]")) or "ERROR" in msg.upper():
                return AppEventKind.ERROR
            if "WARN" in msg.upper():
                return AppEventKind.WARNING
            return AppEventKind.LOG
        # JOB_START / JOB_DONE are owned by JobManager lifecycle; ignore here.
        return None
