# 01 — Current System

> This document describes **exactly how Reelminner works today**, based on a full
> inspection of the repository (`reelminner`, code-named **Reelminner**).
> It is a *discovery* document — nothing here is a proposal. Where the live code
> differs from the original product brief, that discrepancy is called out.

---

## 1.1 What Reelminner is today

Reelminner is a **Python/Tkinter Instagram Reel & Profile scraping toolkit**. Its core
value is a single reusable engine (`Reelminner`) that extracts structured
metadata from public Instagram Reels and the accounts that posted them. The engine is
exposed through **four front-ends** that all call the same engine:

| # | Interface | Entry file | Primary use |
|---|-----------|-----------|-------------|
| 1 | Desktop GUI | `gui.py` | Human operator, one-click scraping |
| 2 | CLI | `scraper.py` (`main`) | Power users, scripts, CI |
| 3 | MCP server | `mcp_server.py` | AI agents / LLM clients |
| 4 | Python API | `import scraper` | Embedding in other code |

---

## 1.2 Architecture map

```
┌──────────────────────────────────────────────────────────────────────┐
│                            ENTRY POINTS                                │
│                                                                        │
│   gui.py (Tk)        scraper.py (CLI)      mcp_server.py (MCP)         │
│   ReelScraperApp     main()               FastMCP tools               │
│        │                  │                     │                      │
│        │ constructs       │ constructs          │ constructs           │
└────────┼──────────────────┼─────────────────────┼──────────────────────┘
         │                  │                     │
         ▼                  ▼                     ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   Reelminner  (scraper.py)                   │
│   • scrape(urls, with_profiles, progress_cb, row_cb) -> List[ReelData] │
│   • session helpers (has_session / save_cookies / clear_session)       │
│   • concurrency: queue.Queue + N threading.Thread workers              │
│   • each worker owns one sync_playwright() Chromium context            │
│   • backoff_delay(), should_retry()                                    │
└───────────┬───────────────────────────┬──────────────────────────────┘
            │ calls                      │ calls
            ▼                            ▼
┌───────────────────────┐     ┌────────────────────────────────────────┐
│  parsers.py (pure)     │     │  Playwright Chromium (browser automation)│
│  normalize_reel_url    │     │  page.goto → _attempt_one → _extract     │
│  parse_username_*      │     │  _dismiss_overlays / _is_login_wall      │
│  parse_music_*         │     │  _is_unavailable / _scrape_profile       │
│  parse_counts_*        │     │                                          │
│  parse_caption/date/url│     └────────────────────────────────────────┘
└───────────────────────┘
            │
            ▼
   ReelData (dataclass)  →  write_csv / export_json / export_excel
```

### Entry-point flows

**GUI flow** (`gui.py`)
1. `ReelScraperApp.__init__` builds the whole window (header, session bar, URL box,
   options, action bar, results `Treeview`, log pane, status bar).
2. User pastes URLs → clicks **Scrape** → `_run_scrape(urls)` starts a background
   `threading.Thread`.
3. The thread calls `self._scraper.scrape(urls, progress_cb=…, row_cb=…)`. Both
   callbacks only `self._q.put(...)` into a thread-safe `queue.Queue`.
4. `_poll()` (scheduled every 120 ms via `self.after`) drains `_q` and updates the
   `Treeview` / log text from the **main (UI) thread**. This queue-marshaling is the
   project's thread-safety boundary.

**CLI flow** (`scraper.py::main`)
1. argparse parses positional URLs / `-f` file / flags (`--login`, `--import-cookies`,
   `--workers`, `--delay`, `--headless`, `--no-profiles`, `--state`, `-o`).
2. Constructs `Reelminner`, optionally logs in / imports cookies.
3. `scraper.scrape(urls)` → writes CSV via `write_csv`.

**Python API flow**
`Reelminner(...).scrape(urls)` returns `(rows: List[ReelData], report)`.
Caller uses `write_csv / export_json / export_excel` or reads `ReelData.to_dict()`.

**MCP flow** (`mcp_server.py`)
1. `FastMCP("reelminner")` registers 5 tools.
2. A `ScraperManager` holds a `_scrape_lock` so only one scrape runs at a time.
3. `scrape_reels` spawns a thread that runs `Reelminner.scrape`; it returns
   immediately with a job summary. `get_status`, `stop_scrape`, `import_cookies`,
   `export_results` operate on the manager.
4. Transport is **stdio** (`mcp.run()`); env overrides `RMIN_HEADLESS/RMIN_WORKERS/
   RMIN_DELAY/RMIN_WITH_PROFILES`.

---

## 1.3 Scraper engine flow (`scrape()`)

```
scrape(urls, with_profiles=True)
   │
   ├─ normalize each URL (parsers.normalize_reel_url)
   ├─ build queue.Queue(urls)
   ├─ lock = threading.Lock()
   ├─ spawn N threading.Thread(worker_fn)   # N = self.workers
   │
   └─ worker_fn(wid):
        with sync_playwright() as p:
          browser = p.chromium.launch(headless=...)
          context = browser.new_context(storage_state=..., user_agent=..., viewport=...)
          loop:
            url = q.get_nowait()  (queue.Empty → break)
            if self._stop.is_set(): break
            page = context.new_page()
            data = self._scrape_one(page, url)     # 2-attempt loop
            with lock: results.append(data)
            progress_cb(len(results), total)
            row_cb(data)
            fail_streak = fail_streak+1 if status!="ok" else 0
            time.sleep(delay + jitter + backoff_delay(fail_streak))
          context.close(); browser.close()
   │
   ├─ join all threads
   │
   └─ if with_profiles:
        second pass over results (reuse one context):
          for d in results where d.status=="ok" and username and not d.followers:
             d.followers = self._scrape_profile(page, d.username)
             row_cb(d)   # live-update followers cell
```

`_scrape_one` = two-attempt loop; `_attempt_one` does:
`page.goto(url, domcontentloaded, 60s)` → `_dismiss_overlays` → `_is_login_wall`
(→ `status="session_expired"`) → wait for a render signal → `_extract(page)` →
`_is_unavailable` (→ `status="unavailable"`) → if no username & no music, one
`page.reload()` + re-extract → `status="ok"`. On `PWTimeoutError` → `status="timeout"`;
any other exception → `status="error: <Type>"`.

---

## 1.4 Parser flow (`parsers.py`)

Pure functions of the HTML string (or URL string) alone — **no browser, no network**:
- `normalize_reel_url(raw)` — canonicalize / validate reel URL (returns `None` if not a reel).
- `parse_username_from_html` — from `og:title` / `description` meta.
- `parse_caption_from_html`, `parse_uploaded_at_from_html`, `parse_video_url_from_html` — meta tags.
- `parse_music_from_html` — brace-matching JSON scan for `music_asset_info` + "Original audio" detection.
- `parse_counts_from_html` — regex for `like_count` / `comment_count` / `play_count`.

The engine tries parsers **first**; DOM `page.evaluate` is only a secondary fallback.

---

## 1.5 Session flow

- `storage_state.json` (default `DEFAULT_STATE_FILE`) holds Playwright cookies/origins.
- `save_cookies_from_file` imports **two formats**: Playwright `{"cookies":[...]}` and
  **EditThisCookie** array; normalizes `sameSite` (`None`/`""` → `"Lax"`).
- `has_session()` returns `True` iff a non-expired `sessionid` cookie exists.
- `clear_session()` deletes the file.
- `login()` opens a visible browser for interactive QR/login; the engine never auto-rotates
  accounts — **one session file, one account**.

---

## 1.6 Browser lifecycle

- Each worker thread opens its **own** `sync_playwright()` → `chromium.launch` →
  `new_context` (with `storage_state`, fixed `USER_AGENT`, 1280×900 viewport, `en-US`).
- One `page` per URL; `page.close()` in a `finally`.
- Profile phase opens a **separate** `sync_playwright()` context (not reused from workers).
- No browser is shared across workers → N workers = N Chromium instances (memory-heavy).

---

## 1.7 Threading / concurrency

- `queue.Queue` feeds URLs to workers (work-stealing, no central scheduler).
- `threading.Lock()` guards the shared `results` list append.
- `threading.Event()` (`self._stop`) is the only stop signal; checked inside the loop.
- GUI bridges worker→UI via a second `queue.Queue` (`self._q`) drained by `self.after`.
- **No GIL-unsafe Tk calls** — callbacks only push to a queue.

---

## 1.8 Export flow

`ReelData.to_dict()` → `write_csv` (utf-8-sig, `csv.DictWriter`),
`export_json` (indent=2, ensure_ascii=False), `export_excel` (openpyxl, styled header).
The CSV column order is defined once in `ReelData.csv_columns()`.

---

## 1.9 Logging

- The engine has **no logging framework**. It calls `self.log(msg)` where `self.log` is
  a callback (default `print`). The GUI routes it through `_log_from_thread` into the
  queue; MCP/CLI let it print.
- **No log levels, no file sink, no structured/JSON logs, no per-job log files.**

---

## 1.10 Testing

- `pytest` unit layer (`tests/`): pure parsers, session import/expiry, export round-trips,
  backoff, retry, QA metrics, URL normalization, theme, MCP server, skill-vs-MCP parity.
  **Never touches the network** (fixtures in `tests/fixtures/*.html`).
- `run_qa.py`: integration harness that runs the **real** engine over `tests/corpus.txt`,
  measures fill-rate gates (`ok_rate≥0.75`, `username≥0.80`, `music≥0.60`, no
  `session_expired`, `runtime≤1800s`), writes `results/qa/qa_report.json` + CSV, exit 0 iff pass.

---

## 1.11 Build / EXE

- `build_exe.py` + `Reelminner.spec` (PyInstaller) → one-file
  `dist/Reelminner.exe`.
- `installer/Reelminner.iss` (Inno Setup) packages the EXE into a Windows
  installer (`dist/Reelminner-Setup.exe` already exists in `dist/`).
- **Caveat:** end users still must have Python + `playwright install chromium` today;
  the EXE bundles the *app* but not the browser runtime automatically.

---

## 1.12 ⚠️ Discrepancy vs. original product brief

The original brief listed capabilities that the **current code does not implement**:

| Brief claimed | Actually in `ReelData` today? |
|---------------|------------------------------|
| Full name, Bio, Verification status, Reels count | ❌ Not extracted |
| Profile URL, Reel ID, Thumbnail, Music ID, Scrape timestamp | ❌ Not extracted |
| "Owner username / follower count" | ✅ Username + followers only |

Today the engine produces exactly these 14 fields:
`username, followers, reel_url, music_title, music_artist, audio_page_url,
caption, likes, comments, plays, uploaded_at, video_url, status, is_original_audio`.

This gap is the single most important input to the gap analysis (doc `08`).
