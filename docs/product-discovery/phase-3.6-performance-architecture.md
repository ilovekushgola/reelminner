# Phase 3.6 — Performance Intelligence & Compute Monitoring: Architecture

> Status: DESIGN (Part 1). Implementation starts only after this document is
> internally consistent with the existing Phase 1–3.5 architecture.
> Backend-only. No UI, no Electron/Tauri/React, no installer, no EXE packaging.

## 0. Scope & Non-Goals (hard constraints)

**Build:**
- Read-only compute/performance observability for the local Reelminner process
  and the jobs it runs.
- Capability detection, real-time system + process monitoring, per-job
  performance sampling, persisted summaries/history, rule-based bottleneck
  detection, and a conservative recommendation engine.
- A thin `.performance` facade on `ReelminnerApplication` and 6 MCP tools.

**Explicitly NOT built (non-goals, do not implement):**
- Automatic worker scaling / auto-tuning of running jobs.
- Autonomous stress testing, artificial Instagram benchmarks, fake metrics.
- AI/ML recommendations or any external API/cloud telemetry.
- Collection of personal data (user names, file contents, browsing history,
  credentials, cookies, proxy secrets).
- Any UI, desktop shell, installer, or packaging step.

**Core rule:** the system only *observes* and *recommends*. It never changes
running jobs or settings without an explicit, separate user action.

---

## 1. Integration points inspected (current state, ground truth)

| Concern | Location | How Phase 3.6 plugs in |
|---|---|---|
| Composition root | `app.py :: ReelminnerApplication` | Add `self.performance` facade; wire `JobManager.performance_recorder`. |
| Settings persistence | `settings.py :: SettingsService` (`app_settings` JSON blob in `JobStore`) | Add `PerformanceSettings` dataclass + `performance_*` validation. |
| Settings access | `app.settings.get_all()` / `update_bulk({"performance": {...}})` | New `performance` section, flat keys `performance_monitoring_enabled` etc. |
| Event bus | `app_events.py :: ApplicationEventBus.emit_app(kind, job_id, payload)` | Add `PERFORMANCE_*` kinds; bus already exists. |
| Job lifecycle | `job_manager.py :: JobManager` (`start_job`, `_run`, finalize methods) | Optional `performance_recorder` hook (same pattern as `proxy_resolver`). |
| Job→dict | `job_manager.py :: job_to_dict(job)` | Reused by `get_job_performance`. |
| SQLite store | `storage.py :: JobStore` (`init_schema`, `get_setting`/`set_setting`) | Extend `init_schema` with 4 `perf_*` tables; reuse same DB. |
| MCP surface | `mcp_server.py :: @mcp.tool()`, `registered_tools()` | Add 6 tools; update `test_mcp_server.EXPECTED_TOOLS`. |
| Proxy metadata | `proxies.py :: to_safe_dict()` | Job samples store `network_mode` + `proxy_id` (never credentials). |

Key facts confirmed:
- `emit_app` (not `emit`) must be used for app events — `emit` drops app events.
- `proxy_id`/`network_mode` already exist on `JobConfig`; samples reuse them.
- `JobConfig` is a JSON blob, so no DB migration is required for new sample fields.
- `ReelminnerApplication.get_instance()` singleton already exists for MCP/tests.

---

## 2. Component map

```
ReelminnerApplication
└── .performance  (PerformanceService — facade)
      ├── SystemCapabilities   (typed snapshot of machine: OS/CPU/RAM/disk/GPU-best-effort)
      ├── SystemMonitor        (background thread: periodic SystemSnapshot)
      ├── RuntimeMonitor       (background thread: Reelminner process + child browsers)
      ├── PerformanceStore     (writes perf_* tables in the shared SQLite DB)
      ├── PerformanceAnalyzer  (compare worker counts / detect bottlenecks / diminishing returns)
      └── RecommendationEngine (rule-based, Observed/Estimated/Insufficient-Data)

JobManager ──(performance_recorder hook)──▶ PerformanceService.record_job_*()
MCP tools ──▶ app.performance.*  (read-only)
```

### 2.1 `SystemCapabilities` (PART 2)
Typed `@dataclass` describing the host once at startup (and re-detectable):
- `os_name`, `os_version`, `arch`, `python_version`
- `cpu_logical`, `cpu_physical`, `cpu_model` (best-effort, may be UNKNOWN)
- `total_ram_bytes`, `total_disk_bytes`
- `gpu_available` (bool, best-effort; never a hard dependency)
- No PII: no hostname, username, IP, MAC, serial numbers, or file contents.

### 2.2 `SystemMonitor` (PART 3)
- `start(interval=settings.performance.sampling_interval)`, `stop()`, `get_snapshot()`.
- Default interval 5s; clamped to 1–60s.
- `SystemSnapshot`: `timestamp`, `cpu_percent` (interval-based), `memory_percent`,
  `memory_used_bytes`, `disk_used_percent`, `net_sent_bytes`, `net_recv_bytes`,
  `gpu_percent` (optional/None).
- Uses `psutil` (confirmed installed: 7.2.2). All reads wrapped in try/except —
  monitor degrades gracefully if a metric is unavailable.

### 2.3 `RuntimeMonitor` (PART 4, process monitoring)
- Watches the current process (`psutil.Process(os.getpid())`) and its children.
- Reports: `process_cpu_percent`, `process_memory_bytes`, `child_browser_count`,
  `child_cpu_percent`, `child_memory_bytes`.
- If psutil cannot resolve children (e.g. browser not launched yet), values are
  `0`/`None` — never raises, never blocks the main app.
- Lives behind `performance.process_monitoring_enabled`.

### 2.4 `JobPerformanceSample` (PART 5 + 6)
Captured periodically (throttled by `performance.sampling_interval`) and on
finalize. Fields:
- `job_id`, `timestamp`, `worker_count`, `delay`, `network_mode`, `proxy_id`
- `processed`, `successful`, `failed`, `blocked`, `rate_limited`
- `elapsed_seconds`, `urls_per_min_current`, `urls_per_min_avg`,
  `avg_seconds_per_url`, `eta_seconds`
- **Formulas (documented, div-by-zero safe):**
  - `elapsed = max(0, now - started_at)`
  - `urls_per_min_avg = (processed / elapsed * 60) if elapsed > 0 else 0`
  - `urls_per_min_current = (processed_since_last_sample / interval * 60)` (guarded)
  - `avg_seconds_per_url = (elapsed / processed) if processed > 0 else None`
  - `eta_seconds = ((total - processed) / urls_per_min_avg * 60) if urls_per_min_avg > 0 else None`
- Works for every job state (created/running/paused/stopped/failed/completed)
  because it reads live counters; pending jobs emit a sample with zeros.

### 2.5 `PerformanceStore` (PART 7)
- **Decision: extend the existing shared SQLite DB** (`JobStore` DB path) with
  four new tables created in `JobStore.init_schema` via `CREATE TABLE IF NOT EXISTS`.
  Rationale: one source of truth, one file, no new credentials, survives restart,
  and the existing `StorageError`/transaction pattern is reused.
- Tables:
  - `perf_machine_profile(job_id NULL, captured_at, os_name, cpu_logical, cpu_physical, total_ram_bytes, total_disk_bytes, gpu_available)` — one row per app start (or per job if capabilities are re-detected).
  - `perf_job_summary(job_id PK, created_at, completed_at, worker_count, delay, network_mode, proxy_id, total_urls, processed, successful, failed, blocked, rate_limited, elapsed_seconds, avg_urls_per_min, avg_seconds_per_url, bottleneck_label, bottleneck_confidence)` — generated on finalize.
  - `perf_job_sample(id PK, job_id, timestamp, worker_count, processed, successful, failed, blocked, rate_limited, elapsed_seconds, urls_per_min_current, urls_per_min_avg, avg_seconds_per_url, eta_seconds)` — capped at `max_samples_per_job`.
  - `perf_config_outcome(id PK, job_id, workers, delay, network_mode, proxy_id, processed, successful, failed, elapsed_seconds, urls_per_min)` — used for cross-job worker comparison.
- Retention: a `purge_old(days)` method removes rows older than
  `performance.history_retention_days`.

### 2.6 `JobPerformanceSummary` (PART 8)
- Built on job finalize (complete/stop/fail) from the counters + samples.
- Persisted to `perf_job_summary` and `perf_config_outcome`.
- Survives restart (it is in SQLite). Does not alter existing job persistence
  (`perf_*` tables are additive; no schema change to `jobs`/`results`).

### 2.7 `PerformanceAnalyzer` (PART 9 + 10 + 11)
- `compare_workers()` — groups `perf_config_outcome` by worker count, computes
  mean `urls_per_min`, success rate, blocked/rate-limited rate.
- `detect_bottleneck(summary_or_samples)` — rule-based, returns
  `{label, confidence}` where `confidence ∈ {LIKELY, POSSIBLE, UNKNOWN}`:
  - `CPU_BOUND` — `process_cpu_percent` consistently ≥ 85% AND throughput flat vs workers.
  - `MEMORY_BOUND` — `process_memory_bytes / total_ram` ≥ 90%.
  - `NETWORK_LIMITED` — high blocked/rate_limited rate OR low `urls_per_min` with low CPU.
  - `SCRAPER_LIMITED` — throughput saturates as workers grow (diminishing returns).
  - `UNKNOWN` — insufficient evidence.
- `diminishing_returns()` — finds the worker count where marginal `urls_per_min`
  gain drops below a threshold; marks `safe_max_workers` as **Observed** when
  backed by ≥3 data points, else **Estimated** / **Insufficient-Data**.
- All outputs use correlation≠causation language (see §5).

### 2.8 `RecommendationEngine` (PART 12 + 13 + 14)
- Pure rule function over `PerformanceAnalyzer` outputs + current `SystemCapabilities`.
- Returns `PerformanceRecommendation(basis, confidence, message, suggested_workers?)`.
- `basis ∈ {Observed, Estimated, Insufficient-Data}`.
- **No fabricated confidence.** If data is thin, `basis = Insufficient-Data` and
  the message states exactly what is missing.
- Benchmarks (PART 14): only *real-job comparison* — reusing `perf_config_outcome`.
  No synthetic/fake benchmarks, no autonomous stress testing.

---

## 3. Wiring into `ReelminnerApplication` (composition root)

```python
self.performance = PerformanceService(
    data_dir=self.data_dir,
    db_path=self._db_path,
    event_bus=self.event_bus,
    settings=self.settings,
)
# JobManager already accepts optional hooks:
self.jobs = JobManager(..., performance_recorder=self.performance)
```

`PerformanceService` exposes:
- `get_capabilities()`, `start_monitoring()`, `stop_monitoring()`,
  `get_system_snapshot()`, `get_process_snapshot()`,
  `record_job_start(job)`, `record_job_progress(run, done, total)`,
  `record_job_end(job)`, `get_job_performance(job_id)`,
  `get_history(job_id=None, limit, offset)`, `get_worker_recommendation()`,
  `get_recommendations()`.

`JobManager` calls (non-raising, throttled):
- `performance.record_job_start(job)` in `start_job`/`resume_job`
- `performance.record_job_progress(run, done, total)` inside `_make_progress_cb`
  (throttled to `sampling_interval`)
- `performance.record_job_end(job)` in each `_finalize_*` method

This mirrors the existing `proxy_resolver`/`on_proxy_used` hook pattern — no
business logic duplicated, facade remains the composition root.

---

## 4. Settings (PART 15)

New section `performance` in `Settings`, flat keys validated in
`SettingsService.validate`:
| Key | Default | Range |
|---|---|---|
| `performance_monitoring_enabled` | `True` | bool |
| `performance_sampling_interval` | `5.0` | 1.0–60.0 (s) |
| `performance_history_retention_days` | `30` | 1–365 |
| `performance_max_samples_per_job` | `100` | 10–1000 |
| `performance_process_monitoring_enabled` | `True` | bool |
| `performance_gpu_monitoring_enabled` | `False` | bool |

---

## 5. Analysis & recommendation methodology (conservative)

- **Correlation ≠ causation.** Every recommendation text includes a hedge
  ("observed", "may", "likely"). Never states "X caused Y".
- **Confidence labels:** `LIKELY` (clear signal across ≥3 samples/jobs),
  `POSSIBLE` (one signal present), `UNKNOWN` (insufficient data).
- **Basis labels:** `Observed` (real job data exists), `Estimated` (extrapolated
  from partial data), `Insufficient-Data` (not enough to advise).
- **No auto-change:** recommendations are returned to the caller only. The MCP
  tools and the engine never mutate `workers`/`delay`/running jobs.

---

## 6. Events (PART 16)

New `AppEventKind` members (payloads are safe metadata only — no samples, no
credentials, no per-sample flooding):
- `PERFORMANCE_MONITOR_STARTED {"interval"}`
- `PERFORMANCE_MONITOR_STOPPED {}`
- `PERFORMANCE_WARNING {"kind", "message"}` (throttled, e.g. memory ≥ 90%)
- `PERFORMANCE_RECOMMENDATION_AVAILABLE {"job_id"? , "basis"}`
- `JOB_PERFORMANCE_RECORDED {"job_id", "workers", "urls_per_min"}`

---

## 7. MCP tools (PART 17)

Six read-only tools, app-layer only, backward compatible:
1. `get_system_capabilities() -> dict` — `SystemCapabilities`.
2. `get_system_performance(include_process: bool = True) -> dict` — latest
   `SystemSnapshot` + optional `RuntimeMonitor` snapshot.
3. `get_job_performance(job_id: str) -> dict` — summary + latest sample + ETA.
4. `get_performance_history(job_id: Optional[str], limit: int, offset: int) -> dict`
   — paginated summaries/samples (no raw per-sample flooding).
5. `get_worker_recommendation() -> dict` — current-capacity recommendation
   (`Observed`/`Estimated`/`Insufficient-Data`).
6. `get_performance_recommendations() -> dict` — list of recommendations.

All return JSON-serializable dicts; none touch credentials or cookies.

---

## 8. Privacy (PART 18, full doc: `phase-3.6-performance-privacy.md`)

- No hostname, username, IP, MAC, serial, geolocation.
- No cookie/credential/proxy-secret content. Only `network_mode` + `proxy_id`.
- No scraping target URLs stored in perf tables (only counts).
- GPU is best-effort and never required.
- All persisted data is local SQLite, git-ignored alongside `data/`.

---

## 9. Storage decision summary (PART 7 resolution)

Extend `JobStore.init_schema` with `perf_machine_profile`, `perf_job_summary`,
`perf_job_sample`, `perf_config_outcome`. No migration of existing tables;
additive only. Reuses `StorageError`, transactions, and the single DB file.
This satisfies "history survives restart" and "no break to existing job
persistence".

---

## 10. Implementation order (post-design)

PART 2 → 3 → 4 → 5/6 → 7 → 8 → 9/10/11 → 12/13/14 → 15 → 16 → 17 → 18 →
tests → final report. Each part keeps the contracts above.

## 11. Definition-of-Done crosswalk

| DoD | Addressed by |
|---|---|
| Capability detection | §2.1 / `SystemCapabilities` |
| Real-time monitoring | §2.2–2.3 |
| Process monitoring | §2.3 `RuntimeMonitor` |
| Graceful degradation | §2.2–2.3 (try/except everywhere) |
| Efficient job samples | §2.4 (throttled, capped) |
| Persisted summaries | §2.5–2.6 |
| History survives restart | §2.5 (SQLite) |
| Worker comparison | §2.7 `compare_workers` |
| Diminishing returns | §2.7 |
| Conservative labels | §5 (LIKELY/POSSIBLE/UNKNOWN) |
| Data-driven recs | §2.8 (Observed/Estimated/Insufficient-Data) |
| No auto-changes | §5 |
| Configurable settings | §4 |
| App-layer access | §3 |
| MCP querying | §7 |
| Backward-compatible MCP | §7 (additive) |
| No sensitive leaks | §8 |
| Regression passes | tests |
| 8 docs complete | Parts 1 + 18 + others |
