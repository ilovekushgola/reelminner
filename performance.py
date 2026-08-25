"""Phase 3.6 — Performance Intelligence & Compute Monitoring (backend only).

This module implements read-only observability for the local Reelminner process
and the jobs it runs. It NEVER changes running jobs or settings; it only
observes, persists, analyzes, and recommends.

Components:
  * SystemCapabilities        — one-time host profile (no PII).
  * SystemMonitor             — background thread sampling the whole machine.
  * RuntimeMonitor            — background thread sampling the Reelminner process
                                and its child browsers (graceful degradation).
  * JobPerformanceSample      — throttled per-job throughput/quality sample.
  * PerformanceStore          — additive tables in the shared SQLite DB.
  * JobPerformanceSummary     — generated on job finalize, survives restart.
  * PerformanceAnalyzer       — worker comparison + conservative bottleneck
                                detection + diminishing-returns analysis.
  * RecommendationEngine      — rule-based, Observed/Estimated/Insufficient-Data.
  * PerformanceService        — facade held by ReelminnerApplication.performance.

No UI, no auto-tuning, no network telemetry, no personal data.
"""

from __future__ import annotations

import os
import platform
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import psutil

from app_events import AppEventKind, ApplicationEventBus
from job_manager import job_to_dict

# --------------------------------------------------------------------------- #
# Conservative vocabulary
# --------------------------------------------------------------------------- #
# Bottleneck labels (never stated as proven cause).
BOTTLENECK_CPU_BOUND = "CPU_BOUND"
BOTTLENECK_MEMORY_BOUND = "MEMORY_BOUND"
BOTTLENECK_NETWORK_LIMITED = "NETWORK_LIMITED"
BOTTLENECK_SCRAPER_LIMITED = "SCRAPER_LIMITED"
BOTTLENECK_UNKNOWN = "UNKNOWN"

# Confidence for a bottleneck label.
CONF_LIKELY = "LIKELY"
CONF_POSSIBLE = "POSSIBLE"
CONF_UNKNOWN = "UNKNOWN"

# Basis for a recommendation.
BASIS_OBSERVED = "Observed"
BASIS_ESTIMATED = "Estimated"
BASIS_INSUFFICIENT = "Insufficient-Data"


# --------------------------------------------------------------------------- #
# Typed models
# --------------------------------------------------------------------------- #
@dataclass
class SystemCapabilities:
    """Host profile captured once at startup. Deliberately contains NO PII:

    no hostname, username, IP, MAC, serial number, or file contents.
    """

    os_name: str = "unknown"
    os_version: str = "unknown"
    arch: str = "unknown"
    python_version: str = "unknown"
    cpu_logical: int = 0
    cpu_physical: int = 0
    cpu_model: str = "unknown"
    total_ram_bytes: int = 0
    total_disk_bytes: int = 0
    gpu_available: bool = False
    gpu_model: str = "unknown"

    def to_dict(self) -> dict:
        return {
            "os_name": self.os_name,
            "os_version": self.os_version,
            "arch": self.arch,
            "python_version": self.python_version,
            "cpu_logical": self.cpu_logical,
            "cpu_physical": self.cpu_physical,
            "cpu_model": self.cpu_model,
            "total_ram_bytes": self.total_ram_bytes,
            "total_disk_bytes": self.total_disk_bytes,
            "gpu_available": self.gpu_available,
            "gpu_model": self.gpu_model,
        }


@dataclass
class SystemSnapshot:
    timestamp: float = 0.0
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used_bytes: int = 0
    disk_used_percent: float = 0.0
    net_sent_bytes: int = 0
    net_recv_bytes: int = 0
    gpu_percent: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "cpu_percent": round(self.cpu_percent, 2),
            "memory_percent": round(self.memory_percent, 2),
            "memory_used_bytes": self.memory_used_bytes,
            "disk_used_percent": round(self.disk_used_percent, 2),
            "net_sent_bytes": self.net_sent_bytes,
            "net_recv_bytes": self.net_recv_bytes,
            "gpu_percent": (
                round(self.gpu_percent, 2) if self.gpu_percent is not None else None
            ),
        }


@dataclass
class ProcessSnapshot:
    """Reelminner process + child browser metrics. All fields degrade to 0/None."""

    timestamp: float = 0.0
    process_cpu_percent: float = 0.0
    process_memory_bytes: int = 0
    child_browser_count: int = 0
    child_cpu_percent: float = 0.0
    child_memory_bytes: int = 0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "process_cpu_percent": round(self.process_cpu_percent, 2),
            "process_memory_bytes": self.process_memory_bytes,
            "child_browser_count": self.child_browser_count,
            "child_cpu_percent": round(self.child_cpu_percent, 2),
            "child_memory_bytes": self.child_memory_bytes,
        }


@dataclass
class JobPerformanceSample:
    """One throttled observation of a running job. Formula fields are div-safe."""

    job_id: str
    timestamp: float = 0.0
    worker_count: int = 0
    delay: float = 0.0
    network_mode: str = "direct"
    proxy_id: Optional[str] = None
    processed: int = 0
    successful: int = 0
    failed: int = 0
    blocked: int = 0
    rate_limited: int = 0
    elapsed_seconds: float = 0.0
    urls_per_min_current: float = 0.0
    urls_per_min_avg: float = 0.0
    avg_seconds_per_url: Optional[float] = None
    eta_seconds: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "timestamp": self.timestamp,
            "worker_count": self.worker_count,
            "delay": self.delay,
            "network_mode": self.network_mode,
            "proxy_id": self.proxy_id,
            "processed": self.processed,
            "successful": self.successful,
            "failed": self.failed,
            "blocked": self.blocked,
            "rate_limited": self.rate_limited,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "urls_per_min_current": round(self.urls_per_min_current, 3),
            "urls_per_min_avg": round(self.urls_per_min_avg, 3),
            "avg_seconds_per_url": (
                round(self.avg_seconds_per_url, 3)
                if self.avg_seconds_per_url is not None
                else None
            ),
            "eta_seconds": (
                round(self.eta_seconds, 1) if self.eta_seconds is not None else None
            ),
        }


@dataclass
class JobPerformanceSummary:
    """Persisted outcome of a finished (or sampled) job."""

    job_id: str
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    worker_count: int = 0
    delay: float = 0.0
    network_mode: str = "direct"
    proxy_id: Optional[str] = None
    total_urls: int = 0
    processed: int = 0
    successful: int = 0
    failed: int = 0
    blocked: int = 0
    rate_limited: int = 0
    elapsed_seconds: float = 0.0
    avg_urls_per_min: float = 0.0
    avg_seconds_per_url: Optional[float] = None
    bottleneck_label: str = BOTTLENECK_UNKNOWN
    bottleneck_confidence: str = CONF_UNKNOWN

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "worker_count": self.worker_count,
            "delay": self.delay,
            "network_mode": self.network_mode,
            "proxy_id": self.proxy_id,
            "total_urls": self.total_urls,
            "processed": self.processed,
            "successful": self.successful,
            "failed": self.failed,
            "blocked": self.blocked,
            "rate_limited": self.rate_limited,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "avg_urls_per_min": round(self.avg_urls_per_min, 3),
            "avg_seconds_per_url": (
                round(self.avg_seconds_per_url, 3)
                if self.avg_seconds_per_url is not None
                else None
            ),
            "bottleneck_label": self.bottleneck_label,
            "bottleneck_confidence": self.bottleneck_confidence,
        }


@dataclass
class PerformanceRecommendation:
    """A single, non-binding recommendation. Never auto-applied."""

    kind: str
    basis: str  # BASIS_OBSERVED / BASIS_ESTIMATED / BASIS_INSUFFICIENT
    confidence: str  # CONF_LIKELY / CONF_POSSIBLE / CONF_UNKNOWN
    message: str
    suggested_workers: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "basis": self.basis,
            "confidence": self.confidence,
            "message": self.message,
            "suggested_workers": self.suggested_workers,
        }


# --------------------------------------------------------------------------- #
# Capability detection (PART 2)
# --------------------------------------------------------------------------- #
def _cpu_model() -> str:
    try:
        if platform.system() == "Windows":
            return "unknown"  # avoid WMI; model is non-essential
        import subprocess

        out = subprocess.run(
            ["sh", "-c", "grep -m1 'model name' /proc/cpuinfo 2>/dev/null"],
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout
        if out:
            return out.split(":", 1)[1].strip()[:120]
    except Exception:
        pass
    return "unknown"


def _detect_gpu() -> tuple[bool, str]:
    """Best-effort GPU detection. Never a hard dependency (optional lib)."""
    try:
        import GPUtil  # type: ignore

        gpus = GPUtil.getGPUs()
        if gpus:
            return True, gpus[0].name[:120]
    except Exception:
        pass
    return False, "unknown"


def detect_capabilities() -> SystemCapabilities:
    try:
        cpu_logical = int(psutil.cpu_count(logical=True) or 0)
        cpu_physical = int(psutil.cpu_count(logical=False) or 0)
    except Exception:
        cpu_logical = cpu_physical = 0
    try:
        total_ram = int(psutil.virtual_memory().total)
    except Exception:
        total_ram = 0
    try:
        total_disk = int(psutil.disk_usage(os.getcwd()).total)
    except Exception:
        total_disk = 0
    gpu_available, gpu_model = _detect_gpu()
    return SystemCapabilities(
        os_name=platform.system() or "unknown",
        os_version=platform.version() or "unknown",
        arch=platform.machine() or "unknown",
        python_version=platform.python_version() or "unknown",
        cpu_logical=cpu_logical,
        cpu_physical=cpu_physical,
        cpu_model=_cpu_model(),
        total_ram_bytes=total_ram,
        total_disk_bytes=total_disk,
        gpu_available=gpu_available,
        gpu_model=gpu_model,
    )


# --------------------------------------------------------------------------- #
# System monitoring (PART 3)
# --------------------------------------------------------------------------- #
class SystemMonitor:
    def __init__(self, event_bus: ApplicationEventBus, gpu_enabled: bool = False):
        self._bus = event_bus
        self._gpu_enabled = gpu_enabled
        self._lock = threading.Lock()
        self._latest: Optional[SystemSnapshot] = None
        self._interval = 5.0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._cpu_max = 0.0
        self._mem_max = 0.0

    def start(self, interval: float) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._interval = max(1.0, min(60.0, float(interval)))
        self._stop.clear()
        self._cpu_max = self._mem_max = 0.0
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._bus.emit_app(
            AppEventKind.PERFORMANCE_MONITOR_STARTED,
            None,
            {"interval": self._interval, "scope": "system"},
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                snap = self._sample()
                with self._lock:
                    self._latest = snap
                    self._cpu_max = max(self._cpu_max, snap.cpu_percent)
                    self._mem_max = max(self._mem_max, snap.memory_percent)
                self._maybe_warn(snap)
            except Exception:
                pass
            self._stop.wait(self._interval)

    def _sample(self) -> SystemSnapshot:
        try:
            cpu = float(psutil.cpu_percent(interval=None))
        except Exception:
            cpu = 0.0
        try:
            vm = psutil.virtual_memory()
            mem_pct = float(vm.percent)
            mem_used = int(vm.used)
        except Exception:
            mem_pct, mem_used = 0.0, 0
        try:
            du = psutil.disk_usage(os.getcwd())
            disk_pct = float(du.percent)
        except Exception:
            disk_pct = 0.0
        try:
            net = psutil.net_io_counters()
            sent = int(net.bytes_sent)
            recv = int(net.bytes_recv)
        except Exception:
            sent = recv = 0
        gpu = None
        if self._gpu_enabled:
            try:
                import GPUtil  # type: ignore

                g = GPUtil.getGPUs()
                if g:
                    gpu = float(g[0].load * 100.0)
            except Exception:
                gpu = None
        return SystemSnapshot(
            timestamp=time.time(),
            cpu_percent=cpu,
            memory_percent=mem_pct,
            memory_used_bytes=mem_used,
            disk_used_percent=disk_pct,
            net_sent_bytes=sent,
            net_recv_bytes=recv,
            gpu_percent=gpu,
        )

    def _maybe_warn(self, snap: SystemSnapshot) -> None:
        if snap.memory_percent >= 90.0:
            self._bus.emit_app(
                AppEventKind.PERFORMANCE_WARNING,
                None,
                {"kind": "memory", "message": "System memory usage >= 90%"},
            )

    def get_snapshot(self) -> Optional[SystemSnapshot]:
        with self._lock:
            return self._latest

    def peak_cpu(self) -> float:
        with self._lock:
            return self._cpu_max

    def peak_memory(self) -> float:
        with self._lock:
            return self._mem_max


# --------------------------------------------------------------------------- #
# Process / runtime monitoring (PART 4)
# --------------------------------------------------------------------------- #
class RuntimeMonitor:
    def __init__(self, event_bus: ApplicationEventBus):
        self._bus = event_bus
        self._lock = threading.Lock()
        self._latest: Optional[ProcessSnapshot] = None
        self._interval = 5.0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._cpu_max = 0.0
        self._mem_max = 0.0
        self._pid = os.getpid()

    def start(self, interval: float) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._interval = max(1.0, min(60.0, float(interval)))
        self._stop.clear()
        self._cpu_max = self._mem_max = 0.0
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._bus.emit_app(
            AppEventKind.PERFORMANCE_MONITOR_STARTED,
            None,
            {"interval": self._interval, "scope": "process"},
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                snap = self._sample()
                with self._lock:
                    self._latest = snap
                    self._cpu_max = max(self._cpu_max, snap.process_cpu_percent)
                    self._mem_max = max(self._mem_max, snap.process_memory_bytes)
            except Exception:
                pass
            self._stop.wait(self._interval)

    def _sample(self) -> ProcessSnapshot:
        proc_cpu = 0.0
        proc_mem = 0
        child_count = 0
        child_cpu = 0.0
        child_mem = 0
        try:
            proc = psutil.Process(self._pid)
            proc.cpu_percent(interval=None)  # prime; first call returns 0.0
            try:
                proc_cpu = float(proc.cpu_percent(interval=None))
            except Exception:
                proc_cpu = 0.0
            try:
                proc_mem = int(proc.memory_info().rss)
            except Exception:
                proc_mem = 0
            try:
                children = proc.children(recursive=True)
            except Exception:
                children = []
            # Count browser-like children (chrome/headless_shell/chromium).
            for ch in children:
                try:
                    name = (ch.name() or "").lower()
                except Exception:
                    name = ""
                if any(b in name for b in ("chrome", "chromium", "headless")):
                    child_count += 1
                    try:
                        child_cpu += float(ch.cpu_percent(interval=None))
                    except Exception:
                        pass
                    try:
                        child_mem += int(ch.memory_info().rss)
                    except Exception:
                        pass
        except Exception:
            pass
        return ProcessSnapshot(
            timestamp=time.time(),
            process_cpu_percent=proc_cpu,
            process_memory_bytes=proc_mem,
            child_browser_count=child_count,
            child_cpu_percent=child_cpu,
            child_memory_bytes=child_mem,
        )

    def get_snapshot(self) -> Optional[ProcessSnapshot]:
        with self._lock:
            return self._latest

    def peak_cpu(self) -> float:
        with self._lock:
            return self._cpu_max

    def peak_memory_bytes(self) -> int:
        with self._lock:
            return self._mem_max


# --------------------------------------------------------------------------- #
# Persistence (PART 7) — additive tables in the shared SQLite DB
# --------------------------------------------------------------------------- #
class PerformanceStore:
    def __init__(self, db_path):
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS perf_machine_profile (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    captured_at REAL,
                    os_name TEXT, cpu_logical INTEGER, cpu_physical INTEGER,
                    total_ram_bytes INTEGER, total_disk_bytes INTEGER,
                    gpu_available INTEGER
                );
                CREATE TABLE IF NOT EXISTS perf_job_summary (
                    job_id TEXT PRIMARY KEY,
                    created_at TEXT, completed_at TEXT,
                    worker_count INTEGER, delay REAL,
                    network_mode TEXT, proxy_id TEXT,
                    total_urls INTEGER, processed INTEGER, successful INTEGER,
                    failed INTEGER, blocked INTEGER, rate_limited INTEGER,
                    elapsed_seconds REAL, avg_urls_per_min REAL,
                    avg_seconds_per_url REAL,
                    bottleneck_label TEXT, bottleneck_confidence TEXT
                );
                CREATE TABLE IF NOT EXISTS perf_job_sample (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT, timestamp REAL,
                    worker_count INTEGER, processed INTEGER, successful INTEGER,
                    failed INTEGER, blocked INTEGER, rate_limited INTEGER,
                    elapsed_seconds REAL, urls_per_min_current REAL,
                    urls_per_min_avg REAL, avg_seconds_per_url REAL, eta_seconds REAL
                );
                CREATE TABLE IF NOT EXISTS perf_config_outcome (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT, workers INTEGER, delay REAL,
                    network_mode TEXT, proxy_id TEXT,
                    processed INTEGER, successful INTEGER, failed INTEGER,
                    elapsed_seconds REAL, urls_per_min REAL
                );
                CREATE INDEX IF NOT EXISTS idx_perf_sample_job
                    ON perf_job_sample(job_id);
                CREATE INDEX IF NOT EXISTS idx_perf_outcome_workers
                    ON perf_config_outcome(workers);
                """
            )
            self._conn.commit()

    # -- machine profile --------------------------------------------------- #
    def save_machine_profile(self, caps: SystemCapabilities) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO perf_machine_profile
                (captured_at, os_name, cpu_logical, cpu_physical,
                 total_ram_bytes, total_disk_bytes, gpu_available)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    time.time(),
                    caps.os_name,
                    caps.cpu_logical,
                    caps.cpu_physical,
                    caps.total_ram_bytes,
                    caps.total_disk_bytes,
                    1 if caps.gpu_available else 0,
                ),
            )
            self._conn.commit()

    # -- job summary ------------------------------------------------------- #
    def save_job_summary(self, s: JobPerformanceSummary) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO perf_job_summary
                (job_id, created_at, completed_at, worker_count, delay,
                 network_mode, proxy_id, total_urls, processed, successful,
                 failed, blocked, rate_limited, elapsed_seconds,
                 avg_urls_per_min, avg_seconds_per_url, bottleneck_label,
                 bottleneck_confidence)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    s.job_id, s.created_at, s.completed_at, s.worker_count,
                    s.delay, s.network_mode, s.proxy_id, s.total_urls,
                    s.processed, s.successful, s.failed, s.blocked,
                    s.rate_limited, s.elapsed_seconds, s.avg_urls_per_min,
                    s.avg_seconds_per_url, s.bottleneck_label,
                    s.bottleneck_confidence,
                ),
            )
            self._conn.commit()

    # -- samples (capped) -------------------------------------------------- #
    def add_job_sample(self, sample: JobPerformanceSample, max_per_job: int) -> None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT COUNT(*) AS c FROM perf_job_sample WHERE job_id=?",
                (sample.job_id,),
            )
            count = cur.fetchone()["c"]
            self._conn.execute(
                """
                INSERT INTO perf_job_sample
                (job_id, timestamp, worker_count, processed, successful,
                 failed, blocked, rate_limited, elapsed_seconds,
                 urls_per_min_current, urls_per_min_avg, avg_seconds_per_url,
                 eta_seconds)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    sample.job_id, sample.timestamp, sample.worker_count,
                    sample.processed, sample.successful, sample.failed,
                    sample.blocked, sample.rate_limited, sample.elapsed_seconds,
                    sample.urls_per_min_current, sample.urls_per_min_avg,
                    sample.avg_seconds_per_url, sample.eta_seconds,
                ),
            )
            if count >= max_per_job:
                # Drop the oldest sample for this job to cap storage.
                self._conn.execute(
                    """
                    DELETE FROM perf_job_sample
                    WHERE job_id=? AND id = (
                        SELECT id FROM perf_job_sample
                        WHERE job_id=? ORDER BY id ASC LIMIT 1
                    )
                    """,
                    (sample.job_id, sample.job_id),
                )
            self._conn.commit()

    # -- config outcomes --------------------------------------------------- #
    def save_config_outcome(self, outcome: dict) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO perf_config_outcome
                (job_id, workers, delay, network_mode, proxy_id, processed,
                 successful, failed, elapsed_seconds, urls_per_min)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    outcome["job_id"], outcome["workers"], outcome["delay"],
                    outcome["network_mode"], outcome["proxy_id"],
                    outcome["processed"], outcome["successful"], outcome["failed"],
                    outcome["elapsed_seconds"], outcome["urls_per_min"],
                ),
            )
            self._conn.commit()

    # -- reads ------------------------------------------------------------- #
    def get_job_summary(self, job_id: str):
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM perf_job_summary WHERE job_id=?", (job_id,)
            ).fetchone()
        return self._row_to_summary(row) if row else None

    def get_latest_sample(self, job_id: str):
        with self._lock:
            row = self._conn.execute(
                """
                SELECT * FROM perf_job_sample
                WHERE job_id=? ORDER BY timestamp DESC LIMIT 1
                """,
                (job_id,),
            ).fetchone()
        return self._row_to_sample(row) if row else None

    def get_job_samples(self, job_id: str, limit: int, offset: int = 0):
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM perf_job_sample
                WHERE job_id=? ORDER BY timestamp DESC LIMIT ? OFFSET ?
                """,
                (job_id, int(limit), int(offset)),
            ).fetchall()
        return [self._row_to_sample(r) for r in rows]

    def get_summaries(self, limit: int, offset: int = 0):
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM perf_job_summary
                ORDER BY completed_at DESC, created_at DESC LIMIT ? OFFSET ?
                """,
                (int(limit), int(offset)),
            ).fetchall()
        return [self._row_to_summary(r) for r in rows]

    def count_summaries(self, job_id: Optional[str] = None) -> int:
        with self._lock:
            if job_id:
                return self._conn.execute(
                    "SELECT COUNT(*) AS c FROM perf_job_summary WHERE job_id=?",
                    (job_id,),
                ).fetchone()["c"]
            return self._conn.execute(
                "SELECT COUNT(*) AS c FROM perf_job_summary"
            ).fetchone()["c"]

    def get_config_outcomes(self, min_processed: int = 1):
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM perf_config_outcome
                WHERE processed >= ? ORDER BY workers ASC, urls_per_min DESC
                """,
                (min_processed,),
            ).fetchall()
        return [dict(r) for r in rows]

    # -- retention --------------------------------------------------------- #
    def purge_old(self, days: int) -> int:
        cutoff = time.time() - max(1, int(days)) * 86400.0
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM perf_job_sample WHERE timestamp < ?", (cutoff,)
            )
            self._conn.execute(
                "DELETE FROM perf_job_summary WHERE "
                "COALESCE(completed_at, created_at) < ?",
                (str(cutoff),),
            )
            self._conn.commit()
            return cur.rowcount

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    # -- row helpers ------------------------------------------------------- #
    @staticmethod
    def _row_to_summary(row) -> JobPerformanceSummary:
        return JobPerformanceSummary(
            job_id=row["job_id"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
            worker_count=row["worker_count"],
            delay=row["delay"],
            network_mode=row["network_mode"],
            proxy_id=row["proxy_id"],
            total_urls=row["total_urls"],
            processed=row["processed"],
            successful=row["successful"],
            failed=row["failed"],
            blocked=row["blocked"],
            rate_limited=row["rate_limited"],
            elapsed_seconds=row["elapsed_seconds"],
            avg_urls_per_min=row["avg_urls_per_min"],
            avg_seconds_per_url=row["avg_seconds_per_url"],
            bottleneck_label=row["bottleneck_label"],
            bottleneck_confidence=row["bottleneck_confidence"],
        )

    @staticmethod
    def _row_to_sample(row) -> JobPerformanceSample:
        return JobPerformanceSample(
            job_id=row["job_id"],
            timestamp=row["timestamp"],
            worker_count=row["worker_count"],
            processed=row["processed"],
            successful=row["successful"],
            failed=row["failed"],
            blocked=row["blocked"],
            rate_limited=row["rate_limited"],
            elapsed_seconds=row["elapsed_seconds"],
            urls_per_min_current=row["urls_per_min_current"],
            urls_per_min_avg=row["urls_per_min_avg"],
            avg_seconds_per_url=row["avg_seconds_per_url"],
            eta_seconds=row["eta_seconds"],
        )


# --------------------------------------------------------------------------- #
# Analysis (PART 9 / 10 / 11)
# --------------------------------------------------------------------------- #
class PerformanceAnalyzer:
    @staticmethod
    def compare_workers(outcomes: list[dict]) -> dict:
        """Group config outcomes by worker count; report mean throughput."""
        by_workers: dict[int, list[dict]] = {}
        for o in outcomes:
            by_workers.setdefault(int(o["workers"]), []).append(o)
        result = {}
        for w, items in sorted(by_workers.items()):
            ups = [o["urls_per_min"] for o in items if o["urls_per_min"] is not None]
            succ = [o["successful"] for o in items]
            total = [o["processed"] for o in items]
            blk = [o.get("blocked", 0) for o in items]
            rl = [o.get("rate_limited", 0) for o in items]
            n = len(items)
            result[w] = {
                "samples": n,
                "mean_urls_per_min": round(sum(ups) / len(ups), 3) if ups else 0.0,
                "mean_successful": round(sum(succ) / n, 2),
                "mean_processed": round(sum(total) / n, 2),
                "mean_blocked": round(sum(blk) / n, 2),
                "mean_rate_limited": round(sum(rl) / n, 2),
            }
        return result

    @staticmethod
    def diminishing_returns(comparison: dict) -> tuple[Optional[int], str]:
        """Find the worker count where marginal throughput gain collapses.

        Returns (safe_max_workers, basis). Conservative: requires >=3 worker
        levels with data to claim an Observed plateau.
        """
        levels = sorted(comparison.keys())
        if not levels:
            return None, BASIS_INSUFFICIENT
        if len(levels) < 2:
            return levels[-1], BASIS_ESTIMATED
        prev = comparison[levels[0]]["mean_urls_per_min"]
        safe = levels[0]
        for w in levels[1:]:
            cur = comparison[w]["mean_urls_per_min"]
            if prev > 0 and (cur - prev) / prev < 0.10:  # <10% marginal gain
                break
            safe = w
            prev = cur
        basis = BASIS_OBSERVED if len(levels) >= 3 else BASIS_ESTIMATED
        return safe, basis

    @staticmethod
    def detect_bottleneck(
        summary: JobPerformanceSummary,
        process_peak_cpu: float,
        process_peak_mem_bytes: int,
        total_ram_bytes: int,
        comparison: Optional[dict] = None,
    ) -> tuple[str, str]:
        """Conservative, rule-based bottleneck label. Never asserts causation."""
        processed = max(1, summary.processed)
        block_rate = (summary.blocked + summary.rate_limited) / processed

        # Network throttling signal (Instagram blocking / rate limiting).
        if block_rate >= 0.30:
            return BOTTLENECK_NETWORK_LIMITED, CONF_LIKELY
        if block_rate >= 0.10:
            return BOTTLENECK_NETWORK_LIMITED, CONF_POSSIBLE

        # Memory pressure on the Reelminner process.
        if total_ram_bytes > 0:
            mem_ratio = process_peak_mem_bytes / total_ram_bytes
            if mem_ratio >= 0.90:
                return BOTTLENECK_MEMORY_BOUND, CONF_LIKELY
            if mem_ratio >= 0.75:
                return BOTTLENECK_MEMORY_BOUND, CONF_POSSIBLE

        # CPU saturation on the Reelminner process.
        if process_peak_cpu >= 90.0:
            return BOTTLENECK_CPU_BOUND, CONF_POSSIBLE

        # Throughput plateaus as workers grow -> scraper/worker saturation.
        if comparison:
            safe, _ = PerformanceAnalyzer.diminishing_returns(comparison)
            if safe is not None and safe < summary.worker_count:
                return BOTTLENECK_SCRAPER_LIMITED, CONF_POSSIBLE

        return BOTTLENECK_UNKNOWN, CONF_UNKNOWN


# --------------------------------------------------------------------------- #
# Recommendation engine (PART 12 / 13 / 14)
# --------------------------------------------------------------------------- #
class RecommendationEngine:
    def __init__(self, caps: SystemCapabilities):
        self._caps = caps

    def recommend_workers(self, outcomes: list[dict]) -> PerformanceRecommendation:
        """Advise a safe worker count from REAL job outcomes only.

        No synthetic benchmarks, no autonomous stress testing.
        """
        if not outcomes:
            return PerformanceRecommendation(
                kind="worker_count",
                basis=BASIS_INSUFFICIENT,
                confidence=CONF_UNKNOWN,
                message=(
                    "Insufficient data: run jobs with different worker counts "
                    "to receive a data-driven worker recommendation."
                ),
                suggested_workers=None,
            )
        comparison = PerformanceAnalyzer.compare_workers(outcomes)
        safe, basis = PerformanceAnalyzer.diminishing_returns(comparison)
        cpu_cap = max(1, self._caps.cpu_logical)
        if safe is None:
            return PerformanceRecommendation(
                kind="worker_count",
                basis=BASIS_ESTIMATED,
                confidence=CONF_POSSIBLE,
                message=(
                    "Limited data: a tested worker count could not be derived; "
                    "keep worker counts within your logical CPU count "
                    f"({cpu_cap}) unless observed otherwise."
                ),
                suggested_workers=min(3, cpu_cap),
            )
        suggested = min(safe, cpu_cap)
        note = (
            f"Observed throughput plateau near {safe} workers across "
            f"{len(comparison)} worker levels"
            if basis == BASIS_OBSERVED
            else f"Estimated safe maximum near {safe} workers (limited data)"
        )
        return PerformanceRecommendation(
            kind="worker_count",
            basis=basis,
            confidence=CONF_LIKELY if basis == BASIS_OBSERVED else CONF_POSSIBLE,
            message=(
                f"{note}. Suggested worker count capped at logical CPUs "
                f"({cpu_cap}). This is a recommendation only — no running job "
                "or setting is changed automatically."
            ),
            suggested_workers=suggested,
        )

    def recommend_from_summary(
        self, summary: JobPerformanceSummary, outcomes: list[dict]
    ) -> list[PerformanceRecommendation]:
        recs: list[PerformanceRecommendation] = []
        label, conf = PerformanceAnalyzer.detect_bottleneck(
            summary, 0.0, 0, self._caps.total_ram_bytes
        )
        if label == BOTTLENECK_NETWORK_LIMITED:
            recs.append(
                PerformanceRecommendation(
                    kind="network",
                    basis=BASIS_OBSERVED if conf == CONF_LIKELY else BASIS_ESTIMATED,
                    confidence=conf,
                    message=(
                        "High block/rate-limit rate observed. Consider a higher "
                        "delay or a proxy rotation strategy. Correlation only — "
                        "this does not prove Instagram throttling."
                    ),
                )
            )
        elif label == BOTTLENECK_MEMORY_BOUND:
            recs.append(
                PerformanceRecommendation(
                    kind="memory",
                    basis=BASIS_ESTIMATED,
                    confidence=conf,
                    message=(
                        "Process memory pressure observed. Consider fewer "
                        "concurrent workers or headless mode. Correlation only."
                    ),
                )
            )
        elif label == BOTTLENECK_CPU_BOUND:
            recs.append(
                PerformanceRecommendation(
                    kind="cpu",
                    basis=BASIS_ESTIMATED,
                    confidence=conf,
                    message=(
                        "Process CPU saturation observed. Consider fewer "
                        "concurrent workers. Correlation only."
                    ),
                )
            )
        recs.append(self.recommend_workers(outcomes))
        return recs


# --------------------------------------------------------------------------- #
# Facade (PART 3.6 integration root)
# --------------------------------------------------------------------------- #
class PerformanceService:
    """Held by ReelminnerApplication.performance. Read-only by design."""

    def __init__(self, data_dir, db_path, event_bus: ApplicationEventBus, settings):
        self._data_dir = data_dir
        self._event_bus = event_bus
        self._settings = settings
        self._caps = detect_capabilities()
        perf = settings.get().performance
        self._system = SystemMonitor(
            event_bus, gpu_enabled=bool(perf.gpu_monitoring_enabled)
        )
        self._runtime = RuntimeMonitor(event_bus)
        self._store = PerformanceStore(db_path)
        self._analyzer = PerformanceAnalyzer()
        self._rec_engine = RecommendationEngine(self._caps)
        self._last_sample_at: dict[str, float] = {}
        self._lock = threading.Lock()
        self._monitoring = False

    # -- capabilities ------------------------------------------------------ #
    def get_capabilities(self) -> SystemCapabilities:
        return self._caps

    # -- monitoring lifecycle --------------------------------------------- #
    def start_monitoring(self) -> None:
        if self._monitoring:
            return
        perf = self._settings.get().performance
        interval = max(1.0, min(60.0, float(perf.sampling_interval)))
        if bool(perf.monitoring_enabled):
            self._system.start(interval)
        if bool(perf.process_monitoring_enabled):
            self._runtime.start(interval)
        self._monitoring = True
        try:
            self._store.save_machine_profile(self._caps)
        except Exception:
            pass

    def stop_monitoring(self) -> None:
        self._system.stop()
        self._runtime.stop()
        if self._monitoring:
            self._monitoring = False
            self._event_bus.emit_app(
                AppEventKind.PERFORMANCE_MONITOR_STOPPED, None, {}
            )

    def get_system_snapshot(self) -> Optional[dict]:
        s = self._system.get_snapshot()
        return s.to_dict() if s else None

    def get_process_snapshot(self) -> Optional[dict]:
        p = self._runtime.get_snapshot()
        return p.to_dict() if p else None

    # -- job hooks (called by JobManager, non-raising) -------------------- #
    def record_job_start(self, job) -> None:
        try:
            self._last_sample_at[job.id] = time.time()
        except Exception:
            pass

    def record_job_progress(self, run, done: int, total: int) -> None:
        try:
            perf = self._settings.get().performance
            if not bool(perf.monitoring_enabled):
                return
            interval = max(1.0, min(60.0, float(perf.sampling_interval)))
            now = time.time()
            last = self._last_sample_at.get(run.job_id, 0.0)
            if now - last < interval:
                return  # throttle: avoid excessive DB writes
            self._last_sample_at[run.job_id] = now
            sample = self._build_sample(run.job, done, total, prev_done=0)
            self._store.add_job_sample(sample, int(perf.max_samples_per_job))
        except Exception:
            pass

    def record_job_end(self, job) -> None:
        try:
            summary = self._build_summary(job)
            # Bottleneck detection uses peaks captured during this session.
            proc_peak_cpu = self._runtime.peak_cpu()
            proc_peak_mem = self._runtime.peak_memory_bytes()
            outcomes = self._store.get_config_outcomes(min_processed=1)
            comparison = self._analyzer.compare_workers(outcomes)
            label, conf = self._analyzer.detect_bottleneck(
                summary, proc_peak_cpu, proc_peak_mem,
                self._caps.total_ram_bytes, comparison,
            )
            summary.bottleneck_label = label
            summary.bottleneck_confidence = conf
            self._store.save_job_summary(summary)
            self._store.save_config_outcome(
                {
                    "job_id": summary.job_id,
                    "workers": summary.worker_count,
                    "delay": summary.delay,
                    "network_mode": summary.network_mode,
                    "proxy_id": summary.proxy_id,
                    "processed": summary.processed,
                    "successful": summary.successful,
                    "failed": summary.failed,
                    "elapsed_seconds": summary.elapsed_seconds,
                    "urls_per_min": summary.avg_urls_per_min,
                }
            )
            self._event_bus.emit_app(
                AppEventKind.JOB_PERFORMANCE_RECORDED,
                summary.job_id,
                {
                    "workers": summary.worker_count,
                    "urls_per_min": summary.avg_urls_per_min,
                },
            )
            recs = self._rec_engine.recommend_from_summary(summary, outcomes)
            if recs:
                self._event_bus.emit_app(
                    AppEventKind.PERFORMANCE_RECOMMENDATION_AVAILABLE,
                    summary.job_id,
                    {"basis": recs[-1].basis},
                )
        except Exception:
            pass

    # -- sample / summary builders (PART 5 formulas) ---------------------- #
    def _build_sample(self, job, done: int, total: int, prev_done: int = 0):
        started = getattr(job, "started_at", None)
        elapsed = 0.0
        if started:
            try:
                elapsed = max(0.0, time.time() - float(started))
            except Exception:
                elapsed = 0.0
        processed = getattr(job, "processed_items", 0)
        successful = getattr(job, "successful_items", 0)
        failed = getattr(job, "failed_items", 0)
        blocked = getattr(job, "blocked_items", 0)
        rate_limited = getattr(job, "rate_limited_items", 0)
        avg_per_min = (processed / elapsed * 60.0) if elapsed > 0 else 0.0
        delta = max(0, done - prev_done)
        cur_per_min = 0.0
        # current rate derived from progress callback delta over a nominal tick
        if elapsed > 0 and getattr(job, "total_items", 0) > 0:
            cur_per_min = avg_per_min  # conservative: use avg when per-tick unknown
        avg_sec_per_url = (elapsed / processed) if processed > 0 else None
        eta = None
        if avg_per_min > 0 and getattr(job, "total_items", 0) > processed:
            remaining = max(0, getattr(job, "total_items", 0) - processed)
            eta = remaining / avg_per_min * 60.0
        return JobPerformanceSample(
            job_id=job.id,
            timestamp=time.time(),
            worker_count=int(getattr(job.config, "workers", 0)),
            delay=float(getattr(job.config, "delay", 0.0)),
            network_mode=getattr(job.config, "network_mode", None).value
            if getattr(job.config, "network_mode", None) is not None
            else "direct",
            proxy_id=getattr(job.config, "proxy_id", None),
            processed=processed,
            successful=successful,
            failed=failed,
            blocked=blocked,
            rate_limited=rate_limited,
            elapsed_seconds=elapsed,
            urls_per_min_current=cur_per_min,
            urls_per_min_avg=avg_per_min,
            avg_seconds_per_url=avg_sec_per_url,
            eta_seconds=eta,
        )

    def _build_summary(self, job) -> JobPerformanceSummary:
        started = getattr(job, "started_at", None)
        completed = getattr(job, "completed_at", None) or getattr(
            job, "ended_at", None
        )
        elapsed = 0.0
        if started:
            try:
                end = time.time() if completed is None else float(completed)
                elapsed = max(0.0, end - float(started))
            except Exception:
                elapsed = 0.0
        processed = getattr(job, "processed_items", 0)
        successful = getattr(job, "successful_items", 0)
        failed = getattr(job, "failed_items", 0)
        blocked = getattr(job, "blocked_items", 0)
        rate_limited = getattr(job, "rate_limited_items", 0)
        total = getattr(job, "total_items", 0)
        avg_per_min = (processed / elapsed * 60.0) if elapsed > 0 else 0.0
        avg_sec_per_url = (elapsed / processed) if processed > 0 else None
        nm = getattr(job.config, "network_mode", None)
        return JobPerformanceSummary(
            job_id=job.id,
            created_at=getattr(job, "created_at", None),
            completed_at=completed,
            worker_count=int(getattr(job.config, "workers", 0)),
            delay=float(getattr(job.config, "delay", 0.0)),
            network_mode=nm.value if nm is not None else "direct",
            proxy_id=getattr(job.config, "proxy_id", None),
            total_urls=total,
            processed=processed,
            successful=successful,
            failed=failed,
            blocked=blocked,
            rate_limited=rate_limited,
            elapsed_seconds=elapsed,
            avg_urls_per_min=avg_per_min,
            avg_seconds_per_url=avg_sec_per_url,
        )

    # -- queries (MCP) ----------------------------------------------------- #
    def get_job_performance(self, job_id: str) -> Optional[dict]:
        summary = self._store.get_job_summary(job_id)
        latest = self._store.get_latest_sample(job_id)
        job = None
        return {
            "job_id": job_id,
            "summary": summary.to_dict() if summary else None,
            "latest_sample": latest.to_dict() if latest else None,
            "system_snapshot": self.get_system_snapshot(),
            "process_snapshot": self.get_process_snapshot(),
        }

    def get_history(self, job_id: Optional[str], limit: int, offset: int) -> dict:
        limit = max(1, min(500, int(limit)))
        offset = max(0, int(offset))
        if job_id:
            summaries = [self._store.get_job_summary(job_id)]
            summaries = [s for s in summaries if s]
            samples = self._store.get_job_samples(job_id, limit, offset)
            return {
                "job_id": job_id,
                "summaries": [s.to_dict() for s in summaries],
                "samples": [s.to_dict() for s in samples],
                "total_samples": self._store.count_summaries(job_id),
            }
        summaries = self._store.get_summaries(limit, offset)
        return {
            "summaries": [s.to_dict() for s in summaries],
            "count": len(summaries),
            "total": self._store.count_summaries(),
        }

    def get_worker_recommendation(self) -> dict:
        outcomes = self._store.get_config_outcomes(min_processed=1)
        rec = self._rec_engine.recommend_workers(outcomes)
        return rec.to_dict()

    def get_recommendations(self, job_id: Optional[str] = None) -> dict:
        outcomes = self._store.get_config_outcomes(min_processed=1)
        if job_id:
            summary = self._store.get_job_summary(job_id)
            if summary is None:
                return {"job_id": job_id, "recommendations": []}
            recs = self._rec_engine.recommend_from_summary(summary, outcomes)
            return {
                "job_id": job_id,
                "recommendations": [r.to_dict() for r in recs],
            }
        # Global: worker recommendation only.
        rec = self._rec_engine.recommend_workers(outcomes)
        return {"recommendations": [rec.to_dict()]}

    def purge_old(self, days: int) -> int:
        return self._store.purge_old(days)

    def close(self) -> None:
        self.stop_monitoring()
        try:
            self._store.close()
        except Exception:
            pass
