"""Session management for Reelminner Phase 3.

Multi-session architecture. A session is a saved Instagram login (cookies).

Security / storage strategy (see phase-3-session-design.md):

* Sensitive cookie *values* are NEVER stored in the SQLite metadata tables.
  They live only in a per-session cookies file under ``data/sessions/<id>.json``
  (which is git-ignored along with the rest of ``data/``).
* The ``sessions`` SQLite table stores only **metadata** (id, name, status,
  timestamps, error summary, source) plus a *reference* (``cookies_path``) to
  the cookies file — never the cookies themselves.
* ``SessionManager`` getters return metadata only; cookie contents are not
  surfaced through the public API.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from app_events import AppEventKind, ApplicationEventBus
from events import StructuredLogger

LOG = StructuredLogger("reelminner.sessions")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return "sess_" + uuid.uuid4().hex[:12]


class SessionStatus(str, Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    INVALID = "invalid"
    EXPIRED = "expired"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"


# Validator: cookies_path -> (status, error_message_or_None)
SessionValidator = Callable[[str], tuple[SessionStatus, Optional[str]]]


@dataclass
class Session:
    id: str = field(default_factory=_new_id)
    name: str = "Untitled Session"
    username: Optional[str] = None
    status: SessionStatus = SessionStatus.UNKNOWN
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    last_checked_at: Optional[str] = None
    last_used_at: Optional[str] = None
    error_summary: Optional[str] = None
    source: str = "manual"          # manual | editthiscookie | netscape | ...
    cookies_path: Optional[str] = None

    def to_db_row(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "username": self.username,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_checked_at": self.last_checked_at,
            "last_used_at": self.last_used_at,
            "error_summary": self.error_summary,
            "source": self.source,
            "cookies_path": self.cookies_path,
        }

    @classmethod
    def from_db_row(cls, row: dict) -> "Session":
        return cls(
            id=row["id"],
            name=row.get("name", "Untitled Session"),
            username=row.get("username"),
            status=SessionStatus(row.get("status", "unknown")),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            last_checked_at=row.get("last_checked_at"),
            last_used_at=row.get("last_used_at"),
            error_summary=row.get("error_summary"),
            source=row.get("source", "manual"),
            cookies_path=row.get("cookies_path"),
        )


# ----------------------------------------------------------------------------
# Default cookie validator (no browser required)
# ----------------------------------------------------------------------------
def _default_session_validator(path: str) -> tuple[SessionStatus, Optional[str]]:
    """Inspect a cookies file and infer a health status.

    Mirrors the engine's ``has_session`` logic but reads the file directly so
    no Playwright browser is launched.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return SessionStatus.INVALID, "cookies file missing"
    except Exception as exc:  # corrupt / unreadable
        return SessionStatus.INVALID, f"cannot read cookies: {exc}"

    cookies = data.get("cookies") if isinstance(data, dict) else data
    if not isinstance(cookies, list) or not cookies:
        return SessionStatus.UNKNOWN, "no cookies found"

    sid = None
    for c in cookies:
        if c.get("name") == "sessionid":
            sid = c
            break
    if sid is None:
        return SessionStatus.UNKNOWN, "no sessionid cookie"

    expires = sid.get("expires")
    if expires:
        try:
            if float(expires) > 0 and float(expires) < datetime.now(
                timezone.utc
            ).timestamp():
                return SessionStatus.EXPIRED, "sessionid cookie expired"
        except (TypeError, ValueError):
            pass
    return SessionStatus.HEALTHY, None


class SessionStore:
    """SQLite repository for session metadata (cookies stay in files)."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id                TEXT PRIMARY KEY,
                    name              TEXT NOT NULL,
                    username          TEXT,
                    status            TEXT NOT NULL,
                    created_at        TEXT NOT NULL,
                    updated_at        TEXT NOT NULL,
                    last_checked_at   TEXT,
                    last_used_at      TEXT,
                    error_summary     TEXT,
                    source            TEXT,
                    cookies_path      TEXT
                )
                """
            )
            self._conn.commit()

    def create(self, session: Session) -> None:
        row = session.to_db_row()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO sessions (
                    id, name, username, status, created_at, updated_at,
                    last_checked_at, last_used_at, error_summary, source,
                    cookies_path
                ) VALUES (
                    :id, :name, :username, :status, :created_at, :updated_at,
                    :last_checked_at, :last_used_at, :error_summary, :source,
                    :cookies_path
                )
                """,
                row,
            )
            self._conn.commit()

    def update(self, session: Session) -> None:
        session.updated_at = _now_iso()
        row = session.to_db_row()
        with self._lock:
            self._conn.execute(
                """
                UPDATE sessions SET
                    name=:name, username=:username, status=:status,
                    updated_at=:updated_at, last_checked_at=:last_checked_at,
                    last_used_at=:last_used_at, error_summary=:error_summary,
                    source=:source, cookies_path=:cookies_path
                WHERE id=:id
                """,
                row,
            )
            self._conn.commit()

    def get(self, session_id: str) -> Optional[Session]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            )
            row = cur.fetchone()
        if row is None:
            return None
        return Session.from_db_row(self._row_to_dict(row, cur))

    def list(self) -> list[Session]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM sessions ORDER BY created_at DESC"
            )
            rows = cur.fetchall()
        return [Session.from_db_row(self._row_to_dict(r, cur)) for r in rows]

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM sessions WHERE id = ?", (session_id,)
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.commit()
            except Exception:
                pass
            self._conn.close()

    @staticmethod
    def _row_to_dict(row, cur) -> dict:
        cols = [d[0] for d in cur.description]
        return {cols[i]: row[i] for i in range(len(cols))}


class SessionManager:
    """Application service for multi-session management."""

    def __init__(
        self,
        data_dir: str | Path = "data",
        event_bus: Optional[ApplicationEventBus] = None,
        store: Optional[SessionStore] = None,
        validator: Optional[SessionValidator] = None,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._sessions_dir = self._data_dir / "sessions"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        self._bus = event_bus or ApplicationEventBus()
        self._store = store or SessionStore(self._data_dir / "sessions.db")
        self._validator = validator or _default_session_validator

    # ------------------------------------------------------------------ #
    # create / import
    # ------------------------------------------------------------------ #
    def import_session(
        self,
        name: str,
        cookies_file_path: str,
        source: str = "editthiscookie",
        username: Optional[str] = None,
    ) -> Session:
        sess = Session(name=name, username=username, source=source)
        dest = self._sessions_dir / f"{sess.id}.json"
        shutil.copyfile(cookies_file_path, dest)
        sess.cookies_path = str(dest)
        self._store.create(sess)
        self._bus.emit_app(
            AppEventKind.SESSION_CREATED, sess.id, {"name": name, "source": source}
        )
        return sess

    def create_session(
        self,
        name: str,
        username: Optional[str] = None,
        source: str = "manual",
    ) -> Session:
        sess = Session(name=name, username=username, source=source)
        self._store.create(sess)
        self._bus.emit_app(
            AppEventKind.SESSION_CREATED, sess.id, {"name": name, "source": source}
        )
        return sess

    # ------------------------------------------------------------------ #
    # read / update
    # ------------------------------------------------------------------ #
    def get_session(self, session_id: str) -> Optional[Session]:
        return self._store.get(session_id)

    def list_sessions(self) -> list[Session]:
        return self._store.list()

    def update_session(
        self,
        session_id: str,
        name: Optional[str] = None,
        username: Optional[str] = None,
        status: Optional[SessionStatus] = None,
    ) -> Session:
        sess = self._store.get(session_id)
        if sess is None:
            raise KeyError(f"No such session: {session_id}")
        if name is not None:
            sess.name = name
        if username is not None:
            sess.username = username
        if status is not None:
            sess.status = status
        self._store.update(sess)
        self._bus.emit_app(
            AppEventKind.SESSION_UPDATED, sess.id, {"name": sess.name}
        )
        return sess

    # ------------------------------------------------------------------ #
    # test / health
    # ------------------------------------------------------------------ #
    def test_session(self, session_id: str) -> Session:
        sess = self._store.get(session_id)
        if sess is None:
            raise KeyError(f"No such session: {session_id}")
        if not sess.cookies_path:
            sess.status = SessionStatus.INVALID
            sess.error_summary = "no cookies file"
            sess.last_checked_at = _now_iso()
            self._store.update(sess)
            self._bus.emit_app(
                AppEventKind.SESSION_FAILED, sess.id,
                {"error": sess.error_summary},
            )
            return sess
        try:
            status, error = self._validator(sess.cookies_path)
            sess.status = status
            sess.error_summary = error
            sess.last_checked_at = _now_iso()
            self._store.update(sess)
            self._bus.emit_app(
                AppEventKind.SESSION_TESTED, sess.id,
                {"status": status.value, "error": error},
            )
        except Exception as exc:  # validator blew up
            sess.status = SessionStatus.ERROR
            sess.error_summary = str(exc)[:500]
            sess.last_checked_at = _now_iso()
            self._store.update(sess)
            self._bus.emit_app(
                AppEventKind.SESSION_FAILED, sess.id,
                {"error": sess.error_summary},
            )
        return sess

    # ------------------------------------------------------------------ #
    # delete / reference
    # ------------------------------------------------------------------ #
    def delete_session(self, session_id: str) -> None:
        sess = self._store.get(session_id)
        if sess is None:
            return
        if sess.cookies_path:
            try:
                Path(sess.cookies_path).unlink(missing_ok=True)
            except OSError:
                pass
        self._store.delete(session_id)

    def get_cookies_path(self, session_id: str) -> Optional[str]:
        """Resolve the cookies file for a session.

        Returns ``None`` if the session does not exist (e.g. was deleted),
        so historical jobs referencing it remain runnable without corruption.
        """
        sess = self._store.get(session_id)
        if sess is None:
            return None
        return sess.cookies_path

    def mark_used(self, session_id: str) -> None:
        sess = self._store.get(session_id)
        if sess is None:
            return
        sess.last_used_at = _now_iso()
        self._store.update(sess)

    def close(self) -> None:
        self._store.close()
