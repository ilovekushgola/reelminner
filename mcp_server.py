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
  IRS_HEADLESS, IRS_WORKERS, IRS_DELAY, IRS_WITH_PROFILES

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
    InstagramReelScraper,
    export_excel,
    export_json,
    write_csv,
)

from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("instagram-reel-scraper")

_lock = threading.Lock()      # one scrape at a time
_active_scraper: Optional[InstagramReelScraper] = None
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
        workers = workers or _env_int("IRS_WORKERS", 2)
        delay = delay or _env_float("IRS_DELAY", 1.0)
        headless = _env_bool("IRS_HEADLESS", headless)
        with_profiles = _env_bool("IRS_WITH_PROFILES", with_profiles)
        _active_scraper = InstagramReelScraper(
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
        "session_ready": InstagramReelScraper(state_file=STATE_FILE).has_session(),
        "last_run": {"total": len(_last_results), "ok": ok},
    }


@mcp.tool()
def import_cookies(json_path: str) -> dict:
    """Import an EditThisCookie-format JSON cookie export into the session."""
    s = InstagramReelScraper(state_file=STATE_FILE, headless=True)
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
