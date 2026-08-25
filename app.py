"""ReelminnerApplication — top-level application access layer (Phase 3).

This is a thin composition root, not a God object. It wires the existing
backend services together and exposes them so the future UI / IPC / MCP only
need to talk to stable services — never to SQLite, JSONL, or the scraper
internals.

    Future Desktop UI / MCP / CLI
            ↓
    ReelminnerApplication
        ├── .jobs     (JobManager)
        ├── .results  (ResultService)
        ├── .sessions (SessionManager)
        ├── .settings (SettingsService)
        ├── .proxies  (ProxyManager)
        └── .event_bus (ApplicationEventBus)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from app_events import ApplicationEventBus
from job_manager import JobManager
from proxies import ProxyManager, ProxySecretStore, ProxyStore
from results import ResultService
from sessions import SessionManager, SessionStore
from performance import PerformanceService
from settings import SettingsService
from storage import JobStore, ResultStore


class ReelminnerApplication:
    """Coordinates the backend application services."""

    _instance = None

    @classmethod
    def get_instance(cls, data_dir=None, db_name: str = "reelminner.db"):
        """Return the process-wide singleton, creating it on first use.

        The MCP server and tests use this to obtain a single application facade.
        """
        if cls._instance is None:
            cls._instance = cls(
                data_dir=data_dir or Path(os.getcwd()) / "data", db_name=db_name
            )
        return cls._instance

    def __init__(
        self,
        data_dir: str | Path = "data",
        db_name: str = "reelminner.db",
        event_bus: Optional[ApplicationEventBus] = None,
        scraper_factory=None,
    ) -> None:
        self.event_bus = event_bus or ApplicationEventBus()
        self.data_dir = Path(data_dir)
        self._db_path = self.data_dir / db_name

        # Shared persistence (single source of truth per store).
        self._job_store = JobStore(self._db_path)
        self._result_store = ResultStore(self.data_dir)
        self._session_store = SessionStore(self.data_dir / "sessions.db")

        # Application services.
        self.settings = SettingsService(self._job_store, self.event_bus)
        # Phase 3.6: performance intelligence & compute monitoring.
        self.performance = PerformanceService(
            data_dir=self.data_dir,
            db_path=self._db_path,
            event_bus=self.event_bus,
            settings=self.settings,
        )
        self.performance.start_monitoring()
        # Phase 3.5: proxy management. Credentials live in a git-ignored file
        # (data/proxy_secrets.json); metadata lives in the shared SQLite store.
        self._proxy_store = ProxyStore(self._db_path)
        self._proxy_secrets = ProxySecretStore(self.data_dir / "proxy_secrets.json")
        self.proxies = ProxyManager(
            self._proxy_store,
            self._proxy_secrets,
            event_bus=self.event_bus,
        )
        self.sessions = SessionManager(
            data_dir=self.data_dir,
            event_bus=self.event_bus,
            store=self._session_store,
        )
        self.jobs = JobManager(
            data_dir=self.data_dir,
            db_name=db_name,
            event_bus=self.event_bus,
            scraper_factory=scraper_factory,
            store=self._job_store,
            result_store=self._result_store,
            session_state_resolver=self.sessions.get_cookies_path,
            on_session_used=self.sessions.mark_used,
            proxy_resolver=self.proxies.build_scrape_proxy,
            on_proxy_used=self._on_proxy_used,
            performance_recorder=self.performance,
        )
        self.results = ResultService(
            self._result_store,
            default_page_size=self.settings.get().general.default_page_size,
        )

    # -- proxy usage hook --------------------------------------------------
    def _on_proxy_used(self, proxy_id: str, success: bool, error_summary: str) -> None:
        """Record usage/success/failure of a proxy used by a finished job.

        Credentials are never touched here; only metadata counts/timestamps are
        updated by the ProxyManager.
        """
        try:
            self.proxies.record_usage(proxy_id)
            if success:
                self.proxies.record_success(proxy_id)
            else:
                self.proxies.record_failure(proxy_id, error_summary or "")
        except Exception:
            pass
    def close(self) -> None:
        # Stop performance monitors and close the perf store (own connection).
        try:
            self.performance.close()
        except Exception:
            pass
        # Closing JobManager closes the shared JobStore; do not double-close.
        self.jobs.close()
        self.sessions.close()
        try:
            self._proxy_store.close()
        except Exception:
            pass
