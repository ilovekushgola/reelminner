# Phase 2 — Test Report

**Date:** 2026-08-14
**Result:** ✅ PASS — all old tests pass, all new tests pass, no public interface broken.

---

## 1. Test counts

| Metric | Value |
|--------|-------|
| Previous (Phase 1 baseline) | **94 passed** (18 subtests) |
| New test modules | 4 (`test_jobs`, `test_storage`, `test_app_events`, `test_job_manager`) |
| New test methods | 42 |
| Final total | **133 passed, 18 subtests passed** |
| Net new test cases | **+39** |
| Failures | 0 |
| Errors | 0 |

Run command:
```
python -m pytest
# -> 133 passed, 18 subtests passed in ~8s
```

---

## 2. New tests added

### `tests/test_jobs.py` (11)
Job domain model & transitions.
- terminal states / `is_terminal`
- valid transition chain (CREATED→…→COMPLETED)
- illegal transition raises `IllegalTransitionError`
- completed job cannot move
- timestamps set on transition (started_at / completed_at)
- `record_result` categorisation (ok / failed / blocked / rate_limited)
- `reset_stats`
- `JobConfig` JSON round-trip
- `Job` DB row round-trip

### `tests/test_storage.py` (12)
Persistence layer.
- `JobStore` create / get
- update persists config + pending_urls + status
- `list_jobs` ordering and status filter
- settings key/value round-trip
- **crash recovery**: RUNNING job → `INTERRUPTED` on reopen
- `ResultStore` append + load, overwrite, field round-trip, missing → `[]`

### `tests/test_app_events.py` (6)
Application event layer.
- engine `PROGRESS`/`ROW` translated with job context
- `JOB_START`/`JOB_DONE` ignored (owned by lifecycle)
- `LOG` severity mapping (→ `ERROR` / `WARNING` / `LOG`)
- `emit_app` lifecycle events
- bad listener does not break the pipeline

### `tests/test_job_manager.py` (13)
Full lifecycle with an injected `FakeScraperService` (no browser).
- create_job normalises URLs + emits `JOB_CREATED`
- start → completion (stats + results + events)
- events carry `job_id` context
- **pause → resume merges results** (no duplicates, remainder persisted)
- stop persists partial results
- scrape failure → `FAILED` + error summary
- retry creates a *new* job
- invalid transitions (start-from-completed, pause-from-created, resume-from-non-paused, retry-from-created)
- **persists across restart** (new `JobManager` on same DB)
- running job marked `INTERRUPTED` on restart

---

## 3. Regression (existing behaviour)

The full suite of **94 existing tests** still passes. Specifically verified
unchanged and green:

- `test_mcp_server.py` — the **5-tool MCP contract** is intact.
- `test_service.py`, `test_session_and_export.py` — `ScraperService` + exporters.
- `test_extract_wiring.py`, `test_profile_parsers.py`, `test_events.py`,
  `test_gui_columns.py`, etc. — parsing, GUI columns, events.

**No file in the pre-Phase-2 stack was modified**: `scraper.py`, `service.py`,
`events.py`, `parsers.py`, `gui.py`, `mcp_server.py` are byte-for-byte the same
as at end of Phase 1. Only new modules were added (`jobs.py`, `storage.py`,
`app_events.py`, `job_manager.py`), so no public method signature changed.

---

## 4. Warnings

- **None new.** The pre-existing harmless `\/` regex deprecation warnings in
  `scraper.py` (line ~748/769) are untouched — they are out of Phase 2 scope
  and were documented in Phase 1.
- Boundary enforcement between layers is by **convention** (import direction),
  not a runtime guard. The scraper still does not import any backend module.

---

## 5. Known limitations

1. **Cooperative pause (by design).** Python cannot safely suspend a running
   thread / Playwright session, so pause lets the current reel finish, blocks
   new items, and restarts a fresh engine on the remainder. This is real, not
   faked — documented in `phase-2-pause-resume-design.md`.
2. **No per-item checkpoint.** On a hard crash the single in-flight reel is
   lost; `retry_job` re-scrapes it. `pending_urls` is persisted only at pause
   boundaries. A crashed job becomes `INTERRUPTED`, never silently "resumed".
3. **Results are JSONL, not SQL.** Bulk rows live in `data/jobs/<id>.jsonl`.
   This keeps the metadata DB tiny but means result rows are not SQL-queryable;
   aggregation requires loading the file. This is the chosen hybrid trade-off
   (see `phase-2-storage-design.md`).
4. **`blocked_items` / `rate_limited_items` are wired but usually 0.** The
   current engine rarely emits `rate_limited` / `session_expired` / structural
   statuses, so those counts are typically 0 in practice. The categorisation
   is in place for when the engine emits them.
5. **Concurrency:** `JobManager` supports multiple concurrent jobs (each its
   own engine/thread). The initial desktop app may choose to run one at a time;
   there is intentionally no artificial limit for a local single-user tool.
6. **`is_resume` parameter** in `_run` is reserved/unused; resume correctness
   is achieved via `pending_urls` + a fresh engine instance.

---

## 6. Migration notes

- New runtime directory **`data/`** is created on first `JobManager` use
  (SQLite `reelminner.db` + `jobs/*.jsonl` + `storage_state.json`). It is now
  git-ignored. Include it in application backups.
- No migration step is required for existing data — Phase 2 is purely additive.
- **Adoption path for CLI / MCP / UI:** route scrape requests through
  `JobManager` (which drives `ScraperService`) instead of calling
  `ScraperService.scrape` directly, so job lifecycle, persistence and events
  are unified. This is a future integration step, not part of Phase 2.
- Quick smoke (no browser):
  ```python
  from job_manager import JobManager
  jm = JobManager(data_dir="data")
  job = jm.create_job(["https://www.instagram.com/reel/ABCD/"])
  jm.start_job(job.id)          # drives the real ScraperService
  jm.wait_for_job(job.id)
  print(jm.get_job(job.id).status)
  jm.close()
  ```

---

## 7. Definition of Done — checklist

- [x] Jobs have a typed domain model (`jobs.py`)
- [x] Jobs persist across application restarts (`JobStore` + reopen test)
- [x] Job lifecycle transitions are controlled (`LEGAL_TRANSITIONS`)
- [x] `JobManager` is the authoritative lifecycle owner
- [x] Pause/resume behaviour is real and documented
- [x] Existing scraper logic remains reusable (`ScraperService` boundary)
- [x] Events propagate with job context (`app_events.py`)
- [x] Database code is separated from scraping code
- [x] Existing CLI / GUI / MCP behaviour remains compatible (full suite green)
- [x] Full regression suite passes (133 passed)
- [x] Architecture and limitations are documented
