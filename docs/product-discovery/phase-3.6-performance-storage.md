# Phase 3.6 — Performance Storage

> Decision + schema for persisting performance data. Backend-only.

## 1. Decision: extend the existing SQLite DB

**Chosen approach:** add four additive tables to the **same** SQLite database
already used by `JobStore` (the `reelminner.db` file under the app `data_dir`).

Rationale:
- **Single source of truth / single file.** No new credential surface, no second
  connection to manage for backups. The performance data is local and
  git-ignored alongside the rest of `data/`.
- **Survives restart.** SQLite persists; summaries and history are read back on
  the next launch via `PerformanceStore`.
- **No migration of existing tables.** The `jobs`, `results`, `settings`,
  `proxies` tables are untouched. Only `CREATE TABLE IF NOT EXISTS` for the new
  `perf_*` tables is added, so existing job persistence is never broken.
- **Reuses the project's error/transaction conventions** (the store opens its own
  connection to the shared file with `PRAGMA busy_timeout=5000` so light
  concurrent writes — job progress vs. perf sample — wait instead of raising
  "database is locked").

The `PerformanceStore` is instantiated with the same `db_path` the `JobStore`
uses. It is closed by `PerformanceService.close()` (invoked from
`ReelminnerApplication.close()`).

## 2. Schema

```sql
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
CREATE INDEX IF NOT EXISTS idx_perf_sample_job ON perf_job_sample(job_id);

CREATE TABLE IF NOT EXISTS perf_config_outcome (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT, workers INTEGER, delay REAL,
    network_mode TEXT, proxy_id TEXT,
    processed INTEGER, successful INTEGER, failed INTEGER,
    elapsed_seconds REAL, urls_per_min REAL
);
CREATE INDEX IF NOT EXISTS idx_perf_outcome_workers ON perf_config_outcome(workers);
```

## 3. What each table is for

- **perf_machine_profile** — one row per app start (or per re-detection): the host
  capabilities used as context for recommendations. Never overwritten per-job.
- **perf_job_summary** — the authoritative per-job outcome, generated on
  complete/stop/fail. `INSERT OR REPLACE` keyed by `job_id`, so a re-finalize
  updates rather than duplicates.
- **perf_job_sample** — throttled time-series of throughput/quality. Capped at
  `performance.max_samples_per_job` per job (oldest row dropped when exceeded).
- **perf_config_outcome** — one row per finished job capturing `(workers, delay,
  network_mode, proxy_id, throughput)`. This is the dataset the analyzer and
  recommendation engine compare across jobs to find diminishing returns and a
  safe worker count.

## 4. Retention

`PerformanceStore.purge_old(days)` deletes `perf_job_sample` rows older than
`days` and `perf_job_summary` rows whose `completed_at`/`created_at` are older
than the cutoff. `days` comes from `performance.history_retention_days`
(default 30, range 1–365). The app does not auto-purge on a timer in this phase;
the method exists and is tested so a future cron/UI can call it. Nothing is ever
auto-deleted in a way that affects running jobs.

## 5. Privacy guardrails (see also performance-privacy)

- Only `proxy_id` (a reference) is stored — never proxy host, scheme, username,
  or password.
- Only **counts** (processed/successful/failed/blocked/rate_limited) are stored —
  never the target URLs, cookies, or result contents.
- Machine profile contains no hostname, username, IP, MAC, or serial number.
