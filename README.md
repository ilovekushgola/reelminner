<p align="center">
  <img src="assets/icon.ico" alt="Reelminner" width="96" height="96" />
</p>

<h1 align="center">🎬 Reelminner</h1>
<p align="center"><b>Instagram Reel &amp; Profile Scraper — Pro</b></p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" />
  <img alt="Playwright" src="https://img.shields.io/badge/Engine-Playwright-2EAD33?logo=playwright&logoColor=white" />
  <img alt="License" src="https://img.shields.io/badge/License-MIT-green" />
  <img alt="Platform" src="https://img.shields.io/badge/Platform-Windows%20%7C%20WSL%2FLinux-lightgrey" />
</p>

<p align="center">
  Extract <b>reel metadata</b>, <b>owner profiles</b>, <b>follower counts</b>, <b>music</b>,
  <b>likes / comments / views</b> and more from any public Instagram Reel — through a
  desktop GUI, a one‑command CLI, a Python API, or an <b>MCP server</b> that AI agents can drive.
</p>

> 💡 **Name note:** This project's final public name is **Reelminner**. The Python
> engine class is `Reelminner` (see `scraper.py`), the CLI/GUI and MCP server are
> branded `reelminner`, and the GitHub repository is **`reelminner`**. The earlier
> working codename *ReelSnipe* has been fully retired. Other name ideas are listed in
> [Name options](#-name-options).

---

## 📚 Table of Contents

- [What is Reelminner](#what-is-reelminner)
- [✨ Features](#-features)
- [🧠 How it works](#-how-it-works)
- [🏗️ Project architecture](#️-project-architecture)
- [📦 Installation](#-installation)
- [🚀 Quick Start](#-quick-start)
- [💻 Usage](#-usage)
  - [Desktop GUI](#1-desktop-gui)
  - [Command Line (CLI)](#2-command-line-cli)
  - [MCP Server (for AI agents)](#3-mcp-server-for-ai-agents)
  - [Python API](#4-python-api)
- [📊 Output format](#-output-format)
- [⚙️ Configuration](#️-configuration)
- [🗂️ Project structure](#️-project-structure)
- [🧪 Testing & QA](#-testing--qa)
- [📦 Building a standalone EXE](#-building-a-standalone-exe)
- [⚠️ Legal & ethical disclaimer](#️-legal--ethical-disclaimer)
- [🤝 Contributing](#-contributing)
- [📄 License](#-license)
- [🆘 Troubleshooting & FAQ](#-troubleshooting--faq)
- [🏷️ Name](#-name)

---

## What is Reelminner

**Reelminner** is an open‑source toolkit that pulls structured data out of Instagram Reels
and the profiles that posted them. It is built around a single, reusable engine
(`Reelminner`) that is exposed four different ways:

| Interface | File | Best for |
|-----------|------|----------|
| 🖥️ Desktop GUI | `gui.py` | Non‑technical users, one‑click scraping |
| ⌨️ CLI | `scraper.py` | Power users, batch jobs, scripts |
| 🤖 MCP server | `mcp_server.py` | AI agents / LLM workflows |
| 🐍 Python API | import `scraper` | Embedding inside your own code |

Everything shares the **same parsing, session, and rate‑limit logic**, so results are
identical no matter which front‑end you use.

---

## ✨ Features

- **Multi‑source reel parsing** — Reelminner reads data from several layers (embedded JSON,
  GraphQL responses, and a live DOM fallback) so it keeps working even when Instagram
  changes one of them.
- **Owner profile enrichment** — for every reel it can auto‑fetch the poster's
  `username`, `full_name`, `bio`, `followers`, `is_verified`, and `reels_count`.
- **Follower count extraction** — pulled via Instagram's GraphQL `UserByRestrictedView`
  / `GraphQLOwnerInfo` query, with a DOM fallback and **pagination** (handles capped
  follower figures like “1.2M” by scrolling the profile).
- **Music metadata** — reel audio `music_title`, `music_artist`, and `music_id`.
- **Engagement metrics** — `views`, `likes`, `comments`, and the direct `video_url` /
  `thumbnail`.
- **Session & login management** — interactive QR/login, cookie import from
  **EditThisCookie** exports, and a 24‑hour session refresh so you don't re‑login constantly.
- **Concurrent scraping** — a thread pool (`--workers`, default 3) with polite inter‑request
  delays (`--delay`, default 2s) and **adaptive back‑off** when Instagram throws
  `BLOCKED` / `RATE_LIMITED`.
- **Resilient status tracking** — every row carries a `status` code
  (`OK`, `PARSED_PARTIAL`, `FAILED`, `NO_DATA`, `BLOCKED`, `RATE_LIMITED`) so you know
  exactly what succeeded.
- **Multiple export formats** — CSV (default), JSON, and Excel (`.xlsx` via `openpyxl`).
- **MCP server** — five stable tools so an AI agent (Claude, Cursor, etc.) can scrape,
  check status, import cookies, stop, and export.
- **Desktop GUI** — built‑in dark theme, paste‑URL box, live results table, right‑click
  *copy URL* / *open reel*, and one‑click export.
- **Tested** — pytest suite + an end‑to‑end QA harness that enforces data‑quality gates.

---

## 🧠 How it works

```
┌────────────┐   ┌────────────┐   ┌────────────┐   ┌────────────┐
│   GUI      │   │    CLI     │   │  MCP srv   │   │  Python    │
│  gui.py    │   │ scraper.py │   │mcp_server  │   │   import   │
└─────┬──────┘   └─────┬──────┘   └─────┬──────┘   └─────┬──────┘
      └────────────────┴────────────────┴────────────────┘
                       ▼
              ┌───────────────────────┐
              │  Reelminner  │  ← the engine (scraper.py)
              │  • session / cookies   │
              │  • thread pool         │
              │  • adaptive back‑off   │
              └───────────┬───────────┘
                          ▼
              ┌───────────────────────┐
              │  parsers.py            │  ← pure extraction helpers
              │  parse_reel_page / json│
              │  parse_owner / music   │
              │  regex adapters         │
              └───────────────────────┘
```

1. **Normalize** the input URL (`normalize_reel_url`) so `/reel/X/` and `/reel/s/…/` both work.
2. **Load session** — apply saved cookies (`sessionid`, `csrftoken`, `ds_user_id`, `ig_did`,
   `mid`, `rur`) or log in.
3. **Fetch & parse** the reel page with a layered fallback:
   - `parse_reel_page` → embedded `window.__additionalData` / `sharedData` HTML JSON
   - `parse_reel_json` → raw GraphQL `GQL` response
   - `parse_graphql_reel` → `shortcodeMedia` object
   - DOM fallback → `_extract_text_raw` queries the live page for
     likes / comments / plays / followers via regex adapters.
4. **Enrich owner** (unless `--no-profiles`): fetch the profile and read
   `followers`, `full_name`, `bio`, `is_verified`, `reels_count`.
5. **Respect limits**: sleep `delay` between requests; if blocked, back off and retry.
6. **Write** rows to CSV / JSON / Excel with a `status` per row.

---

## 🏗️ Project architecture

Reelminner is a **single‑engine, multi‑interface** design. One core engine
(`Reelminner`) does all the real work; the GUI, CLI, MCP server, and
Python API are thin front‑ends that call into it. This keeps parsing, session
handling, and rate‑limiting identical across every entry point.

```
                         ┌─────────────────────────────┐
        URL(s) in ──────▶│     Reelminner     │  scraper.py
                         │  ── engine / orchestrator ──  │
                         └───────┬───────────┬──────────┘
                  run scrapes    │           │  enrich owner
                                 ▼           ▼
                    ┌────────────────┐  ┌──────────────────┐
                    │   parsers.py    │  │ session + graphql│
                    │ pure extractors │  │ (followers/music)│
                    └───────┬────────┘  └─────────┬────────┘
                            └─────────┬────────────┘
                                      ▼
                            ReelData row + status
                                      ▼
                       CSV / JSON / Excel writers
```

### Module responsibilities

| File | Role | Key public symbols |
|------|------|--------------------|
| `scraper.py` | **Core engine** + CLI. Owns the browser, session, thread pool, and writers. | `Reelminner`, `scrape()`, `login()`, `has_session()`, `save_cookies_from_file()`, `clear_session()`, `write_csv`, `export_json`, `export_excel`, `normalize_reel_url`, `csv_columns`, `ReelData`, `DEFAULT_STATE_FILE` |
| `parsers.py` | **Pure extraction helpers** — no browser, easy to unit‑test. | `parse_reel_page`, `parse_reel_json`, `parse_graphql_reel`, `parse_owner_username_from_html`, `parse_music`, `parse_count`, `parse_caption`, `parse_graphql_followers`, `parse_profile_card` |
| `gui.py` | **Tkinter desktop app**. Builds the window, menu, URL box, workers slider, results table, and export dialogs. | `ReelminnerGUI`, `build()`, `scrape()`, `export_*`, `copy_url()`, `open_reel()` |
| `theme.py` | **GUI styling** — applies the dark theme to `ttk` widgets. | `apply_dark_theme(root)` |
| `mcp_server.py` | **MCP server** — exposes the engine as 5 tools for AI agents over stdio. | `mcp` (FastMCP), `scrape_reels`, `get_status`, `import_cookies`, `stop_scrape`, `export_results` |
| `build_exe.py` | **Packaging** — PyInstaller one‑file build. | `EXE(...)`, `COLLECT`/`Analysis` |
| `run_qa.py` | **QA harness** — runs the engine over a corpus and enforces data‑quality gates. | `run_qa()`, gate checks, `qa_report.json` |

### Engine internals (`Reelminner`)

- **Session layer** — `_SESSION_COOKIE_NAMES` (`sessionid`, `csrftoken`, `ds_user_id`,
  `ig_did`, `mid`, `rur`); `_apply_cookies()`, `_refresh_if_needed()` (24h),
  `login()` (interactive QR), `clear_session()`.
- **Concurrency** — `scrape()` spins up a `ThreadPoolExecutor(max_workers=workers)`;
  each URL is handled by `_worker` → `_scrape_url`, which calls `_gather_metadata`
  (reel data) and optionally `_gather_article` (owner profile). A semaphore +
  `_sleep()` enforce politeness; `status_code` / `retcode` drive an adaptive
  retry/back‑off loop when Instagram returns `BLOCKED` / `RATE_LIMITED`.
- **Parsing pipeline (layered fallback)** — inside `_gather_metadata` the engine tries,
  in order: `parse_reel_page` (embedded HTML JSON) → `parse_reel_json` (raw GraphQL
  `GQL`) → `parse_graphql_reel` (`shortcodeMedia`) → DOM fallback via the
  `_extract_text_html` / `_extract_text_raw` adapters and the `_PATTERNS` regex list
  (likes/comments/plays/followers).
- **Profile enrichment** — `get_follower_count()` uses Instagram's GraphQL
  `UserByRestrictedView` / `GraphQLOwnerInfo` query, falling back to the DOM and
  paginating followers (`_fetch_followers` with `end_cursor`) when counts are capped.
- **Output** — rows are collected as `ReelData` dicts and written by `write_csv`
  (respecting `csv_columns`), `export_json`, or `export_excel` (needs `openpyxl`).

### Why this layout

- **Testability** — all parsing lives in `parsers.py` with no browser dependency, so
  `tests/test_parsers.py` can assert on saved HTML/JSON fixtures.
- **One source of truth** — every interface shares the same `Reelminner`, so
  a fix in the engine benefits the GUI, CLI, and MCP server simultaneously.
- **Safe packaging** — the GUI/CLI thin shells mean the PyInstaller EXE only bundles
  the engine + a minimal UI, keeping the binary small.

---

## 📦 Installation

> Requirements: **Python 3.10+** and the **Playwright** browser engine.

```bash
# 1. Clone
git clone https://github.com/ilovekushgola/reelminner.git
cd reelminner

# 2. (Recommended) create a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install the Chromium browser for Playwright
playwright install chromium
```

> **GUI only:** the desktop app uses `tkinter`, which ships with standard Python installs.
> No extra package needed. The GUI is most polished on **Windows**.

Optional dev/test tools:

```bash
pip install -r requirements-dev.txt   # pytest, coverage
```

> 💡 **Before you start:** Reelminner works best with a logged‑in Instagram session —
> some reels and *all* owner/follower data require authentication. Run
> `python scraper.py --login` once (interactive QR), or import cookies exported from the
> **EditThisCookie** browser extension with `python scraper.py --import-cookies cookies.json`.
> It only reads **public** content you're already allowed to view.

---

## 🚀 Quick Start

```bash
# Scrape a single reel from the command line
python scraper.py "https://www.instagram.com/reel/CxXYZ123/"

# …or many reels from a file (one URL per line)
python scraper.py -f urls.txt -o export.csv

# Launch the desktop GUI
python gui.py
```

---

## 💻 Usage

### 1. Desktop GUI

```bash
python gui.py
```

- Click **Login** (optional but recommended — improves success rate).
- Paste one reel URL per line into the box (or `Ctrl+A` to select all).
- Drag the **Workers** slider, then click **Scrape**.
- Watch results appear in the table.
- **Right‑click** a row to *Copy URL* or *Open Reel*.
- **Export** to CSV / Excel / JSON, or **Open results folder**.

The last results are auto‑saved to `results/_last_results.json`.

### 2. Command Line (CLI)

```bash
python scraper.py [URL ...] [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `urls` | — | One or more reel URLs (positional). |
| `-f`, `--file` | — | Text file with one reel URL per line. |
| `--login` | off | Open a browser to log in interactively (QR). |
| `--import-cookies FILE` | — | Import an **EditThisCookie** JSON export. |
| `--clear-session` | off | Delete the saved `storage_state.json`. |
| `--headless` | off | Run the browser without a window. |
| `-w`, `--workers` | `3` | Number of concurrent scrape threads. |
| `--delay` | `2.0` | Seconds to wait between requests. |
| `--state` | `storage_state.json` | Path for the saved session. |
| `-o`, `--output` | `reels_results.csv` | Output CSV path. |
| `--no-profiles` | off | Skip auto‑fetching owner follower data. |

```bash
# Headless, 5 workers, 1s delay, no profile enrichment
python scraper.py -f reels.txt -w 5 --delay 1 --headless --no-profiles -o out.csv
```

### 3. MCP Server (for AI agents)

Reelminner ships an **MCP (Model Context Protocol)** server so an AI client can drive it.

```bash
python mcp_server.py            # stdio transport
```

Configure your MCP client (`.mcp.json` is included in the repo):

```json
{
  "mcpServers": {
    "reelminner": {
      "command": "python",
      "args": ["mcp_server.py"],
      "cwd": ".",
      "env": { "RMIN_HEADLESS": "true" }
    }
  }
}
```

**Tools exposed (5, stable):**

| Tool | Signature | Purpose |
|------|-----------|---------|
| `scrape_reels` | `(urls, workers, delay, headless, with_profiles)` | Run a scrape job. |
| `get_status` | `()` | Current progress / last result summary. |
| `import_cookies` | `(json_path)` | Load cookies from an EditThisCookie file. |
| `stop_scrape` | `()` | Stop the running job. |
| `export_results` | `(path, fmt)` | Export to `csv` / `json` / `xlsx`. |

**Environment overrides:** `RMIN_HEADLESS`, `RMIN_WORKERS`, `RMIN_DELAY`, `RMIN_WITH_PROFILES`.

### 4. Python API

```python
from scraper import Reelminner, write_csv

scraper = Reelminner(workers=3, delay=2.0, headless=True)
rows, report = scraper.scrape(
    ["https://www.instagram.com/reel/CxXYZ123/"],
    with_profiles=True,
)
write_csv(rows, "out.csv")

for r in rows:
    print(r["username"], r["followers"], r["likes"], r["status"])
```

Key members of `Reelminner`:

- `scrape(urls, with_profiles=True)` → `(rows, report)`
- `login()` — interactive login
- `has_session()` / `save_cookies_from_file(path)` / `clear_session()`
- `write_csv(rows, path)`, `export_json(rows, path)`, `export_excel(rows, path)`
- `normalize_reel_url(url)` — public helper
- `csv_columns` — the ordered list of output fields
- `DEFAULT_STATE_FILE` — default `storage_state.json`

---

## 📊 Output format

Each reel becomes one row. The full CSV schema (`scraper.csv_columns`):

| Column | Description |
|--------|-------------|
| `idx` | Row index. |
| `username` | Reel owner handle (e.g. `natgeo`). |
| `followers` | Owner follower count (may be `follower_min`–`follower_max`). |
| `full_name` | Owner display name. |
| `bio` | Owner biography text. |
| `is_verified` | `True` / `False`. |
| `reels_count` | Number of reels on the owner profile. |
| `profile_url` | Link to the owner profile. |
| `reel_url` | Canonical reel URL. |
| `reel_id` | Instagram reel shortcode / ID. |
| `caption` | Reel caption text. |
| `upload_date` | Post timestamp. |
| `views` | Play / view count. |
| `likes` | Like count. |
| `comments` | Comment count. |
| `video_url` | Direct video file URL. |
| `thumbnail` | Thumbnail image URL. |
| `music_title` | Audio track title. |
| `music_artist` | Audio artist. |
| `music_id` | Audio / music ID. |
| `scrape_ts` | When this row was scraped (ISO timestamp). |
| `status` | `OK` · `PARSED_PARTIAL` · `FAILED` · `NO_DATA` · `BLOCKED` · `RATE_LIMITED`. |

---

## ⚙️ Configuration

**Cookies / session**
- Log in with `python scraper.py --login` (saves `storage_state.json`).
- Or export cookies from your browser via the *EditThisCookie* extension and run
  `python scraper.py --import-cookies cookies.json`.

**Environment variables** (used by MCP server & CLI defaults)

| Variable | Effect |
|----------|--------|
| `RMIN_HEADLESS` | `true`/`false` — run browser headless. |
| `RMIN_WORKERS` | Default worker count. |
| `RMIN_DELAY` | Default delay between requests (seconds). |
| `RMIN_WITH_PROFILES` | `true`/`false` — auto‑enrich owner profiles. |

A template is provided: copy `mcp.env.example` → `mcp.env` to override MCP defaults.

---

## 🗂️ Project structure

```
reelminner/
├── scraper.py          # Core engine: Reelminner + CLI
├── gui.py              # Tkinter desktop application
├── parsers.py          # Pure extraction helpers (HTML/JSON/music/regex)
├── mcp_server.py       # MCP server (5 tools for AI agents)
├── theme.py            # Dark‑theme styling for the GUI
├── build_exe.py        # PyInstaller build script
├── Reelminner.spec  # PyInstaller spec (one‑file EXE)
├── run_qa.py           # End‑to‑end QA harness with data‑quality gates
├── requirements.txt    # Runtime dependencies
├── requirements-dev.txt# Dev / test dependencies
├── mcp.env.example     # MCP env template
├── .mcp.json           # MCP client configuration
├── assets/             # Icons (icon.ico)
├── docs/               # SKILL.md, E2E test/fix plan
├── skills/             # Agent skill definition
├── tests/              # pytest suite + corpus.txt
└── results/            # Scrape outputs (git‑ignored)
```

---

## 🧪 Testing & QA

```bash
# Unit / integration tests
pytest -q

# End‑to‑end data‑quality run (uses your saved session)
python run_qa.py                 # full run over tests/corpus.txt
python run_qa.py --quick         # 1 URL, headless, fast iteration
python run_qa.py --url <reel>    # custom single URL
python run_qa.py --report-only   # show last qa_report.json
```

The QA harness enforces gates such as parsed‑rate, verified‑rate, non‑empty‑rate,
blocked‑rate, and max runtime, and writes `results/qa/qa_report.json` +
`qa_results.csv`.

---

## 📦 Building a standalone EXE

On Windows, produce a portable `.exe` (no Python needed by end users):

```bash
pip install pyinstaller
python build_exe.py
```

Output: `dist/Reelminner.exe` (one‑file build via `Reelminner.spec`).

---

## ⚠️ Legal & ethical disclaimer

> Reelminner is provided **for educational and authorized/personal use only**.
>
> - Scraping Instagram may violate its **Terms of Service**. Use it only on
>   content you own or are permitted to access.
> - Respect rate limits (`--delay`, fewer `--workers`) and **do not** use it for
>   spam, harassment, or commercial bulk extraction.
> - You are responsible for how you use this tool and for complying with
>   applicable laws (incl. GDPR / privacy regulations) in your jurisdiction.
> - The authors are **not affiliated with Instagram/Meta** and accept no liability.

---

## 🆘 Troubleshooting & FAQ

**`playwright` says the browser isn't installed / pages won't open**
→ Make sure you ran both `pip install -r requirements.txt` **and**
`playwright install chromium`. Without the Chromium download nothing will launch.

**Most fields are empty, or I get `BLOCKED` / `RATE_LIMITED`**
→ Log in (`python scraper.py --login`) or import cookies, then slow down:
`--delay 4` and fewer workers (`-w 1`). Instagram throttles anonymous/unauthenticated
traffic hardest, so an authenticated session is the single biggest success factor.

**A reel returns `NO_DATA`**
→ The post may be private, deleted, or region‑locked, or Instagram served a login wall.
Try again with a logged‑in session.

**The GUI window won't open or fonts look wrong**
→ The GUI uses Python's built‑in `tkinter`. On Windows it's most polished. On Linux/macOS
install the Tk package if the window fails to launch (e.g. `sudo apt install python3-tk`).

**`ModuleNotFoundError` when I run a script**
→ You're likely outside the repo or its virtual environment. `cd` into the project folder
and activate the venv (`.venv\Scripts\activate` on Windows, `source .venv/bin/activate`
on macOS/Linux) before running `python scraper.py`.

**How do I scrape lots of reels at once?**
→ Put one URL per line in a text file and run
`python scraper.py -f urls.txt -o out.csv`.

**Can an AI agent use this?**
→ Yes — run `python mcp_server.py` and point any MCP client (Claude Desktop, Cursor, etc.)
at the included `.mcp.json`. See [MCP Server](#3-mcp-server-for-ai-agents).

---

## 🤝 Contributing

1. Fork the repo and create a feature branch.
2. `pip install -r requirements-dev.txt`
3. Add/adjust tests in `tests/`; run `pytest` and `python run_qa.py --quick`.
4. Open a pull request describing the change and the QA result.

---

## 📄 License

Released under the **MIT License** — see [LICENSE](LICENSE).

---

## 🏷️ Name

The project's final public name is **Reelminner** ("Reel miner"). Earlier internal
codenames have been retired. If you fork it you can rename it to anything you like —
just update the title in `gui.py` and this README.

<p align="center">Made with ❤️ for the open‑source scraping community.</p>
