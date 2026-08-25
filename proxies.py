"""Proxy management for Reelminner (Phase 3.5).

This module owns everything related to outbound proxies:

  * a typed :class:`Proxy` domain model (Step 7)
  * input parsing + validation for single + bulk import (Step 8)
  * a persistent :class:`ProxyStore` (SQLite metadata)
  * a file-backed :class:`ProxySecretStore` for credentials (Step 10)
  * a :class:`ProxyManager` service that exposes add/import/list/get/update/
    delete/enable/disable/test and usage tracking (Steps 9, 13)
  * independent, browser-free health checks (Step 9)

Security model (see docs/product-discovery/phase-3.5-proxy-security.md)
-----------------------------------------------------------------------
* Proxy *metadata* (id, name, scheme, host, port, status, enabled,
  timestamps, usage counts, error summary, ``has_credentials`` flag) is stored
  in SQLite.
* Proxy *credentials* (username / password) are stored SEPARATELY in a
  git-ignored file (``data/proxy_secrets.json``) keyed by proxy id. They are
  only ever loaded into memory to actually build a Playwright proxy dict, and
  are NEVER included in MCP responses, application events, log records, or
  exception messages.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from app_events import ApplicationEvent as AppEvent, AppEventKind, ApplicationEventBus
from events import StructuredLogger

LOG = StructuredLogger("reelminner.proxies")

_VALID_SCHEMES = {"http", "https", "socks4", "socks5"}

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class ProxyStatus(str, Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    RATE_LIMITED = "rate_limited"
    DISABLED = "disabled"
    ERROR = "error"


class NetworkMode(str, Enum):
    DIRECT = "direct"
    FIXED_PROXY = "fixed_proxy"


class ProxyError(Exception):
    """Base class for proxy errors."""


class DuplicateProxyError(ProxyError):
    """Raised when adding a proxy that already exists."""


class ProxyNotFoundError(ProxyError):
    """Raised when a referenced proxy does not exist."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return "proxy_" + uuid.uuid4().hex[:12]


# Redaction: strip anything that looks like credentials before it can land in
# a log line, event payload, or error summary.
_REDACT_URL = re.compile(r"(://[^/\s:@]+:)[^/\s:@]+(@)")
_REDACT_PW = re.compile(r"(password\s*=\s*)[^\s&]+", re.IGNORECASE)
_REDACT_AUTH = re.compile(r"(user(?:name)?\s*[:=]\s*)[^\s,}&\"']+", re.IGNORECASE)


def _redact(text: str) -> str:
    if not text:
        return text
    text = _REDACT_URL.sub(r"\1***\2", text)
    text = _REDACT_PW.sub(r"\1***", text)
    text = _REDACT_AUTH.sub(r"\1***", text)
    return text


def _safe_err(exc: BaseException) -> str:
    return _redact(str(exc))[:300]


def _safe_summary(text: str) -> str:
    return _redact(text or "")[:300]


def parse_proxy_input(raw: str) -> dict:
    """Parse a proxy string into its components.

    Accepts:
      * ``127.0.0.1:8080``
      * ``http://127.0.0.1:8080``
      * ``http://user:pass@127.0.0.1:8080``  (optional credentials)

    Returns ``{"scheme", "host", "port", "username"?, "password"?}``.
    Raises ``ValueError`` for malformed input.
    """
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("proxy string is empty")
    if "://" not in raw:
        raw = "http://" + raw
    from urllib.parse import urlparse

    parsed = urlparse(raw)
    scheme = (parsed.scheme or "http").lower()
    if scheme not in _VALID_SCHEMES:
        raise ValueError(f"unsupported proxy scheme: {scheme}")
    host = parsed.hostname
    port = parsed.port
    if not host:
        raise ValueError("proxy host is missing")
    if not port:
        raise ValueError("proxy port is missing")
    result: dict[str, Any] = {"scheme": scheme, "host": host, "port": int(port)}
    if parsed.username is not None:
        result["username"] = parsed.username
    if parsed.password is not None:
        result["password"] = parsed.password
    return result


def _health_check(
    scheme: str,
    host: str,
    port: int,
    username: Optional[str] = None,
    password: Optional[str] = None,
    timeout: float = 10.0,
    url: str = "https://www.google.com/generate_204",
) -> tuple[ProxyStatus, str]:
    """Browser-free liveness/health check through the proxy.

    This does NOT talk to Instagram. It simply verifies the proxy can establish
    an outbound connection. HTTP 429 from the probe is mapped to RATE_LIMITED.
    """
    server = f"{scheme}://{host}:{port}"
    proxy_handler = urllib.request.ProxyHandler({"http": server, "https": server})
    handlers: list[Any] = [proxy_handler]
    if username or password:
        pwd_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        pwd_mgr.add_password(None, server, username or "", password or "")
        handlers.append(urllib.request.ProxyBasicAuthHandler(pwd_mgr))
    opener = urllib.request.build_opener(*handlers)
    opener.addheaders = [("User-Agent", "Reelminner-ProxyHealthCheck/1.0")]
    try:
        resp = opener.open(url, timeout=timeout)
        code = resp.getcode()
        if code == 429:
            return ProxyStatus.RATE_LIMITED, "health probe returned 429"
        if 200 <= code < 400:
            return ProxyStatus.HEALTHY, ""
        return ProxyStatus.UNHEALTHY, f"health probe returned {code}"
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            return ProxyStatus.RATE_LIMITED, "health probe returned 429"
        return ProxyStatus.UNHEALTHY, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - we map any failure to UNHEALTHY
        return ProxyStatus.UNHEALTHY, _safe_err(exc)


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------
@dataclass
class Proxy:
    id: str
    name: str
    scheme: str
    host: str
    port: int
    status: ProxyStatus = ProxyStatus.UNKNOWN
    enabled: bool = True
    created_at: str = ""
    updated_at: str = ""
    last_checked_at: Optional[str] = None
    last_used_at: Optional[str] = None
    success_count: int = 0
    failure_count: int = 0
    error_summary: str = ""
    has_credentials: bool = False

    def to_safe_dict(self) -> dict:
        """Serialise without ever including credentials."""
        return {
            "id": self.id,
            "name": self.name,
            "scheme": self.scheme,
            "host": self.host,
            "port": self.port,
            "status": self.status.value,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_checked_at": self.last_checked_at,
            "last_used_at": self.last_used_at,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "error_summary": self.error_summary,
            "has_credentials": self.has_credentials,
        }


# ---------------------------------------------------------------------------
# Credential secret store (separate from metadata)
# ---------------------------------------------------------------------------
class ProxySecretStore:
    """Stores proxy credentials in a git-ignored JSON file under ``data/``.

    Credentials are keyed by proxy id and are NEVER returned by any method that
    participates in logging, events, or MCP responses.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._cache: Optional[dict] = None

    def _load(self) -> dict:
        if self._cache is not None:
            return self._cache
        data: dict = {}
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as fh:
                    loaded = json.load(fh)
                if isinstance(loaded, dict):
                    data = loaded
            except (json.JSONDecodeError, OSError):
                data = {}
        self._cache = data
        return data

    def _save(self, data: dict) -> None:
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, self._path)
        self._cache = data

    def set_secret(
        self,
        proxy_id: str,
        username: Optional[str],
        password: Optional[str],
    ) -> None:
        if not username and not password:
            return
        with self._lock:
            data = self._load()
            data[proxy_id] = {"username": username, "password": password}
            self._save(data)

    def get_secret(self, proxy_id: str) -> tuple[Optional[str], Optional[str]]:
        with self._lock:
            data = self._load()
            entry = data.get(proxy_id)
            if not isinstance(entry, dict):
                return (None, None)
            return (entry.get("username"), entry.get("password"))

    def delete_secret(self, proxy_id: str) -> None:
        with self._lock:
            data = self._load()
            if proxy_id in data:
                del data[proxy_id]
                self._save(data)

    def clear(self) -> None:
        with self._lock:
            self._cache = {}
            if self._path.exists():
                try:
                    self._path.unlink()
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# Metadata store (SQLite)
# ---------------------------------------------------------------------------
class ProxyStore:
    """Persistent store for proxy *metadata* (credentials live elsewhere)."""

    def __init__(self, db_path: str | Path, connect=None) -> None:
        self._path = str(db_path)
        self._conn = (connect or sqlite3.connect)(self._path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS proxies (
                id                TEXT PRIMARY KEY,
                name              TEXT NOT NULL,
                scheme            TEXT NOT NULL,
                host              TEXT NOT NULL,
                port              INTEGER NOT NULL,
                status            TEXT NOT NULL DEFAULT 'unknown',
                enabled           INTEGER NOT NULL DEFAULT 1,
                created_at        TEXT NOT NULL,
                updated_at        TEXT NOT NULL,
                last_checked_at   TEXT,
                last_used_at      TEXT,
                success_count     INTEGER NOT NULL DEFAULT 0,
                failure_count     INTEGER NOT NULL DEFAULT 0,
                error_summary     TEXT NOT NULL DEFAULT '',
                has_credentials   INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self._conn.commit()

    def add(self, proxy: Proxy) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO proxies (
                id, name, scheme, host, port, status, enabled, created_at,
                updated_at, last_checked_at, last_used_at, success_count,
                failure_count, error_summary, has_credentials
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proxy.id, proxy.name, proxy.scheme, proxy.host, proxy.port,
                proxy.status.value, int(proxy.enabled), proxy.created_at,
                proxy.updated_at, proxy.last_checked_at, proxy.last_used_at,
                proxy.success_count, proxy.failure_count, proxy.error_summary,
                int(proxy.has_credentials),
            ),
        )
        self._conn.commit()

    def get(self, proxy_id: str) -> Optional[Proxy]:
        row = self._conn.execute(
            "SELECT * FROM proxies WHERE id = ?", (proxy_id,)
        ).fetchone()
        return self._row_to_proxy(row) if row else None

    def get_by_address(self, scheme: str, host: str, port: int) -> Optional[Proxy]:
        row = self._conn.execute(
            "SELECT * FROM proxies WHERE scheme = ? AND host = ? AND port = ?",
            (scheme, host, port),
        ).fetchone()
        return self._row_to_proxy(row) if row else None

    def list_all(self) -> list[Proxy]:
        rows = self._conn.execute(
            "SELECT * FROM proxies ORDER BY created_at ASC, id ASC"
        ).fetchall()
        return [self._row_to_proxy(r) for r in rows]

    def delete(self, proxy_id: str) -> None:
        self._conn.execute("DELETE FROM proxies WHERE id = ?", (proxy_id,))
        self._conn.commit()

    def count(self) -> int:
        return int(
            self._conn.execute("SELECT COUNT(*) FROM proxies").fetchone()[0]
        )

    def close(self) -> None:
        try:
            self._conn.commit()
        except Exception:
            pass
        try:
            self._conn.close()
        except Exception:
            pass

    @staticmethod
    def _row_to_proxy(row: sqlite3.Row) -> Proxy:
        return Proxy(
            id=row["id"],
            name=row["name"],
            scheme=row["scheme"],
            host=row["host"],
            port=int(row["port"]),
            status=ProxyStatus(row["status"]),
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_checked_at=row["last_checked_at"],
            last_used_at=row["last_used_at"],
            success_count=int(row["success_count"]),
            failure_count=int(row["failure_count"]),
            error_summary=row["error_summary"],
            has_credentials=bool(row["has_credentials"]),
        )


# ---------------------------------------------------------------------------
# Manager / service
# ---------------------------------------------------------------------------
class ProxyManager:
    """Application service for proxy lifecycle + usage tracking."""

    def __init__(
        self,
        store: ProxyStore,
        secret_store: ProxySecretStore,
        event_bus: Optional[ApplicationEventBus] = None,
        health_timeout: float = 10.0,
        health_url: str = "https://www.google.com/generate_204",
        id_factory: Callable[[], str] = _new_id,
    ) -> None:
        self._store = store
        self._secrets = secret_store
        self._bus = event_bus or ApplicationEventBus()
        self._health_timeout = health_timeout
        self._health_url = health_url
        self._id_factory = id_factory

    # -- events ------------------------------------------------------------
    def _emit(self, kind: AppEventKind, payload: dict) -> None:
        # emit_app routes ApplicationEvents to subscribers; emit() is the
        # engine->application translation path and would drop our event.
        self._bus.emit_app(kind, None, payload)

    # -- internal create path ---------------------------------------------
    def _create_or_skip(
        self,
        scheme: str,
        host: str,
        port: int,
        name: Optional[str],
        username: Optional[str],
        password: Optional[str],
        on_duplicate: str = "skip",
    ) -> tuple[Proxy, bool]:
        existing = self._store.get_by_address(scheme, host, port)
        if existing is not None:
            if on_duplicate == "error":
                raise DuplicateProxyError(
                    f"proxy {scheme}://{host}:{port} already exists"
                )
            if on_duplicate == "skip":
                return existing, False
            # replace: update in place
            proxy_id = existing.id
            has_creds = bool(username) or bool(password)
            existing.scheme = scheme
            existing.host = host
            existing.port = port
            existing.name = name or existing.name
            existing.status = ProxyStatus.UNKNOWN
            existing.has_credentials = has_creds
            existing.updated_at = _now_iso()
            self._store.add(existing)
            if has_creds:
                self._secrets.set_secret(proxy_id, username, password)
            else:
                self._secrets.delete_secret(proxy_id)
            self._emit(
                AppEventKind.PROXY_UPDATED,
                {"id": proxy_id, "name": existing.name},
            )
            return existing, True

        proxy_id = self._id_factory()
        has_creds = bool(username) or bool(password)
        proxy = Proxy(
            id=proxy_id,
            name=name or f"{scheme}://{host}:{port}",
            scheme=scheme,
            host=host,
            port=int(port),
            status=ProxyStatus.UNKNOWN,
            enabled=True,
            created_at=_now_iso(),
            updated_at=_now_iso(),
            has_credentials=has_creds,
        )
        self._store.add(proxy)
        if has_creds:
            self._secrets.set_secret(proxy_id, username, password)
        self._emit(
            AppEventKind.PROXY_CREATED,
            {
                "id": proxy.id,
                "name": proxy.name,
                "scheme": proxy.scheme,
                "host": proxy.host,
                "port": proxy.port,
            },
        )
        return proxy, True

    # -- add / import ------------------------------------------------------
    def add_proxy(
        self,
        *,
        name: Optional[str] = None,
        scheme: str,
        host: str,
        port: int,
        username: Optional[str] = None,
        password: Optional[str] = None,
        on_duplicate: str = "skip",
    ) -> dict:
        proxy, _created = self._create_or_skip(
            scheme, host, int(port), name, username, password, on_duplicate
        )
        return proxy.to_safe_dict()

    def import_proxies(self, items: list[dict]) -> dict:
        added: list[str] = []
        skipped: list[str] = []
        errors: list[dict] = []
        for i, item in enumerate(items or []):
            try:
                if not isinstance(item, dict):
                    raise ValueError("each item must be a dict")
                if "raw" in item:
                    comp = parse_proxy_input(str(item["raw"]))
                    spec = {
                        "scheme": comp["scheme"],
                        "host": comp["host"],
                        "port": comp["port"],
                        "username": comp.get("username"),
                        "password": comp.get("password"),
                        "name": item.get("name"),
                    }
                else:
                    spec = item
                    if "raw" in spec:  # belt and suspenders
                        pass
                    for key in ("scheme", "host", "port"):
                        if key not in spec:
                            raise ValueError(f"missing required field: {key}")
                proxy, created = self._create_or_skip(
                    spec["scheme"],
                    spec["host"],
                    int(spec["port"]),
                    spec.get("name"),
                    spec.get("username"),
                    spec.get("password"),
                    on_duplicate="skip",
                )
                if created:
                    added.append(proxy.id)
                else:
                    skipped.append(proxy.id)
            except Exception as exc:  # noqa: BLE001
                errors.append({"index": i, "error": _safe_err(exc)})
        return {
            "added": added,
            "skipped": skipped,
            "added_count": len(added),
            "skipped_count": len(skipped),
            "error_count": len(errors),
            "errors": errors,
        }

    # -- read --------------------------------------------------------------
    def list_proxies(self) -> list[dict]:
        return [p.to_safe_dict() for p in self._store.list_all()]

    def get_proxy(self, proxy_id: str) -> Optional[dict]:
        proxy = self._store.get(proxy_id)
        return proxy.to_safe_dict() if proxy else None

    # -- update ------------------------------------------------------------
    def update_proxy(
        self,
        proxy_id: str,
        *,
        name: Optional[str] = None,
        scheme: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        enabled: Optional[bool] = None,
        status: Optional[str] = None,
    ) -> dict:
        proxy = self._store.get(proxy_id)
        if proxy is None:
            raise ProxyNotFoundError(proxy_id)
        if name is not None:
            proxy.name = name
        if scheme is not None:
            if scheme not in _VALID_SCHEMES:
                raise ValueError(f"unsupported proxy scheme: {scheme}")
            proxy.scheme = scheme
        if host is not None:
            proxy.host = host
        if port is not None:
            proxy.port = int(port)
        if enabled is not None:
            proxy.enabled = bool(enabled)
            if not proxy.enabled and proxy.status != ProxyStatus.DISABLED:
                proxy.status = ProxyStatus.DISABLED
        if status is not None:
            try:
                proxy.status = ProxyStatus(str(status))
            except ValueError:
                raise ValueError(f"unknown proxy status: {status}")
        creds_changed = username is not None or password is not None
        if creds_changed:
            u, pw = self._secrets.get_secret(proxy_id)
            u = username if username is not None else u
            pw = password if password is not None else pw
            self._secrets.set_secret(proxy_id, u, pw)
            proxy.has_credentials = bool(u) or bool(pw)
        proxy.updated_at = _now_iso()
        self._store.add(proxy)
        self._emit(
            AppEventKind.PROXY_UPDATED,
            {"id": proxy.id, "name": proxy.name, "status": proxy.status.value},
        )
        return proxy.to_safe_dict()

    # -- delete ------------------------------------------------------------
    def delete_proxy(self, proxy_id: str) -> None:
        proxy = self._store.get(proxy_id)
        if proxy is None:
            raise ProxyNotFoundError(proxy_id)
        self._store.delete(proxy_id)
        self._secrets.delete_secret(proxy_id)

    # -- enable / disable --------------------------------------------------
    def enable_proxy(self, proxy_id: str) -> dict:
        proxy = self._store.get(proxy_id)
        if proxy is None:
            raise ProxyNotFoundError(proxy_id)
        proxy.enabled = True
        if proxy.status == ProxyStatus.DISABLED:
            proxy.status = ProxyStatus.UNKNOWN
        proxy.updated_at = _now_iso()
        self._store.add(proxy)
        self._emit(
            AppEventKind.PROXY_ENABLED,
            {"id": proxy.id, "name": proxy.name},
        )
        return proxy.to_safe_dict()

    def disable_proxy(self, proxy_id: str) -> dict:
        proxy = self._store.get(proxy_id)
        if proxy is None:
            raise ProxyNotFoundError(proxy_id)
        proxy.enabled = False
        proxy.status = ProxyStatus.DISABLED
        proxy.updated_at = _now_iso()
        self._store.add(proxy)
        self._emit(
            AppEventKind.PROXY_DISABLED,
            {"id": proxy.id, "name": proxy.name},
        )
        return proxy.to_safe_dict()

    # -- test / health -----------------------------------------------------
    def test_proxy(self, proxy_id: str) -> dict:
        proxy = self._store.get(proxy_id)
        if proxy is None:
            raise ProxyNotFoundError(proxy_id)
        username, password = self._secrets.get_secret(proxy_id)
        status, err = _health_check(
            proxy.scheme,
            proxy.host,
            proxy.port,
            username,
            password,
            self._health_timeout,
            self._health_url,
        )
        proxy.status = status
        proxy.last_checked_at = _now_iso()
        if status == ProxyStatus.HEALTHY:
            proxy.success_count += 1
            proxy.error_summary = ""
        else:
            proxy.failure_count += 1
            proxy.error_summary = _safe_summary(err)
        proxy.updated_at = _now_iso()
        self._store.add(proxy)
        self._emit(
            AppEventKind.PROXY_TESTED,
            {
                "id": proxy.id,
                "status": status.value,
                "error_summary": proxy.error_summary,
            },
        )
        return proxy.to_safe_dict()

    # -- usage tracking ----------------------------------------------------
    def record_usage(self, proxy_id: str) -> None:
        proxy = self._store.get(proxy_id)
        if proxy is None:
            return
        proxy.last_used_at = _now_iso()
        proxy.updated_at = _now_iso()
        self._store.add(proxy)

    def record_success(self, proxy_id: str) -> None:
        proxy = self._store.get(proxy_id)
        if proxy is None:
            return
        proxy.success_count += 1
        proxy.updated_at = _now_iso()
        self._store.add(proxy)

    def record_failure(self, proxy_id: str, error_summary: str = "") -> None:
        proxy = self._store.get(proxy_id)
        if proxy is None:
            return
        proxy.failure_count += 1
        proxy.error_summary = _safe_summary(error_summary)
        proxy.updated_at = _now_iso()
        self._store.add(proxy)
        self._emit(
            AppEventKind.PROXY_FAILED,
            {"id": proxy.id, "error_summary": proxy.error_summary},
        )

    def mark_rate_limited(self, proxy_id: str) -> None:
        proxy = self._store.get(proxy_id)
        if proxy is None:
            return
        proxy.status = ProxyStatus.RATE_LIMITED
        proxy.updated_at = _now_iso()
        self._store.add(proxy)

    # -- build a Playwright proxy dict (internal use only) -----------------
    def build_scrape_proxy(self, proxy_id: str) -> Optional[dict]:
        """Return a Playwright proxy dict (incl. creds) or ``None``.

        Returns ``None`` when the proxy is missing, disabled, or in ERROR state
        (callers then fall back to a DIRECT connection). This is the ONLY place
        credentials leave the secret store, and it never feeds logs/events/MCP.
        """
        proxy = self._store.get(proxy_id)
        if proxy is None:
            return None
        if not proxy.enabled or proxy.status in (
            ProxyStatus.DISABLED,
            ProxyStatus.ERROR,
        ):
            return None
        username, password = self._secrets.get_secret(proxy_id)
        out: dict[str, Any] = {"server": f"{proxy.scheme}://{proxy.host}:{proxy.port}"}
        if username:
            out["username"] = username
        if password:
            out["password"] = password
        return out
