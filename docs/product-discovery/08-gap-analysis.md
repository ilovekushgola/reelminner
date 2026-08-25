# 08 — Gap Analysis

> Three buckets: what we can **reuse**, what we must **improve**, and what is
> **completely missing** for the future desktop application.

---

## 8.1 ✅ Already Exists (reuse as-is or with light refactor)

- **`parsers.py`** — all pure extraction functions. Drop-in reusable; the foundation of
  the engine. Keep verbatim.
- **`ReelData` dataclass + `write_csv` / `export_json` / `export_excel`** — solid data
  contract and exporters. **Extended in Phase 1** with 9 new reliable fields
  (full_name, bio, is_verified, reels_count, thumbnail, music_id, reel_id,
  profile_url, scrape_ts); all covered by regression tests.
- **`Reelminner.scrape()` orchestration** — queue + worker + lock + stop
  pattern works. Keep core; extract into a service.
- **`save_cookies_from_file`** — robust dual-format cookie import. Reuse.
- **`backoff_delay` / `should_retry`** — clean, unit-tested. Reuse.
- **MCP tool contracts** (5 tools) — `scrape_reels`, `get_status`, `import_cookies`,
  `stop_scrape`, `export_results`. Keep the contract; wrap with a service layer.
- **`run_qa.py` gates** — reuse as the QA core in CI / nightly.
- **Unit test suite + fixtures** — reuse; expand.
- **PyInstaller build + Inno Setup installer base + `SIGNING.md`** — reuse; extend to
  bundle runtime.
- **`assets/icon.ico` + `make_icon.py`** — branding reuse.
- **`.mcp.json` / `mcp.env.example`** — reuse.

---

## 8.2 🟡 Needs Improvement (exists but requires refactor / better testing / architecture)

- **Inconsistent field coverage** → **RESOLVED in Phase 1**: `ReelData`/parsers
  extended with full_name, bio, is_verified, reels_count, thumbnail, music_id,
  reel_id, profile_url, scrape_ts (all regression tests green).
- **GUI coupled to business logic** (`gui.py` `ReelScraperApp`) → **RESOLVED in Phase 1**:
  a `ScraperService` facade now sits between GUI/MCP and the engine (clean boundary);
  GUI/MCP were rewired to use it with identical behavior.
- **No pause/resume/cancel-per-URL** → job state machine.
- **No settings persistence** → settings store.
- **Excel export hidden `openpyxl` dependency** → bundle / graceful error.
- **Brittle DOM fallback** → centralized selectors + fixture regression.
- **No CI** → add GitHub Actions.

---

## 8.3 ❌ Completely Missing (required for the future desktop app)

- **Persistent storage / SQLite** (jobs, results, logs, sessions).
- **Job system**: persistent jobs, queue, history, pause/resume/cancel, retry-failed,
  error history, job details.
- **Deduplication** across jobs.
- **Data Explorer**: search, filter, sort, column management, saved filters, bulk select,
  export filtered subset.
- **Dashboard / analytics** (totals, success rate, recent activity).
- **Session health monitoring, refresh, multi-account rotation**.
- **MCP Manager UI** + SSE/HTTP transport + live progress events + connected-clients view.
- **Structured logging** + **Logs screen** (search/filter/export).
- **Settings persistence** screen.
- **Backend service / API / IPC layer** (FastAPI + WebSocket/SSE) separating UI from engine.
- **Premium multi-window frontend** (React/TS/Electron or comparable) replacing Tk.
- **Auto-managed runtime**: bundled Python + Playwright Chromium; pre-flight checks.
- **Professional, code-signed installer** with automated signing.
- **Concurrency / race tests**, **installer smoke tests**, **CI pipeline**.
- **Multi-account / account-rotation** possibilities (noted in vision).
