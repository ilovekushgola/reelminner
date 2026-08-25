"""JobManager — the authoritative lifecycle owner for Reelminner Phase 2.

Dependency direction (per the architecture):

    UI / MCP / CLI
        -> Application Services (JobManager)
            -> Repositories / Persistence (storage.JobStore / ResultStore)
            -> Core Scraper (scraper.Reelminner via service.ScraperService)

The JobManager NEVER implements scraping itself. It drives the existing
``ScraperService`` and owns:

  * job creation / lifecycle transitions (single source of truth)
  * persistence (via ``JobStore`` + ``ResultStore``)
  * the application event flow (via ``ApplicationEventBus``)

The engine remains independently testable; the GUI / MCP keep working because
they talk to ``ScraperService`` directly and are untouched.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from app_events import ApplicationEvent as AppEvent, AppEventKind, ApplicationEventBus
from events import StructuredLogger
from jobs import IllegalTransitionError, Job, JobConfig, JobStatus
from proxies import NetworkMode
from storage import JobStore, ResultStore, StorageError

LOG = StructuredLogger("reelminner.jobmanager")

ScraperFactory = Callable[..., Any]

# A proxy resolver takes a proxy id and returns a Playwright proxy dict (with
# credentials) or None when the proxy is unavailable. Wired by the facade.
ProxyResolver = Callable[[str], Optional[dict]]
# Called after a job finishes to record proxy usage. (proxy_id, success, error_summary)
ProxyUsageCallback = Callable[[str, bool, str], None]
# Phase 3.6 performance hook. Receives JobManager lifecycle + progress signals.
# Duck-typed (Any) to avoid a hard import cycle with performance.py.
PerformanceRecorder = Any


def _default_factory(**kwargs: Any) -> Any:
    """Build the real ``ScraperService`` (lazy import keeps tests light)."""
    from service import ScraperService

    return ScraperService(**kwargs)


@dataclass
class _Run:
    """Transient runtime state for a job that is currently executing."""

    job_id: str
    scraper: Any
    job: Job
    thread: Optional[threading.Thread] = None
    pause_requested: bool = False
    stop_requested: bool = False
    proxy_id: Optional[str] = None


def job_to_dict(job: "Job") -> dict:
    """Serialise a Job for MCP / API responses (no internal objects)."""
    return {
        "id": job.id,
        "status": job.status.value,
        "session_id": job.session_id,
        "network_mode": job.config.network_mode.value,
        "proxy_id": job.config.proxy_id,
        "total_urls": getattr(job, "total_urls", 0),
        "processed": getattr(job, "processed_items", 0),
        "successful": getattr(job, "successful_items", 0),
        "failed": getattr(job, "failed_items", 0),
        "blocked": getattr(job, "blocked_items", 0),
        "rate_limited": getattr(job, "rate_limited_items", 0),
        "created_at": job.created_at,
        "started_at": getattr(job, "started_at", None),
        "ended_at": getattr(job, "completed_at", None) or getattr(job, "ended_at", None),
        "updated_at": getattr(job, "updated_at", None),
        "error_summary": job.error_summary,
    }


class JobManager:
    """Creates, runs, pauses, resumes, stops and persists scrape jobs."""

    def __init__(
        self,
        data_dir: str | Path = "data",
        db_name: str = "reelminner.db",
        event_bus: Optional[ApplicationEventBus] = None,
        scraper_factory: Optional[ScraperFactory] = None,
        store: Optional[JobStore] = None,
        result_store: Optional[ResultStore] = None,
        session_state_resolver: Optional[Callable[[str], Optional[str]]] = None,
        on_session_used: Optional[Callable[[str], None]] = None,
        proxy_resolver: Optional[ProxyResolver] = None,
        on_proxy_used: Optional[ProxyUsageCallback] = None,
        performance_recorder: Optional[PerformanceRecorder] = None,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._state_file = str(self._data_dir / "storage_state.json")
        self._store = store or JobStore(self._data_dir / db_name)
        self._results = result_store or ResultStore(self._data_dir)
        self._bus = event_bus or ApplicationEventBus()
        self._factory = scraper_factory or _default_factory
        # Hooks for Job+Session integration (wired by the application facade).
        self._session_state_resolver = session_state_resolver
        self._on_session_used = on_session_used
        # Hooks for Phase 3.5 Proxy integration (wired by the application facade).
        self._proxy_resolver = proxy_resolver
        self._on_proxy_used = on_proxy_used
        self._perf = performance_recorder
        self._runtime: dict[str, _Run] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Factory helpers
    # ------------------------------------------------------------------ #
    def _build_scraper(self, job: Job, proxy_dict: Optional[dict] = None) -> Any:
        # Resolve the cookies/state file for this job's selected session.
        state_file = self._state_file
        if job.session_id and self._session_state_resolver is not None:
            resolved = self._session_state_resolver(job.session_id)
            if resolved:
                state_file = resolved
                if self._on_session_used is not None:
                    try:
                        self._on_session_used(job.session_id)
                    except Exception:
                        pass
        factory_kwargs = dict(
            headless=job.config.headless,
            workers=job.config.workers,
            delay=job.config.delay,
            state_file=state_file,
            event_sink=self._bus,
            log=self._make_log_cb(job.id),
        )
        if proxy_dict is not None:
            factory_kwargs["proxy"] = proxy_dict
        return self._factory(**factory_kwargs)

    def _resolve_proxy(self, job: Job) -> Optional[dict]:
        """Resolve a Playwright proxy dict for a FIXED_PROXY job.

        Returns ``None`` (and emits a PROXY_FAILED warning) when the proxy is
        missing, disabled, unhealthy or deleted. Callers fall back to a DIRECT
        connection in that case. Proxy credentials never leave this call except
        into the Playwright proxy dict consumed by the scraper.
        """
        if job.config.network_mode != NetworkMode.FIXED_PROXY or not job.config.proxy_id:
            return None
        if self._proxy_resolver is None:
            return None
        try:
            resolved = self._proxy_resolver(job.config.proxy_id)
        except Exception:
            resolved = None
        if resolved is None:
            LOG.warning(
                "proxy unavailable; falling back to DIRECT connection",
                proxy_id=job.config.proxy_id,
            )
            self._bus.emit(
                AppEvent(
                    AppEventKind.PROXY_FAILED,
                    {
                        "proxy_id": job.config.proxy_id,
                        "error": "unavailable; fell back to DIRECT connection",
                    },
                )
            )
            return None
        return resolved

    def _make_log_cb(self, job_id: str) -> Callable[[str], None]:
        def cb(msg: str) -> None:
            print(msg)
            self._bus.emit_app(AppEventKind.LOG, job_id, {"message": msg})

        return cb

    def _make_row_cb(self, run: _Run) -> Callable[[Any], None]:
        def cb(data: Any) -> None:
            run.job.record_result(getattr(data, "status", "ok"))
            self._results.append_result(run.job_id, data)

        return cb

    def _make_progress_cb(self, run: _Run) -> Callable[[int, int], None]:
        def cb(done: int, total: int) -> None:
            run.job.processed_items = done
            run.job.total_items = max(run.job.total_items, total)
            try:
                self._store.update_job(run.job)
            except StorageError:
                pass
            if self._perf is not None:
                try:
                    self._perf.record_job_progress(run, done, total)
                except Exception:
                    pass

        return cb

    # ------------------------------------------------------------------ #
    # create
    # ------------------------------------------------------------------ #
    def create_job(
        self,
        urls: list[str],
        workers: int = 3,
        delay: float = 2.0,
        headless: bool = False,
        with_profiles: bool = True,
        session_id: Optional[str] = None,
        network_mode: NetworkMode = NetworkMode.DIRECT,
        proxy_id: Optional[str] = None,
    ) -> Job:
        from parsers import normalize_reel_url

        if isinstance(network_mode, str):
            try:
                network_mode = NetworkMode(network_mode)
            except ValueError:
                network_mode = NetworkMode.DIRECT
        normalized: list[str] = []
        for u in urls:
            n = normalize_reel_url(u)
            if n:
                normalized.append(n)
            else:
                LOG.warning("Skipping invalid reel URL", url=u)
        config = JobConfig(
            urls=normalized,
            workers=workers,
            delay=delay,
            headless=headless,
            with_profiles=with_profiles,
            pending_urls=[],
            network_mode=network_mode,
            proxy_id=proxy_id if network_mode == NetworkMode.FIXED_PROXY else None,
        )
        job = Job(config=config, session_id=session_id)
        self._store.create_job(job)
        self._bus.emit_app(
            AppEventKind.JOB_CREATED,
            job.id,
            {"urls": normalized, "network_mode": network_mode.value, "proxy_id": job.config.proxy_id},
        )
        return job

    # ------------------------------------------------------------------ #
    # start
    # ------------------------------------------------------------------ #
    def start_job(self, job_id: str) -> Job:
        job = self._store.get_job(job_id)
        if job is None:
            raise StorageError(f"No such job: {job_id}")
        if job.status not in (JobStatus.CREATED, JobStatus.QUEUED):
            raise IllegalTransitionError(
                f"Cannot start job in state {job.status.value}"
            )
        # Fresh (non-resume) start: clear any leftover pending cursor + results.
        job.config.pending_urls = []
        job.result_location = str(self._results.result_path(job.id))
        job.transition_to(JobStatus.STARTING)
        self._store.update_job(job)

        targets = list(job.config.urls)
        job.total_items = len(targets)
        job.reset_stats()
        self._store.update_job(job)

        self._bus.set_active_job(job.id)
        self._bus.emit_app(
            AppEventKind.JOB_STARTED, job.id, {"targets": len(targets)}
        )

        proxy_dict = self._resolve_proxy(job)
        run = _Run(
            job_id=job.id,
            scraper=self._build_scraper(job, proxy_dict),
            job=job,
            proxy_id=job.config.proxy_id if proxy_dict is not None else None,
        )
        with self._lock:
            self._runtime[job_id] = run
        if self._perf is not None:
            try:
                self._perf.record_job_start(job)
            except Exception:
                pass
        run.thread = threading.Thread(
            target=self._run, args=(run, targets, False), daemon=True
        )
        run.thread.start()
        return job

    # ------------------------------------------------------------------ #
    # internal run loop
    # ------------------------------------------------------------------ #
    def _run(self, run: _Run, targets: list[str], is_resume: bool) -> None:
        job = run.job
        try:
            # Honor a pause/stop requested before scraping actually began.
            if run.pause_requested:
                self._finalize_paused(run, targets, [])
                return
            if run.stop_requested:
                self._finalize_stopped(run, targets, [])
                return
            try:
                if job.status != JobStatus.RUNNING:
                    # (start_job / resume_job already emitted the event)
                    job.transition_to(JobStatus.RUNNING)
                    self._store.update_job(job)

                results = run.scraper.scrape(
                    targets,
                    with_profiles=job.config.with_profiles,
                    progress_cb=self._make_progress_cb(run),
                    row_cb=self._make_row_cb(run),
                )
            except Exception as exc:  # scrape crashed
                job.error_summary = str(exc)[:500]
                try:
                    job.transition_to(JobStatus.FAILED)
                except IllegalTransitionError:
                    pass
                try:
                    self._store.update_job(job)
                except Exception:
                    pass
                self._bus.emit_app(
                    AppEventKind.JOB_FAILED, job.id, {"error": job.error_summary}
                )
                return

            # scrape returned (normally or after soft stop)
            try:
                if run.stop_requested:
                    self._finalize_stopped(run, targets, results)
                elif run.pause_requested:
                    self._finalize_paused(run, targets, results)
                else:
                    self._finalize_completed(run, targets, results)
            except Exception:
                # A persistence failure must not crash the worker thread.
                pass
        finally:
            # Record proxy usage (success/failure) for FIXED_PROXY jobs that
            # actually used a proxy. Credentials never appear here.
            if run.proxy_id and self._on_proxy_used is not None:
                try:
                    success = run.job.status == JobStatus.COMPLETED
                    self._on_proxy_used(
                        run.proxy_id, success, run.job.error_summary or ""
                    )
                except Exception:
                    pass
            if self._perf is not None:
                try:
                    self._perf.record_job_end(run.job)
                except Exception:
                    pass
            self._cleanup(run)

    def _finalize_completed(self, run: _Run, targets, results) -> None:
        job = run.job
        job.transition_to(JobStatus.COMPLETED)
        self._store.update_job(job)
        self._bus.emit_app(
            AppEventKind.JOB_COMPLETED,
            job.id,
            {
                "processed": job.processed_items,
                "successful": job.successful_items,
                "failed": job.failed_items,
                "blocked": job.blocked_items,
                "rate_limited": job.rate_limited_items,
            },
        )
        if job.processed_items > 0:
            self._bus.emit_app(
                AppEventKind.RESULTS_AVAILABLE,
                job.id,
                {"count": job.processed_items},
            )

    def _finalize_stopped(self, run: _Run, targets, results) -> None:
        job = run.job
        remaining = self._pending(targets, results)
        job.config.pending_urls = remaining
        try:
            job.transition_to(JobStatus.STOPPED)
        except IllegalTransitionError:
            pass
        self._store.update_job(job)
        # stop_job() already emitted JOB_STOPPED when it set the flag.

    def _finalize_paused(self, run: _Run, targets, results) -> None:
        job = run.job
        remaining = self._pending(targets, results)
        job.config.pending_urls = remaining
        try:
            job.transition_to(JobStatus.PAUSED)
        except IllegalTransitionError:
            pass
        self._store.update_job(job)
        self._bus.emit_app(
            AppEventKind.JOB_PAUSED,
            job.id,
            {"pending": len(remaining)},
        )

    @staticmethod
    def _pending(targets: list[str], results: list) -> list[str]:
        done = {getattr(r, "reel_url", None) for r in results}
        done.discard(None)
        return [u for u in targets if u not in done]

    def _cleanup(self, run: _Run) -> None:
        self._bus.clear_active_job()
        with self._lock:
            self._runtime.pop(run.job_id, None)

    # ------------------------------------------------------------------ #
    # pause / resume / stop
    # ------------------------------------------------------------------ #
    def pause_job(self, job_id: str) -> Job:
        job = self._store.get_job(job_id)
        if job is None:
            raise StorageError(f"No such job: {job_id}")
        if job.status not in (JobStatus.RUNNING, JobStatus.STARTING):
            raise IllegalTransitionError(
                f"Cannot pause job in state {job.status.value}"
            )
        run = self._runtime.get(job_id)
        if run is not None:
            run.pause_requested = True
            try:
                run.scraper.stop()
            except Exception:
                pass
        # Reflect intent immediately; _run finalizes PAUSED (no-op if already).
        job.transition_to(JobStatus.PAUSED)
        self._store.update_job(job)
        return job

    def resume_job(self, job_id: str) -> Job:
        job = self._store.get_job(job_id)
        if job is None:
            raise StorageError(f"No such job: {job_id}")
        if job.status not in (JobStatus.PAUSED,):
            raise IllegalTransitionError(
                f"Can only resume a PAUSED job, not {job.status.value}"
            )
        pending = list(job.config.pending_urls) or list(job.config.urls)
        if not pending:
            job.transition_to(JobStatus.COMPLETED)
            self._store.update_job(job)
            self._bus.emit_app(AppEventKind.JOB_COMPLETED, job.id, {})
            return job

        job.transition_to(JobStatus.RUNNING)
        self._store.update_job(job)
        self._bus.set_active_job(job.id)
        self._bus.emit_app(
            AppEventKind.JOB_RESUMED, job.id, {"pending": len(pending)}
        )

        proxy_dict = self._resolve_proxy(job)
        run = _Run(
            job_id=job.id,
            scraper=self._build_scraper(job, proxy_dict),
            job=job,
            proxy_id=job.config.proxy_id if proxy_dict is not None else None,
        )
        with self._lock:
            self._runtime[job_id] = run
        if self._perf is not None:
            try:
                self._perf.record_job_start(job)
            except Exception:
                pass
        run.thread = threading.Thread(
            target=self._run, args=(run, pending, True), daemon=True
        )
        run.thread.start()
        return job

    def stop_job(self, job_id: str) -> Job:
        job = self._store.get_job(job_id)
        if job is None:
            raise StorageError(f"No such job: {job_id}")
        if job.is_terminal():
            return job
        run = self._runtime.get(job_id)
        if run is not None:
            run.stop_requested = True
            try:
                run.scraper.stop()
            except Exception:
                pass
        job.transition_to(JobStatus.STOPPED)
        self._store.update_job(job)
        self._bus.emit_app(AppEventKind.JOB_STOPPED, job.id, {"pending": 0})
        return job

    def retry_job(self, job_id: str) -> Job:
        old = self._store.get_job(job_id)
        if old is None:
            raise StorageError(f"No such job: {job_id}")
        if old.status not in (
            JobStatus.FAILED,
            JobStatus.STOPPED,
            JobStatus.INTERRUPTED,
        ):
            raise IllegalTransitionError(
                f"Can only retry a failed/stopped/interrupted job, "
                f"not {old.status.value}"
            )
        # Create a NEW job from the old config (history preserved).
        return self.create_job(
            urls=old.config.urls,
            workers=old.config.workers,
            delay=old.config.delay,
            headless=old.config.headless,
            with_profiles=old.config.with_profiles,
        )

    # ------------------------------------------------------------------ #
    # read
    # ------------------------------------------------------------------ #
    def get_job(self, job_id: str) -> Optional[Job]:
        return self._store.get_job(job_id)

    def list_jobs(
        self,
        limit: int = 50,
        offset: int = 0,
        status: Optional[JobStatus] = None,
    ) -> list[Job]:
        return self._store.list_jobs(limit=limit, offset=offset, status=status)

    def get_job_results(self, job_id: str) -> list:
        return self._results.load_results(job_id)

    def get_job_result_count(self, job_id: str) -> int:
        return self._results.count(job_id)

    # ------------------------------------------------------------------ #
    # settings
    # ------------------------------------------------------------------ #
    def set_setting(self, key: str, value: Any) -> None:
        self._store.set_setting(key, value)

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self._store.get_setting(key, default)

    def close(self) -> None:
        with self._lock:
            for run in list(self._runtime.values()):
                try:
                    run.scraper.stop()
                except Exception:
                    pass
        self.wait_for_idle()
        self._store.close()

    # ------------------------------------------------------------------ #
    # thread management
    # ------------------------------------------------------------------ #
    def wait_for_job(self, job_id: str, timeout: float = 30.0) -> None:
        """Block until the job's worker thread has exited (best-effort)."""
        run = self._runtime.get(job_id)
        if run is not None and run.thread is not None:
            run.thread.join(timeout)

    def wait_for_idle(self, timeout: float = 30.0) -> None:
        """Block until all active worker threads have exited."""
        with self._lock:
            runs = list(self._runtime.values())
        for run in runs:
            if run.thread is not None:
                run.thread.join(timeout)
