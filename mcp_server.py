"""MCP server — lets AI agents drive the Instagram Reel Scraper over stdio.

Run:  python mcp_server.py
      (or via an MCP client configured with mcp.json / .mcp.json)

Tools (5):
  scrape_reels(urls, workers, delay, headless, with_profiles) -> dict
  get_status()                                                  -> dict
  import_cookies(json_path)                                     -> dict
  stop_scrape()                                                 -> dict
  export_results(path, fmt)                                     -> dict

Environment overrides (all optional):
  RMIN_HEADLESS, RMIN_WORKERS, RMIN_DELAY, RMIN_WITH_PROFILES

Design: exactly one scrape at a time (non-blocking threading lock).
Agent-facing tool names must stay stable — tests assert the exact surface.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
from pathlib import Path
from typing import List, Optional

# Import the engine both from source and when frozen inside the .exe.
if getattr(sys, "frozen", False):  # PyInstaller one-file
    sys.path.insert(0, str(Path(sys.executable).resolve().parent))
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from scraper import (  # noqa: E402
    DEFAULT_STATE_FILE,
    export_excel,
    export_json,
    write_csv,
)
from service import ScraperService
from app import ReelminnerApplication
from proxies import NetworkMode
from job_manager import job_to_dict as _job_to_dict
from jobs import JobStatus

from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("reelminner")

_lock = threading.Lock()      # one scrape at a time
_active_scraper: Optional[ScraperService] = None
_last_results: List = []
STATE_FILE: Path = Path(DEFAULT_STATE_FILE)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, ""))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, ""))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@mcp.tool()
def scrape_reels(
    urls: List[str],
    workers: int = 0,
    delay: float = 0,
    headless: bool = True,
    with_profiles: bool = True,
) -> dict:
    """Scrape Instagram reels by URL.

    Returns JSON-serializable dict:
      {"results": [{reel_url, username, followers, music_title, music_artist,
                    likes, comments, plays, status}, ...]}
    Each URL is scraped with the saved user session (cookies). If
    with_profiles is true, the tool also fetches each owner's followers count.
    """
    global _active_scraper, _last_results
    if not urls:
        return {"error": "urls must not be empty"}
    if not _lock.acquire(blocking=False):
        return {"error": "a scrape is already running"}
    try:
        workers = workers or _env_int("RMIN_WORKERS", 2)
        delay = delay or _env_float("RMIN_DELAY", 1.0)
        headless = _env_bool("RMIN_HEADLESS", headless)
        with_profiles = _env_bool("RMIN_WITH_PROFILES", with_profiles)
        _active_scraper = ScraperService(
            state_file=STATE_FILE, headless=headless,
            workers=workers, delay=delay,
        )
        _last_results = _active_scraper.scrape(urls, with_profiles=with_profiles)
        return {"results": [r.to_dict() for r in _last_results]}
    finally:
        _active_scraper = None
        _lock.release()


@mcp.tool()
def get_status() -> dict:
    """Return scraper readiness and the last run summary."""
    ok = sum(1 for r in _last_results if r.status == "ok")
    return {
        "session_ready": ScraperService(state_file=STATE_FILE).has_session(),
        "last_run": {"total": len(_last_results), "ok": ok},
    }


@mcp.tool()
def import_cookies(json_path: str) -> dict:
    """Import an EditThisCookie-format JSON cookie export into the session."""
    s = ScraperService(state_file=STATE_FILE, headless=True)
    try:
        ok = s.save_cookies_from_file(json_path)
        return {"imported": ok, "path": json_path}
    except Exception as exc:  # noqa: BLE001 - surface any import failure
        return {"imported": False, "error": str(exc)}


@mcp.tool()
def stop_scrape() -> dict:
    """Request a graceful stop of the running scrape (if any)."""
    global _active_scraper
    if _active_scraper is not None:
        _active_scraper.stop()
        return {"stopped": True}
    return {"stopped": False, "note": "no active scrape"}


@mcp.tool()
def export_results(path: str, fmt: str = "csv") -> dict:
    """Export the last results to a file (csv | xlsx | json)."""
    if not _last_results:
        return {"error": "no results yet - run scrape_reels first"}
    fmt = fmt.lower()
    p = Path(path)
    try:
        if fmt == "csv":
            write_csv(_last_results, p)
        elif fmt == "xlsx":
            export_excel(_last_results, p)
        elif fmt == "json":
            export_json(_last_results, p)
        else:
            return {"error": f"unsupported format: {fmt} (use csv|xlsx|json)"}
        return {"exported": str(p.resolve()), "rows": len(_last_results)}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


# ------------------------------------------------------------------------- #
# Phase 3.5 - Job management
# ------------------------------------------------------------------------- #
@mcp.tool()
def create_job(
    urls: List[str],
    workers: int = 3,
    delay: float = 2.0,
    headless: bool = False,
    with_profiles: bool = True,
    session_id: Optional[str] = None,
    network_mode: str = "direct",
    proxy_id: Optional[str] = None,
) -> dict:
    """Create a scraping job. Returns the full job state dict.

    Args:
        urls: Reel/profile URLs to scrape.
        network_mode: "direct" or "fixed_proxy".
        proxy_id: Proxy id when network_mode="fixed_proxy".
    """
    app = ReelminnerApplication.get_instance()
    try:
        mode = NetworkMode(network_mode)
    except ValueError:
        mode = NetworkMode.DIRECT
    job = app.jobs.create_job(
        urls=list(urls),
        workers=workers,
        delay=delay,
        headless=headless,
        with_profiles=with_profiles,
        session_id=session_id,
        network_mode=mode,
        proxy_id=proxy_id,
    )
    return _job_to_dict(job)


@mcp.tool()
def start_job(job_id: str) -> dict:
    """Start a previously created job."""
    app = ReelminnerApplication.get_instance()
    app.jobs.start(job_id)
    return _job_to_dict(app.jobs.get_job(job_id))


@mcp.tool()
def pause_job(job_id: str) -> dict:
    """Pause a running job (cooperative)."""
    app = ReelminnerApplication.get_instance()
    app.jobs.pause(job_id)
    return _job_to_dict(app.jobs.get_job(job_id))


@mcp.tool()
def resume_job(job_id: str) -> dict:
    """Resume a paused job from where it left off."""
    app = ReelminnerApplication.get_instance()
    app.jobs.resume(job_id)
    return _job_to_dict(app.jobs.get_job(job_id))


@mcp.tool()
def stop_job(job_id: str) -> dict:
    """Stop a running job."""
    app = ReelminnerApplication.get_instance()
    app.jobs.stop(job_id)
    return _job_to_dict(app.jobs.get_job(job_id))


@mcp.tool()
def retry_job(job_id: str) -> dict:
    """Retry a failed/interrupted job."""
    app = ReelminnerApplication.get_instance()
    app.jobs.retry(job_id)
    return _job_to_dict(app.jobs.get_job(job_id))


@mcp.tool()
def get_job(job_id: str) -> Optional[dict]:
    """Get full state for a single job."""
    app = ReelminnerApplication.get_instance()
    job = app.jobs.get_job(job_id)
    return _job_to_dict(job) if job else None


@mcp.tool()
def list_jobs(status: Optional[str] = None, limit: int = 50) -> dict:
    """List jobs, optionally filtered by status, most-recent first."""
    app = ReelminnerApplication.get_instance()
    jobs = app.jobs.list_jobs(status=status)
    jobs = jobs[: max(1, int(limit))]
    return {"jobs": [_job_to_dict(j) for j in jobs], "count": len(jobs)}


# ------------------------------------------------------------------------- #
# Phase 3.5 - Session management (metadata only; never raw cookies)
# ------------------------------------------------------------------------- #
@mcp.tool()
def list_sessions() -> dict:
    """List all sessions, returning only safe metadata."""
    app = ReelminnerApplication.get_instance()
    sessions = app.sessions.list_sessions()
    return {
        "sessions": [app.sessions.session_to_dict(s) for s in sessions],
        "count": len(sessions),
    }


@mcp.tool()
def get_session(session_id: str) -> Optional[dict]:
    """Get safe metadata for a single session."""
    app = ReelminnerApplication.get_instance()
    s = app.sessions.get_session(session_id)
    return app.sessions.session_to_dict(s) if s else None


@mcp.tool()
def import_session(name: str, cookies_path: str, source: str = "unknown", notes: Optional[str] = None) -> dict:
    """Import cookies from a Netscape/JSON file as a named session."""
    app = ReelminnerApplication.get_instance()
    session = app.sessions.import_session(name, cookies_path, source, notes)
    return app.sessions.session_to_dict(session)


@mcp.tool()
def test_session(session_id: str) -> dict:
    """Validate that a session's cookies file parses and looks usable."""
    app = ReelminnerApplication.get_instance()
    result = app.sessions.test_session(session_id)
    return {"session_id": session_id, **result}


@mcp.tool()
def update_session(session_id: str, name: Optional[str] = None, username: Optional[str] = None, status: Optional[str] = None, notes: Optional[str] = None) -> Optional[dict]:
    """Update metadata for a session (name / username / status / notes)."""
    app = ReelminnerApplication.get_instance()
    s = app.sessions.update_session(session_id, name=name, username=username, status=status, notes=notes)
    return app.sessions.session_to_dict(s) if s else None


@mcp.tool()
def delete_session(session_id: str) -> dict:
    """Delete a session (removes its cookie file)."""
    app = ReelminnerApplication.get_instance()
    app.sessions.delete_session(session_id)
    return {"session_id": session_id, "deleted": True}


# ------------------------------------------------------------------------- #
# Phase 3.5 - Result queries (never loads the whole dataset by default)
# ------------------------------------------------------------------------- #
@mcp.tool()
def get_result(job_id: str, reel_url: str) -> Optional[dict]:
    """Get a single stored result by job id + reel url."""
    app = ReelminnerApplication.get_instance()
    row = app.results.get_result(job_id, reel_url)
    return row.to_dict() if row is not None else None


@mcp.tool()
def search_results(job_id: str, text: str, page: int = 1, page_size: int = 50) -> dict:
    """Full-text search across stored results (default page=1, page_size=50)."""
    app = ReelminnerApplication.get_instance()
    rs = app.results.search_results(job_id, text, page=page, page_size=page_size)
    return rs.to_dict()


@mcp.tool()
def filter_results(job_id: str, field: str, op: str, value: str, page: int = 1, page_size: int = 50) -> dict:
    """Filter results by a field/operator/value (e.g. field='verified', op='eq', value='true')."""
    app = ReelminnerApplication.get_instance()
    rs = app.results.filter_results(job_id, field, op, value, page=page, page_size=page_size)
    return rs.to_dict()


@mcp.tool()
def sort_results(job_id: str, field: str, descending: bool = False, page: int = 1, page_size: int = 50) -> dict:
    """Return results sorted by a field."""
    app = ReelminnerApplication.get_instance()
    rs = app.results.sort_results(job_id, field, descending=descending, page=page, page_size=page_size)
    return rs.to_dict()


@mcp.tool()
def paginate_results(job_id: str, page: int = 1, page_size: int = 50) -> dict:
    """Paginate results for a job (default page=1, page_size=50)."""
    app = ReelminnerApplication.get_instance()
    rs = app.results.paginate_results(job_id, page=page, page_size=page_size)
    return rs.to_dict()


@mcp.tool()
def get_result_statistics(job_id: str) -> dict:
    """Aggregate statistics for a job's results."""
    app = ReelminnerApplication.get_instance()
    return app.results.get_result_statistics(job_id).to_dict()


# ------------------------------------------------------------------------- #
# Phase 3.5 - Settings
# ------------------------------------------------------------------------- #
@mcp.tool()
def get_settings() -> dict:
    """Return the current application settings."""
    app = ReelminnerApplication.get_instance()
    return app.settings.get_all().to_dict()


@mcp.tool()
def update_settings(settings: dict) -> dict:
    """Update settings from a nested dict, e.g. {"scraping": {"workers": 6}}.

    Validation flows through the SettingsService (same path the UI uses).
    """
    app = ReelminnerApplication.get_instance()
    app.settings.update_bulk(settings)
    return app.settings.get_all().to_dict()


@mcp.tool()
def reset_settings() -> dict:
    """Reset all settings to defaults."""
    app = ReelminnerApplication.get_instance()
    app.settings.reset()
    return app.settings.get_all().to_dict()


# ------------------------------------------------------------------------- #
# Phase 3.5 - Application status overview
# ------------------------------------------------------------------------- #
@mcp.tool()
def get_application_status() -> dict:
    """Lightweight overview: jobs/sessions/proxies by status + recent errors."""
    app = ReelminnerApplication.get_instance()
    jobs = app.jobs.list_jobs()
    jobs_by_status: dict[str, int] = {}
    recent_errors: list[dict] = []
    for j in jobs:
        key = j.status.value if hasattr(j.status, "value") else str(j.status)
        jobs_by_status[key] = jobs_by_status.get(key, 0) + 1
        if getattr(j, "error_summary", None):
            recent_errors.append(
                {"job_id": j.id, "status": key, "error": j.error_summary}
            )

    sessions = app.sessions.list_sessions()
    sessions_by_status: dict[str, int] = {}
    for s in sessions:
        key = s.status.value if hasattr(s.status, "value") else str(s.status)
        sessions_by_status[key] = sessions_by_status.get(key, 0) + 1

    proxies = app.proxies.list_proxies()
    proxies_by_status: dict[str, int] = {}
    for p in proxies:
        proxies_by_status[p["status"]] = proxies_by_status.get(p["status"], 0) + 1

    return {
        "jobs": {"total": len(jobs), "by_status": jobs_by_status},
        "sessions": {"total": len(sessions), "by_status": sessions_by_status},
        "proxies": {"total": len(proxies), "by_status": proxies_by_status},
        "recent_errors": recent_errors[:10],
    }


# ------------------------------------------------------------------------- #
# Phase 3.5 - Proxy management (no credentials in responses)
# ------------------------------------------------------------------------- #
@mcp.tool()
def list_proxies() -> dict:
    """List all proxies (metadata only; credentials are never returned)."""
    app = ReelminnerApplication.get_instance()
    proxies = app.proxies.list_proxies()
    return {"proxies": proxies, "count": len(proxies)}


@mcp.tool()
def get_proxy(proxy_id: str) -> Optional[dict]:
    """Get metadata for a single proxy (no credentials)."""
    app = ReelminnerApplication.get_instance()
    return app.proxies.get_proxy(proxy_id)


@mcp.tool()
def add_proxy(name: Optional[str] = None, scheme: str = "http", host: str = "127.0.0.1", port: int = 8080, username: Optional[str] = None, password: Optional[str] = None, on_duplicate: str = "skip") -> dict:
    """Add a single proxy. Credentials are stored separately and never returned.

    Accepts scheme in {http, https, socks4, socks5}. Duplicate address handling
    is controlled by on_duplicate: skip | error | replace.
    """
    app = ReelminnerApplication.get_instance()
    # Never echo username/password back to the caller.
    return app.proxies.add_proxy(
        name=name,
        scheme=scheme,
        host=host,
        port=int(port),
        username=username,
        password=password,
        on_duplicate=on_duplicate,
    )


@mcp.tool()
def import_proxies(items: List[dict]) -> dict:
    """Bulk-import proxies. Each item is either {"raw": "http://1.2.3.4:8080"}
    or {"scheme","host","port",[username],[password],[name]}.

    Returns {added, skipped, errors, counts}.
    """
    app = ReelminnerApplication.get_instance()
    return app.proxies.import_proxies(items)


@mcp.tool()
def update_proxy(proxy_id: str, name: Optional[str] = None, scheme: Optional[str] = None, host: Optional[str] = None, port: Optional[int] = None, username: Optional[str] = None, password: Optional[str] = None, enabled: Optional[bool] = None, status: Optional[str] = None) -> dict:
    """Update proxy metadata/credentials (credentials never returned)."""
    app = ReelminnerApplication.get_instance()
    return app.proxies.update_proxy(
        proxy_id,
        name=name,
        scheme=scheme,
        host=host,
        port=port,
        username=username,
        password=password,
        enabled=enabled,
        status=status,
    )


@mcp.tool()
def delete_proxy(proxy_id: str) -> dict:
    """Delete a proxy (also removes stored credentials)."""
    app = ReelminnerApplication.get_instance()
    app.proxies.delete_proxy(proxy_id)
    return {"proxy_id": proxy_id, "deleted": True}


@mcp.tool()
def enable_proxy(proxy_id: str) -> dict:
    """Enable a proxy."""
    app = ReelminnerApplication.get_instance()
    return app.proxies.enable_proxy(proxy_id)


@mcp.tool()
def disable_proxy(proxy_id: str) -> dict:
    """Disable a proxy (status becomes 'disabled')."""
    app = ReelminnerApplication.get_instance()
    return app.proxies.disable_proxy(proxy_id)


@mcp.tool()
def test_proxy(proxy_id: str) -> dict:
    """Run a browser-free health check through the proxy and record the result."""
    app = ReelminnerApplication.get_instance()
    return app.proxies.test_proxy(proxy_id)


# ------------------------------------------------------------------------- #
# Phase 3.6 - Performance intelligence & compute monitoring (read-only)
# ------------------------------------------------------------------------- #
@mcp.tool()
def get_system_capabilities() -> dict:
    """Return the host capability profile (no PII: no host/user/IP/MAC)."""
    app = ReelminnerApplication.get_instance()
    return app.performance.get_capabilities().to_dict()

@mcp.tool()
def get_system_performance(include_process: bool = True) -> dict:
    """Return the latest system + (optional) Reelminner process snapshot.

    Process monitoring reports the Reelminner process and its child browsers.
    """
    app = ReelminnerApplication.get_instance()
    out: dict = {"system": app.performance.get_system_snapshot()}
    if include_process:
        out["process"] = app.performance.get_process_snapshot()
    return out

@mcp.tool()
def get_job_performance(job_id: str) -> Optional[dict]:
    """Return a job's performance summary + latest sample + live snapshots."""
    app = ReelminnerApplication.get_instance()
    return app.performance.get_job_performance(job_id)

@mcp.tool()
def get_performance_history(job_id: Optional[str] = None, limit: int = 50, offset: int = 0) -> dict:
    """Return paginated performance history (job summaries and/or samples).

    With job_id set, returns that job's summaries + samples. Without it,
    returns recent job summaries across all jobs.
    """
    app = ReelminnerApplication.get_instance()
    return app.performance.get_history(job_id=job_id, limit=int(limit), offset=int(offset))

@mcp.tool()
def get_worker_recommendation() -> dict:
    """Return a worker-count recommendation derived from real job outcomes.

    Basis is Observed / Estimated / Insufficient-Data — never fabricated, and
    no running job or setting is changed.
    """
    app = ReelminnerApplication.get_instance()
    return app.performance.get_worker_recommendation()

@mcp.tool()
def get_performance_recommendations(job_id: Optional[str] = None) -> dict:
    """Return performance recommendations. Never mutates jobs or settings."""
    app = ReelminnerApplication.get_instance()
    return app.performance.get_recommendations(job_id=job_id)

# ------------------------------------------------------------------------- #
# Discovery + entry
# ------------------------------------------------------------------------- #


def registered_tools() -> List[str]:
    """Sorted list of tool names — used by tests and the SKILL.md validator."""
    tm = getattr(mcp, "_tool_manager", None)
    if tm is None:
        return []
    tools = getattr(tm, "_tools", {})
    return sorted(tools.keys())


def main() -> None:
    parser = argparse.ArgumentParser(prog="mcp_server")
    parser.add_argument(
        "--state",
        default=str(DEFAULT_STATE_FILE),
        help="storage_state.json path (default: repo storage_state.json)",
    )
    args = parser.parse_args()
    global STATE_FILE
    STATE_FILE = Path(args.state)
    mcp.run()


if __name__ == "__main__":
    main()
