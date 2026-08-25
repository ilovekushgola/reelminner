# Phase 3.6 — Monitoring Design

> Companion to `phase-3.6-performance-architecture.md`. Describes the live
> monitoring layer: `SystemMonitor`, `RuntimeMonitor`, per-job sampling, and the
> events they emit. Backend-only; no UI.

## 1. Two cooperating monitors

Both monitors are thin background threads managed by `PerformanceService`
(facade on `ReelminnerApplication.performance`). They are started together by
`PerformanceService.start_monitoring()` (called from `ReelminnerApplication.__init__`)
and stopped by `close()`.

| Monitor | Scope | Key metrics | Degrades to |
|---|---|---|---|
| `SystemMonitor` | Whole machine | cpu%, mem%, disk%, net I/O, GPU% (optional) | `0.0`/`None` per metric on any psutil error |
| `RuntimeMonitor` | Reelminner process + children | process cpu% / rss, child browser count, child cpu% / rss | `0`/`None` if psutil cannot resolve the process |

Both threads are `daemon=True` and wrap **every** measurement in try/except, so a
missing metric, a denied syscall, or an unmounted disk never crashes the app or
blocks the main scraper thread.

## 2. Sampling interval & throttling

- Configurable via `performance.sampling_interval` (default 5.0s, clamped to
  1.0–60.0s). Read from `SettingsService` at start time.
- The monitor loop samples **immediately** on start, then sleeps the interval.
  So a snapshot is available within ~0ms of start and refreshed every interval.
- `SystemMonitor` tracks `peak_cpu()` / `peak_memory()` across the session; these
  peaks feed bottleneck detection at job finalize (real signals, not guessed).
- `RuntimeMonitor` tracks `peak_cpu()` / `peak_memory_bytes()` for the process.

## 3. Process / browser monitoring (PART 4)

`RuntimeMonitor` resolves `psutil.Process(os.getpid())`, primes cpu accounting,
then walks `proc.children(recursive=True)`. A child is counted as a *browser*
when its process name contains `chrome`, `chromium`, or `headless`. Browser
count + aggregate child CPU/rss are reported. If the browser is not yet spawned
(e.g. job queued), values are `0` — never an error.

## 4. Per-job performance sampling (PART 5 / 6)

`JobManager` calls the performance hook (same pattern as the proxy hook):

- `record_job_start(job)` — stamps the start time for throttling.
- `record_job_progress(run, done, total)` — called from the scraper progress
  callback, but **throttled** to `performance.sampling_interval` so we do not
  write a DB row per URL. Builds a `JobPerformanceSample` and stores it (capped at
  `performance.max_samples_per_job` per job).
- `record_job_end(job)` — builds the `JobPerformanceSummary`, detects the
  bottleneck, persists the summary + a `perf_config_outcome` row, and emits
  `JOB_PERFORMANCE_RECORDED` (+ `PERFORMANCE_RECOMMENDATION_AVAILABLE` if any).

### Sample formulas (div-by-zero safe)

```
elapsed            = max(0, now - job.started_at)
urls_per_min_avg   = (processed / elapsed) * 60      if elapsed > 0 else 0
urls_per_min_current = urls_per_min_avg             (conservative: per-tick
                                                     delta is unknown from the
                                                     progress callback, so avg
                                                     is reported instead)
avg_seconds_per_url = elapsed / processed            if processed > 0 else None
eta_seconds        = ((total - processed) / urls_per_min_avg) * 60
                     if urls_per_min_avg > 0 and remaining > 0 else None
```

These formulas work for **every** job state: created/running/paused/stopped/
failed/completed, because they read the live counters and guard divisors.

## 5. Events emitted (PART 16)

| Event | When | Payload (safe metadata only) |
|---|---|---|
| `PERFORMANCE_MONITOR_STARTED` | monitor thread starts | `{interval, scope}` |
| `PERFORMANCE_MONITOR_STOPPED` | `close()` | `{}` |
| `PERFORMANCE_WARNING` | memory ≥ 90% observed | `{kind, message}` |
| `PERFORMANCE_RECOMMENDATION_AVAILABLE` | job finalize w/ recs | `{basis}` |
| `JOB_PERFORMANCE_RECORDED` | job finalize (once) | `{workers, urls_per_min}` |

No per-sample flooding: samples themselves are written to the store, not
emitted as events. Events carry only aggregate metadata, never credentials,
cookies, or raw URLs.

## 6. Graceful degradation checklist

- psutil missing a metric → `0.0`/`None`, monitor continues.
- `performance.monitoring_enabled = False` → `SystemMonitor` not started.
- `performance.process_monitoring_enabled = False` → `RuntimeMonitor` not started.
- `performance.gpu_monitoring_enabled = False` (default) → GPU field stays `None`;
  even when enabled, GPU sampling is wrapped in try/except (optional lib).
- Any exception inside the hook calls from `JobManager` is swallowed, so
  monitoring can never break a running scrape.
