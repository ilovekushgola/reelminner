# Phase 2 — Storage Design

**Status:** Decision made before implementation.
**Scope:** Persistent storage for the future Reelminner desktop app backend.
**Constraint:** Do **not** duplicate scraper logic. SQLite is for metadata; the engine remains the source of truth for scraping.

---

## 1. What must be persisted

| Concern | Examples |
|---------|----------|
| Jobs | One row per scrape run |
| Job configuration | Target URLs, workers, delay, headless, with_profiles |
| Job lifecycle state | CREATED → … → COMPLETED / FAILED / STOPPED / INTERRUPTED |
| Job statistics | total / processed / successful / failed / blocked / rate_limited |
| Result metadata | Where the result rows live (`result_location`) |
| Session metadata | App-level settings (default headless, state file, last config) |
| Application settings | Key/value store (theme, defaults, paths) |

The result *rows* themselves are the part that can grow large (hundreds →
thousands of reels, each with ~23 fields, across many jobs over time).

---

## 2. The decision: hybrid (SQLite metadata + file-based bulk results)

```
┌──────────────────────────────────────────────────────────┐
│  SQLite  (reelminner.db)  — small, structured, query-heavy │
│   • jobs        (metadata, config, stats, status)         │
│   • settings    (key/value app settings)                   │
└──────────────────────────────────────────────────────────┘
                          │  result_location (path)
                          ▼
┌──────────────────────────────────────────────────────────┐
│  File store  (data/jobs/<job_id>.jsonl)  — bulk rows      │
│   • one JSON object per reel, newline-delimited            │
│   • streamed append during scrape, streamed read on load  │
└──────────────────────────────────────────────────────────┘
```

### Options evaluated

**Option A — Hybrid (CHOSEN).**
SQLite stores metadata, configuration, lifecycle, and statistics. Bulk result
rows are written to a per-job JSONL file. The `jobs.result_location` column
points at that file.

**Option B — SQLite for everything.**
A `job_results` table holds every reel row, joined to `jobs` by `job_id`.

### Why hybrid wins for *this* app

1. **Query shape.** Jobs, settings, and statistics are small, relational, and
   read/written transactionally. SQLite is ideal here: single file, zero
   external dependencies, ACID, easy backup, survives a process crash via its
   rollback journal / WAL.
2. **Bulk-append shape.** Result rows are an append-only stream produced as the
   scrape runs. Shoving them into SQLite bloats the database, slows the
   metadata queries the Job Monitor needs, and makes schema migrations painful
   (every migration touches the heavy table).
3. **Streaming.** JSONL lets us append a row the instant the engine yields it
   (via the existing `row_cb`), so a crash loses at most the in-flight item —
   not the whole run. Loading is a line-by-line read; we never hold thousands of
   rows in memory at once.
4. **Portability / inspectability.** A `.jsonl` file is trivially diffable,
   greppable, and re-exportable. The desktop app can preview it without opening
   the DB.
5. **Crash recovery.** SQLite stays tiny and fast; on restart we only need to
   flip any non-terminal job to `INTERRUPTED`. The already-written JSONL rows
   are preserved on disk.

### Trade-off we accept

Results now live in two stores, linked by `result_location`. This is a
deliberately simple "manifest" pattern (one file per job) rather than a sharded
results table. It is easier to reason about, back up, and migrate than Option B,
and the cost (a path indirection) is negligible.

---

## 3. Schema (SQLite)

```sql
CREATE TABLE IF NOT EXISTS jobs (
    id                TEXT PRIMARY KEY,
    created_at        TEXT NOT NULL,
    started_at        TEXT,
    completed_at      TEXT,
    updated_at        TEXT NOT NULL,
    status            TEXT NOT NULL,
    config_json       TEXT NOT NULL,   -- JobConfig serialized
    total_items       INTEGER NOT NULL DEFAULT 0,
    processed_items   INTEGER NOT NULL DEFAULT 0,
    successful_items  INTEGER NOT NULL DEFAULT 0,
    failed_items      INTEGER NOT NULL DEFAULT 0,
    blocked_items     INTEGER NOT NULL DEFAULT 0,
    rate_limited_items INTEGER NOT NULL DEFAULT 0,
    result_location   TEXT,            -- path to <job_id>.jsonl
    error_summary     TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);
```

- `config_json` holds the `JobConfig` (urls, workers, delay, headless,
  with_profiles, pending_urls). `pending_urls` is the resume cursor.
- All statistics are stored as flat integers to match the Job domain model
  exactly (see `jobs.py`), avoiding an extra join on every progress update.
- Migrations are versioned via a `PRAGMA user_version` check; new columns are
  added with `ADD COLUMN … DEFAULT 0` so old rows stay valid.

---

## 4. Result file layout

`data/jobs/<job_id>.jsonl` — one line per reel:

```json
{"username": "…", "reel_url": "…", "status": "ok", "…": "…"}
```

Reconstructed with `ReelData(**row)` (the `to_dict()` round-trips all fields).
Appended as rows arrive; truncated/rewritten only on a fresh (non-resume) start.

---

## 5. Recovery contract

- The DB is opened with WAL + a foreign-key-safe single connection per
  `JobStore`.
- On `JobStore` construction (app start), any job whose `status` is not a
  terminal state (`COMPLETED`, `FAILED`, `STOPPED`, `INTERRUPTED`) is flipped to
  `INTERRUPTED`. We do **not** claim a job can resume mid-flight after a crash —
  the queue state is only persisted at pause boundaries, not per-item.
- `result_location` files that already exist are left intact; an `INTERRUPTED`
  job can be *retried* (fresh run) or *resumed* from its `pending_urls` if it was
  paused before the crash.

---

## 6. Files introduced

| File | Responsibility |
|------|----------------|
| `storage.py` | `JobStore` (SQLite), `ResultStore` (JSONL), `StorageError` |
| `jobs.py` | `Job`, `JobConfig`, `JobStatus`, transition rules |
| `job_manager.py` | Orchestration; owns lifecycle + persistence |
| `app_events.py` | Event bus bridging engine → app events |

No changes to `scraper.py`, `service.py`, `events.py`, `gui.py`, `mcp_server.py`,
or `parsers.py`.
