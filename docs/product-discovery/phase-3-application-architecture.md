# Phase 3 — Application Architecture

**Status:** Implemented. Regression green (168 passed, 18 subtests).
**Scope:** Clean, typed application service layer for Sessions, Results,
Settings, and a top-level facade. No frontend work.

---

## 1. Target direction

```
Future Desktop UI / MCP / CLI
        ↓
Application Service Layer
        ├── JobManager      (jobs + lifecycle)      [Phase 2]
        ├── ResultService   (Data Explorer backend) [Phase 3]
        ├── SessionManager  (multi-session)         [Phase 3]
        ├── SettingsService (typed settings)        [Phase 3]
        └── LogService      (future; events already flow)
                ↓
        Storage / Core Engine
   (JobStore + ResultStore + sessions.db + scraper.Reelminner)
```

The UI/IPC talks to **stable services**, never to SQLite, JSONL, or the scraper.

---

## 2. New modules (Phase 3)

| Module | Responsibility |
|--------|----------------|
| `sessions.py` | `Session`, `SessionStatus`, `SessionStore` (SQLite), `SessionManager`, default cookie validator |
| `results.py` | `ResultService` + query model (`ResultQuery`, `FilterCondition`, `SortSpec`, `PageSpec`, `ResultSet`, `ResultStatistics`), `parse_count`, `InvalidFilterError` |
| `settings.py` | `SettingsService` + typed `Settings` (General / Scraping / Storage / Export / MCP), validation, reset |
| `app.py` | `ReelminnerApplication` — composition root wiring all services + shared stores + event bus |

Additive changes to existing modules:
- `jobs.py` — `Job.session_id` (+ DB column/persistence).
- `storage.py` — `session_id` column + migration ALTER; `ResultStore.iter_results`.
- `job_manager.py` — `create_job(session_id=)`, `session_state_resolver` /
  `on_session_used` hooks, shared `store`/`result_store` injection,
  `RESULTS_AVAILABLE` emit.
- `app_events.py` — new `AppEventKind`: `SESSION_CREATED`, `SESSION_UPDATED`,
  `SESSION_TESTED`, `SESSION_FAILED`, `SETTINGS_UPDATED`, `RESULTS_AVAILABLE`.
- `scraper.py`, `service.py`, `events.py`, `parsers.py`, `gui.py`,
  `mcp_server.py` — **untouched**.

---

## 3. ReelminnerApplication (facade)

A thin composition root, **not a God object**. It owns shared stores and wires
lifecycle hooks:

```python
app = ReelminnerApplication(data_dir="data")
app.jobs        # JobManager
app.results     # ResultService
app.sessions    # SessionManager
app.settings    # SettingsService
app.event_bus   # ApplicationEventBus  (subscribe here for UI/logs/MCP)
```

- `JobManager.session_state_resolver = app.sessions.get_cookies_path`
- `JobManager.on_session_used = app.sessions.mark_used`
- `ResultService` is built from the *same* `ResultStore` the `JobManager` writes
  to, so results are queryable immediately after a run.
- `SettingsService` is built from the *same* `JobStore`, so settings survive
  restart and feed `ResultService.default_page_size`.

---

## 4. Application events (extended, backward compatible)

Existing `JOB_*` / `ROW_PROCESSED` / `JOB_PROGRESS` / `WARNING` / `ERROR` / `LOG`
contracts are unchanged. Added:

| Event | Emitted by | Context |
|-------|-----------|---------|
| `SESSION_CREATED` | SessionManager.import/create | session id |
| `SESSION_UPDATED` | SessionManager.update | session id |
| `SESSION_TESTED` | SessionManager.test (success) | session id + status |
| `SESSION_FAILED` | SessionManager.test (error) | session id + error |
| `SETTINGS_UPDATED` | SettingsService.update/reset | keys |
| `RESULTS_AVAILABLE` | JobManager on completion | job id + count |

No events are emitted for trivial getter calls (per spec).

---

## 5. Data contracts (summary)

- **Session** → `sessions` table (metadata) + `data/sessions/<id>.json`
  (cookies). Job references via `jobs.session_id`.
- **Result query** → `ResultQuery{search, filters[], sort, page}` →
  `ResultSet{rows, total_matched, total_in_job, page, page_size, has_next,
  has_prev}`.
- **Statistics** → `ResultStatistics{total, successful, failed, partial,
  blocked, rate_limited, verified, total_engagement, average_engagement}`.
- **Settings** → `Settings{general, scraping, storage, export, mcp}` persisted
  as one JSON blob under key `app_settings`.

---

## 6. Boundaries & testability

- The scraper is never imported by the service layer except to reuse exporters
  and `ReelData` (read-only). No scraping logic is duplicated.
- Every service accepts injectable dependencies: `SessionManager(validator=)`,
  `JobManager(scraper_factory=, store=, result_store=,
  session_state_resolver=, on_session_used=)`, `SettingsService(store=)`.
  This is what makes the full Phase 3 test suite run **without a browser**.
- `ReelminnerApplication` can be constructed with a `scraper_factory` for
  headless/CI runs.

---

## 7. Known limitations

- `test_session` is a static cookie check (no live Instagram auth).
- Sorting/filtering materialises the matched subset in memory (fine for local
  use; a future index is out of scope).
- `partial_rows` / `rate_limited_rows` depend on engine-emitted statuses; today
  they are usually 0 because the engine rarely emits those specific statuses.
- No session rotation, proxy management, or cloud sync (explicit non-goals).

---

## 8. Python API example

```python
from app import ReelminnerApplication

app = ReelminnerApplication(data_dir="data")
app.event_bus.subscribe(lambda e: print(e.kind, e.job_id))

sess = app.sessions.import_session("Main", "cookies.json")
app.sessions.test_session(sess.id)

job = app.jobs.create_job(urls, session_id=sess.id)
app.jobs.start_job(job.id)
app.jobs.wait_for_job(job.id)

stats = app.results.get_result_statistics(job.id)
page  = app.results.filter_results(job.id,
            [FilterCondition(field="is_verified", op=FilterOp.EQ, value=True)])
app.results.export_filtered(job.id, "csv", "out.csv",
            ResultQuery(filters=page and None))
app.close()
```
