# Phase 2 — Backend Service Architecture

**Status:** Implemented. Regression green (133 passed, 18 subtests).
**Scope:** Persistent, job-based local application backend for the future
Reelminner desktop app. No frontend / Electron / installer work.

---

## 1. Dependency direction (hard rule)

```
UI / MCP / CLI
    ↓
Application Services   (job_manager.JobManager)
    ↓                      ↓
Repositories / Persistence   Core Scraper
(storage.JobStore,            (scraper.Reelminner
 ResultStore)                  via service.ScraperService)
    ↓
SQLite (metadata) + JSONL (bulk rows)
```

- The **scraper never imports the backend**. `scraper.py`, `service.py`,
  `events.py`, `parsers.py`, `gui.py`, `mcp_server.py` are **unchanged** in
  Phase 2.
- The scraper is driven only through `service.ScraperService` (its existing
  facade), so scraping logic is reused, not duplicated.
- `JobManager` is the **single authoritative owner** of job lifecycle. Neither
  the GUI nor the scraper hold competing job state.

---

## 2. New modules

| Module | Responsibility | Key types |
|--------|----------------|-----------|
| `jobs.py` | Pure domain model | `JobStatus`, `Job`, `JobConfig`, transition rules, `IllegalTransitionError` |
| `storage.py` | Persistence | `JobStore` (SQLite), `ResultStore` (JSONL), `StorageError` |
| `app_events.py` | Event layer | `ApplicationEventBus` (EventSink), `AppEventKind`, `ApplicationEvent` |
| `job_manager.py` | Orchestration | `JobManager` (create/start/pause/resume/stop/retry/get/list) |

No changes to any pre-Phase-2 file.

---

## 3. Job domain model (`jobs.py`)

`Job` fields (per spec):

`id, created_at, started_at, completed_at, status, config, total_items,
processed_items, successful_items, failed_items, blocked_items,
rate_limited_items, result_location, error_summary`

Plus `updated_at` (audit) and a nested `JobConfig` (urls, workers, delay,
headless, with_profiles, **pending_urls** — the resume cursor).

**Explicit statuses:** `CREATED, QUEUED, STARTING, RUNNING, PAUSED, STOPPED,
COMPLETED, FAILED, INTERRUPTED`.

**Legal transitions** are encoded in `LEGAL_TRANSITIONS`; any other move raises
`IllegalTransitionError`. Terminal states (`COMPLETED, FAILED, STOPPED,
INTERRUPTED`) cannot move except via `retry_job`, which creates a *new* job.

```
CREATED → QUEUED → STARTING → RUNNING → COMPLETED
                               ├→ PAUSED → RUNNING
                               ├→ STOPPED
                               └→ FAILED
(non-terminal on restart) → INTERRUPTED
```

---

## 4. Persistence (`storage.py`)

Decision: **hybrid**. Rationale and trade-offs in
`phase-2-storage-design.md`.

- `JobStore` — SQLite (`jobs`, `settings` tables). Stores metadata, config
  (JSON), lifecycle, statistics, `result_location`. WAL + FK on. On
  construction, `mark_interrupted()` flips any non-terminal job to
  `INTERRUPTED` (honest crash recovery — we never pretend a crashed job
  resumed).
- `ResultStore` — per-job JSONL (`data/jobs/<job_id>.jsonl`), one `ReelData`
  per line, reconstructed with `ReelData(**row)`. Appended as rows arrive
  (streaming, crash-tolerant), loaded lazily.

---

## 5. Application event layer (`app_events.py`)

```
Scraper engine
  → ScraperService (event_sink = ApplicationEventBus)
      → ApplicationEventBus.translate(ScraperEvent)
          → ApplicationEvent(kind, job_id, payload)
              → listeners (future UI / Logs / MCP)
JobManager.emit_app(...)  → lifecycle events with job_id
```

`ApplicationEventBus` **implements `EventSink`** so it can be handed directly to
`ScraperService`. It tags every engine event with the **active job id** and
re-dispatches it as an application event (`JOB_PROGRESS`, `ROW_PROCESSED`,
`WARNING`, `ERROR`, `LOG`, `STATUS`). `JOB_START`/`JOB_DONE` are owned by the
JobManager lifecycle and not double-emitted. Lifecycle events
(`JOB_CREATED/STARTED/PAUSED/RESUMED/STOPPED/COMPLETED/FAILED`) are emitted by
the JobManager with full job context.

No Tkinter coupling anywhere.

---

## 6. JobManager (`job_manager.py`)

Owns the full lifecycle and is the **only** place that flips job state:

- `create_job(urls, …)` — normalizes URLs, persists `CREATED`, emits
  `JOB_CREATED`.
- `start_job(id)` — `CREATED/QUEUED → STARTING → RUNNING`, spawns a worker
  thread that drives `ScraperService.scrape(...)`, persists `result_location`.
- `pause_job(id)` — cooperative soft-stop; remaining URLs persisted to
  `config.pending_urls`; finalizes `PAUSED`.
- `resume_job(id)` — from `PAUSED` only; starts a **fresh** engine on the
  remaining URLs; results appended to the same file; finalizes `COMPLETED`.
- `stop_job(id)` — hard stop; finalizes `STOPPED`; remainder retained.
- `retry_job(id)` — from `FAILED/STOPPED/INTERRUPTED`; creates a **new** job
  with the same config (history preserved) and starts it.
- `get_job`, `list_jobs`, `get_job_results`, settings getters/setters.

Concurrency/safety:
- The worker thread runs `scrape()` (blocking) off the caller's thread.
- `row_cb` appends to `ResultStore` (JSONL, locked); `progress_cb` updates
  in-memory stats and persists.
- `pause`/`stop` are cooperative: they set a flag + call `scraper.stop()`
  (the engine's existing soft-stop). The in-flight item always finishes.
- `wait_for_job` / `wait_for_idle` join worker threads; `close()` stops and
  joins before closing the DB.

---

## 7. How the deliverables are satisfied

| Spec deliverable | Where |
|------------------|-------|
| 1. Persistent storage + strategy doc | `storage.py`, `phase-2-storage-design.md` |
| 2. Typed Job model + legal transitions | `jobs.py` |
| 3. JobManager (authoritative owner) | `job_manager.py` |
| 4. Pause/resume investigation + doc | `phase-2-pause-resume-design.md`, `pause_job`/`resume_job` |
| 5. Recovery (INTERRUPTED) | `JobStore.mark_interrupted`, `INTERRUPTED` status |
| 6. Application event layer | `app_events.py`, bus wired into `ScraperService` |
| 7. Repository / service boundaries | separate `jobs`/`storage`/`app_events`/`job_manager` |
| 8. Backward compatibility | untouched scraper/service/events/gui/mcp; full suite green |

---

## 8. Python API (for future CLI/MCP/UI)

```python
from job_manager import JobManager
from app_events import ApplicationEventBus

bus = ApplicationEventBus()
jm = JobManager(data_dir="data", event_bus=bus)
bus.subscribe(lambda e: print(e.kind, e.job_id, e.payload))

job = jm.create_job(["https://www.instagram.com/reel/ABCD/"])
jm.start_job(job.id)
# later: jm.pause_job(job.id) / jm.resume_job(job.id) / jm.stop_job(job.id)
jm.wait_for_job(job.id)
print(jm.get_job(job.id).status, len(jm.get_job_results(job.id)))
jm.close()
```

The engine remains independently testable; `JobManager` accepts an injectable
`scraper_factory` so it can run without a browser in tests.
