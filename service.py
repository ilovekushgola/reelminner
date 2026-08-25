"""Clean service layer between the UI / MCP and the scraping engine.

``ScraperService`` is the single, GUI-independent boundary the desktop app, the
CLI, and the MCP server talk to. It owns an :class:`Reelminner`
instance and exposes a small, intentional API plus optional typed event emission.
This is the "service / core boundary" introduced in the discovery Phase 1 work.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

from events import EventSink, StructuredLogger
from scraper import (
    DEFAULT_STATE_FILE,
    Reelminner,
    ReelData,
    export_excel,
    export_json,
    write_csv,
)

LOG = StructuredLogger("reelminner.service")


class ScraperService:
    """High-level facade over the scraping engine.

    The engine remains the source of truth for scraping logic; this class only
    coordinates configuration, execution, export, and event emission so that no
    consumer (GUI, CLI, MCP, future backend) needs to know engine internals.
    """

    def __init__(
        self,
        *,
        headless: bool = False,
        workers: int = 3,
        delay: float = 2.0,
        state_file: str = DEFAULT_STATE_FILE,
        log: Optional[Callable[[str], None]] = None,
        event_sink: Optional[EventSink] = None,
        proxy: Optional[dict] = None,
    ) -> None:
        self._event_sink = event_sink
        self._engine = Reelminner(
            headless=headless,
            workers=workers,
            delay=delay,
            state_file=state_file,
            log=log,
            event_sink=event_sink,
            proxy=proxy,
        )

    # --- configuration proxies (engine owns the real values) ---
    @property
    def headless(self) -> bool:
        return self._engine.headless

    @headless.setter
    def headless(self, value: bool) -> None:
        self._engine.headless = value

    @property
    def workers(self) -> int:
        return self._engine.workers

    @workers.setter
    def workers(self, value: int) -> None:
        self._engine.workers = value

    @property
    def delay(self) -> float:
        return self._engine.delay

    @delay.setter
    def delay(self, value: float) -> None:
        self._engine.delay = value

    @property
    def engine(self) -> Reelminner:
        """Direct engine access for advanced/legacy callers."""
        return self._engine

    # --- session management ---
    def has_session(self) -> bool:
        return self._engine.has_session()

    def clear_session(self) -> bool:
        return self._engine.clear_session()

    def save_cookies_from_file(self, path: str) -> bool:
        return self._engine.save_cookies_from_file(path)

    def login(self) -> None:
        self._engine.login()

    def stop(self) -> None:
        self._engine.stop()

    # --- scraping ---
    def scrape(
        self,
        urls: List[str],
        with_profiles: bool = True,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        row_cb: Optional[Callable[[ReelData], None]] = None,
    ) -> List[ReelData]:
        return self._engine.scrape(
            urls,
            with_profiles=with_profiles,
            progress_cb=progress_cb,
            row_cb=row_cb,
            event_sink=self._event_sink,
        )

    # --- export ---
    def export(self, rows: List[ReelData], path: str, fmt: str = "csv") -> Path:
        fmt = (fmt or "csv").lower()
        target = Path(path)
        if fmt == "csv":
            write_csv(rows, target)
        elif fmt == "xlsx":
            export_excel(rows, target)
        elif fmt == "json":
            export_json(rows, target)
        else:
            raise ValueError(f"unsupported export format: {fmt}")
        LOG.info("exported rows", count=len(rows), path=str(target), fmt=fmt)
        return target
