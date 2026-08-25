"""Typed events and structured logging for Reelminner.

This module is the foundation for the future desktop application (UI, Job Monitor,
Logs, and MCP layers). It intentionally depends only on the standard library so it
can be imported anywhere without pulling in the scraping engine.

Exposes:
  * ``EventKind`` / ``ScraperEvent``  - typed events emitted by the engine.
  * ``EventSink``                     - protocol that consumers implement.
  * ``ProgressCallback`` / ``RowCallback`` / ``LogCallback`` - backward-compatible
    typed callbacks used by the engine today.
  * ``StructuredLogger``             - thin wrapper over :mod:`logging`.
  * ``configure_logging``            - set up console / file / JSON logging.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, Protocol


class EventKind(str, Enum):
    """Kinds of events the engine can emit."""

    LOG = "log"
    PROGRESS = "progress"
    ROW = "row"
    STATUS = "status"
    ERROR = "error"
    JOB_START = "job_start"
    JOB_DONE = "job_done"


@dataclass
class ScraperEvent:
    """A single typed event.

    ``payload`` is a plain ``dict`` so events serialize cleanly over IPC / MCP.
    """

    kind: EventKind
    payload: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind.value,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }


class EventSink(Protocol):
    """Implemented by anything that wants to receive engine events."""

    def emit(self, event: ScraperEvent) -> None:  # pragma: no cover - protocol
        ...


# Backward-compatible typed callbacks (kept so the existing engine API is stable).
ProgressCallback = Callable[[int, int], None]
RowCallback = Callable[[Any], None]
LogCallback = Callable[[str], None]


class StructuredLogger:
    """Thin wrapper around :mod:`logging` with optional structured context."""

    def __init__(self, name: str = "reelminner") -> None:
        self._log = logging.getLogger(name)

    def log(self, level: int, msg: str, **ctx: Any) -> None:
        extra = {"reelminner_ctx": ctx} if ctx else {}
        self._log.log(level, msg, extra=extra)

    def debug(self, msg: str, **ctx: Any) -> None:
        self.log(logging.DEBUG, msg, **ctx)

    def info(self, msg: str, **ctx: Any) -> None:
        self.log(logging.INFO, msg, **ctx)

    def warning(self, msg: str, **ctx: Any) -> None:
        self.log(logging.WARNING, msg, **ctx)

    def error(self, msg: str, **ctx: Any) -> None:
        self.log(logging.ERROR, msg, **ctx)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        obj: dict = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        ctx = getattr(record, "reelminner_ctx", None)
        if ctx:
            obj["ctx"] = ctx
        return json.dumps(obj, ensure_ascii=False)


def configure_logging(
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    json_logs: bool = False,
    console: bool = False,
) -> None:
    """Configure the ``reelminner`` logger.

    Safe to call multiple times: handlers are only attached once. ``console`` is
    ``False`` by default so we do not duplicate the engine's own ``print``-based
    ``self.log`` output.
    """
    root = logging.getLogger("reelminner")
    root.setLevel(level)
    if root.handlers:
        return

    fmt: logging.Formatter = (
        _JsonFormatter() if json_logs else logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"
        )
    )
    if console:
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        root.addHandler(ch)
    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    # Keep Playwright / dependency noise out of our logs.
    logging.getLogger("playwright").setLevel(logging.WARNING)
