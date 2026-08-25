"""Persistence layer for Reelminner Phase 2.

Two stores:

* ``JobStore``   - SQLite. Jobs metadata, configuration, lifecycle, statistics,
                   and application settings. Small, structured, query-heavy.
* ``ResultStore``- File-based JSONL. Bulk result rows (one reel per line), kept
                   out of SQLite so the metadata DB stays tiny and fast.

Decision rationale: see docs/product-discovery/phase-2-storage-design.md
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

from jobs import Job, JobStatus

try:  # ReelData lives in the engine; imported lazily-safe for type checks.
    from scraper import ReelData
except Exception:  # pragma: no cover - only relevant in minimal environments
    ReelData = None  # type: ignore


class StorageError(Exception):
    """Raised for persistence failures."""


_TERMINAL = {s.value for s in JobStatus.terminal_states()}


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


class JobStore:
    """SQLite-backed store for jobs and application settings."""

    def __init__(self, db_path: str | Path, recover: bool = True) -> None:
        self._db_path = str(db_path)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            self._db_path, check_same_thread=False
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()
        if recover:
            self.mark_interrupted()

    # ------------------------------------------------------------------ #
    # Schema
    # ------------------------------------------------------------------ #
    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id                 TEXT PRIMARY KEY,
                    created_at         TEXT NOT NULL,
                    started_at         TEXT,
                    completed_at       TEXT,
                    updated_at         TEXT NOT NULL,
                    status             TEXT NOT NULL,
                    config_json        TEXT NOT NULL,
                    total_items        INTEGER NOT NULL DEFAULT 0,
                    processed_items    INTEGER NOT NULL DEFAULT 0,
                    successful_items   INTEGER NOT NULL DEFAULT 0,
                    failed_items       INTEGER NOT NULL DEFAULT 0,
                    blocked_items      INTEGER NOT NULL DEFAULT 0,
                    rate_limited_items INTEGER NOT NULL DEFAULT 0,
                    result_location    TEXT,
                    session_id         TEXT,
                    error_summary      TEXT
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key        TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL
                );
                """
            )
            # Migration: add session_id to any pre-existing jobs table.
            try:
                self._conn.execute(
                    "ALTER TABLE jobs ADD COLUMN session_id TEXT"
                )
            except Exception:
                pass
            self._conn.commit()

    # ------------------------------------------------------------------ #
    # Recovery (crash while running)
    # ------------------------------------------------------------------ #
    def mark_interrupted(self) -> int:
        """Flip any non-terminal job to INTERRUPTED.

        Returns the number of jobs affected. Called on app start; we never
        silently pretend a crashed job finished or can resume mid-flight.
        """
        with self._lock:
            now = _now_iso()
            cur = self._conn.execute(
                """
                UPDATE jobs
                   SET status = ?,
                       completed_at = ?,
                       updated_at = ?,
                       error_summary = ?
                 WHERE status NOT IN (%s)
                """
                % ",".join("?" for _ in _TERMINAL),
                [
                    JobStatus.INTERRUPTED.value,
                    now,
                    now,
                    "Interrupted by application restart",
                    *_TERMINAL,
                ],
            )
            self._conn.commit()
            return cur.rowcount

    # ------------------------------------------------------------------ #
    # Job CRUD
    # ------------------------------------------------------------------ #
    def create_job(self, job: Job) -> None:
        self._upsert(job)

    def update_job(self, job: Job) -> None:
        self._upsert(job)

    def _upsert(self, job: Job) -> None:
        row = job.to_db_row()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO jobs (
                    id, created_at, started_at, completed_at, updated_at,
                    status, config_json, total_items, processed_items,
                    successful_items, failed_items, blocked_items,
                    rate_limited_items, result_location, session_id, error_summary
                ) VALUES (
                    :id, :created_at, :started_at, :completed_at, :updated_at,
                    :status, :config_json, :total_items, :processed_items,
                    :successful_items, :failed_items, :blocked_items,
                    :rate_limited_items, :result_location, :session_id, :error_summary
                )
                ON CONFLICT(id) DO UPDATE SET
                    created_at=excluded.created_at,
                    started_at=excluded.started_at,
                    completed_at=excluded.completed_at,
                    updated_at=excluded.updated_at,
                    status=excluded.status,
                    config_json=excluded.config_json,
                    total_items=excluded.total_items,
                    processed_items=excluded.processed_items,
                    successful_items=excluded.successful_items,
                    failed_items=excluded.failed_items,
                    blocked_items=excluded.blocked_items,
                    rate_limited_items=excluded.rate_limited_items,
                    result_location=excluded.result_location,
                    error_summary=excluded.error_summary
                """,
                row,
            )
            self._conn.commit()

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            )
            row = cur.fetchone()
        if row is None:
            return None
        return Job.from_db_row(self._row_to_dict(row, cur))

    def list_jobs(
        self,
        limit: int = 50,
        offset: int = 0,
        status: Optional[JobStatus] = None,
    ) -> list[Job]:
        sql = "SELECT * FROM jobs"
        params: list[Any] = []
        if status is not None:
            sql += " WHERE status = ?"
            params.append(status.value)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self._lock:
            cur = self._conn.execute(sql, params)
            rows = cur.fetchall()
        return [Job.from_db_row(self._row_to_dict(r, cur)) for r in rows]

    def count_jobs(self, status: Optional[JobStatus] = None) -> int:
        if status is None:
            with self._lock:
                return self._conn.execute(
                    "SELECT COUNT(*) FROM jobs"
                ).fetchone()[0]
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status = ?",
                (status.value,),
            ).fetchone()[0]

    @staticmethod
    def _row_to_dict(row, cur) -> dict:
        cols = [d[0] for d in cur.description]
        return {cols[i]: row[i] for i in range(len(cols))}

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.commit()
            except Exception:
                pass
            self._conn.close()

    # ------------------------------------------------------------------ #
    # Settings (key/value)
    # ------------------------------------------------------------------ #
    def set_setting(self, key: str, value: Any) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO settings (key, value_json) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json
                """,
                (key, json.dumps(value, ensure_ascii=False)),
            )
            self._conn.commit()

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._lock:
            cur = self._conn.execute(
                "SELECT value_json FROM settings WHERE key = ?", (key,)
            )
            row = cur.fetchone()
        if row is None:
            return default
        try:
            return json.loads(row[0])
        except Exception:
            return default


class ResultStore:
    """File-based store for bulk job result rows (JSONL)."""

    def __init__(self, data_dir: str | Path) -> None:
        self._dir = Path(data_dir) / "jobs"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def result_path(self, job_id: str) -> Path:
        return self._dir / f"{job_id}.jsonl"

    def write_results(self, job_id: str, rows: list) -> None:
        path = self.result_path(job_id)
        with self._lock:
            with open(path, "w", encoding="utf-8") as f:
                for r in rows:
                    data = r.to_dict() if hasattr(r, "to_dict") else dict(r)
                    f.write(json.dumps(data, ensure_ascii=False) + "\n")

    def append_result(self, job_id: str, reel_data) -> None:
        path = self.result_path(job_id)
        data = (
            reel_data.to_dict()
            if hasattr(reel_data, "to_dict")
            else dict(reel_data)
        )
        with self._lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")

    def load_results(self, job_id: str) -> list:
        path = self.result_path(job_id)
        if not path.exists():
            return []
        out = []
        with self._lock:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    out.append(ReelData(**d) if ReelData is not None else d)
        return out

    def iter_results(self, job_id: str):
        """Stream rows one at a time (memory-friendly for large datasets)."""
        path = self.result_path(job_id)
        if not path.exists():
            return
        with self._lock:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    yield ReelData(**d) if ReelData is not None else d

    def count(self, job_id: str) -> int:
        path = self.result_path(job_id)
        if not path.exists():
            return 0
        with self._lock:
            with open(path, "r", encoding="utf-8") as f:
                return sum(1 for line in f if line.strip())

    def delete(self, job_id: str) -> None:
        path = self.result_path(job_id)
        with self._lock:
            if path.exists():
                path.unlink()
