# Phase 3 — Session Design

**Status:** Designed and implemented before wiring.
**Scope:** Multi-session architecture for Reelminner Phase 3.
**Constraint:** Sensitive cookie values must never live in the metadata tables;
the scraper remains the source of truth for scraping.

---

## 1. Domain model (`sessions.py`)

```python
class SessionStatus(str, Enum):
    UNKNOWN / HEALTHY / INVALID / EXPIRED / RATE_LIMITED / ERROR

@dataclass
class Session:
    id, name, username, status,
    created_at, updated_at, last_checked_at, last_used_at,
    error_summary, source, cookies_path
```

Operations on `SessionManager`:

| Operation | Notes |
|-----------|-------|
| `import_session(name, cookies_file, source, username)` | Copies the cookies file into `data/sessions/<id>.json`; status starts `UNKNOWN`; emits `SESSION_CREATED`. |
| `create_session(name, username, source)` | Manual session with no cookies yet. |
| `get_session` / `list_sessions` | Metadata only. |
| `update_session(id, name, username, status)` | Persists; emits `SESSION_UPDATED`. |
| `test_session(id)` | Runs the validator; sets health status + `last_checked_at`; emits `SESSION_TESTED` or `SESSION_FAILED`. |
| `delete_session(id)` | Removes metadata **and** the cookies file. Safe. |
| `get_cookies_path(id)` | Resolves the cookies file for a job; returns `None` if the session is gone (deleted-session safety). |
| `mark_used(id)` | Sets `last_used_at` when a job runs with the session. |

---

## 2. Storage & security strategy

Two physical stores, deliberately separated:

```
data/sessions/<session_id>.json     <- SENSITIVE cookie values (git-ignored)
sessions.db  (SQLite `sessions` table)  <- METADATA ONLY
    id, name, username, status, timestamps, error_summary, source, cookies_path
```

- **Cookie values are never written to SQLite.** The DB holds only a
  *reference* (`cookies_path`) to the per-session cookies file.
- The cookies file lives under `data/` which is git-ignored (added in Phase 2).
- `SessionManager` getters return metadata only; cookie contents are not
  surfaced through the public API.
- `test_session` reads the cookies file directly (parsing `sessionid` +
  expiry) — **no Playwright browser is launched** for a health check.

### Default validator (no browser)

`_default_session_validator(path)`:
- missing / unreadable file → `INVALID`
- no `sessionid` cookie → `UNKNOWN`
- `sessionid` present and not expired → `HEALTHY`
- `sessionid` expired → `EXPIRED`
- unexpected format → `UNKNOWN`
- parser exception → `ERROR`

`RATE_LIMITED` is reserved in the enum for when the engine reports a rate-limited
session during an actual run (future enhancement); the static validator does not
manufacture it.

### Injectable validator

`SessionManager(validator=callable)` accepts a `Callable[[path], (status, error)]`.
Tests inject fake validators, so no browser/cookies are needed in CI.

---

## 3. Job + Session integration

- `Job` gains a `session_id` column (safe `ALTER TABLE` migration in
  `JobStore._init_schema`).
- `JobManager.create_job(..., session_id=...)` stores the reference.
- On `start_job`, `JobManager` resolves the cookies file via an injected
  `session_state_resolver` (wired to `SessionManager.get_cookies_path`) and
  passes it as `state_file` to the engine. If a session is selected,
  `on_session_used` (`SessionManager.mark_used`) records `last_used_at`.
- **Deleted sessions do not corrupt historical jobs:** `get_cookies_path`
  returns `None` for a missing session, so `JobManager` falls back to the
  default `storage_state.json` and the job still runs. The job record keeps its
  `session_id` for audit.
- Jobs created before sessions existed have `session_id = None` and run exactly
  as before (backward compatible).

---

## 4. Files introduced

| File | Responsibility |
|------|----------------|
| `sessions.py` | `Session`, `SessionStatus`, `SessionStore` (SQLite), `SessionManager`, default validator |

`job_manager.py` and `jobs.py` received *additive* changes only (optional
`session_id`, `session_state_resolver`, `RESULTS_AVAILABLE` emit). `scraper.py`,
`service.py`, `events.py`, `gui.py`, `mcp_server.py`, `parsers.py` untouched.

---

## 5. Known limitations

- `test_session` is a *static* cookie check, not a live Instagram auth check.
  True live validation requires a browser and is out of scope for the backend.
- No session rotation (per spec non-goal). Selection + lifecycle only.
- Cookies file format is assumed to be the engine's
  `{"cookies":[...],"origins":[...]}` shape; import copies the raw file and the
  engine loads it at scrape time.
