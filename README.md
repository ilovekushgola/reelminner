# Instagram Reel Scraper

A Python tool that scrapes Instagram Reels **using your own logged-in session
(cookies)**. It opens real browser windows (Playwright + Chromium), so Instagram
sees a normal logged-in user, and collects the data points you asked for:

| Field          | Example                        |
|----------------|--------------------------------|
| `username`     | `shubham__travels`             |
| `reel_url`     | `https://www.instagram.com/reel/CxXy123AbCd/` |
| `music_title`  | `Dilbar (From "Satyameva Jayate")` |
| `music_artist` | `Neha Kakkar`                  |
| `audio_page_url` | link to the sound page       |
| plus           | caption, likes, comments, plays, upload date, video URL |

## Features

- **Uses your cookies** - either log in once from inside the app (session is
  saved to `storage_state.json`) or import a cookie JSON export
  (Playwright format or EditThisCookie).
- **Visible browsers by default** ("head on") - you can watch it scrape, which
  also avoids Instagram's headless-browser login walls.
- **Parallel workers of your choice** - pick how many browser windows scrape
  at the same time (default 3, max 8).
- **Desktop GUI** - paste URLs, click Start, view results in a table,
  export to CSV / Excel / JSON, or copy to clipboard.
- **CLI** also included for scripting.
- Detects login walls / expired sessions and marks them instead of failing
  silently. One automatic reload retry per reel.

## Setup

```powershell
cd instagram-reel-scraper
pip install -r requirements.txt
python -m playwright install chromium     # one-time browser download
```

(On this machine Python 3.11, Playwright, Chromium and openpyxl are already
installed, so you can go straight to `python gui.py`.)

## GUI usage

```powershell
python gui.py
```

1. **Log in once** - click **Login to Instagram**. A visible browser opens;
   sign in (2FA etc. normally). The moment Instagram issues your session
   cookie, it is saved to `storage_state.json` in the project folder.
   Alternative: use a cookie exporter extension (e.g. EditThisCookie) and
   click **Import cookies file**.
2. **Paste reel URLs** - one per line, or click **Load URLs from file**.
3. **Choose your worker count** (parallel browser windows) and delay.
   Keep "Headless" unchecked unless you know what you are doing -
   Instagram is much more likely to block headless browsers.
4. Click **Start Scraping**. Watch the log and progress bar.
5. Review the **Results** table. Double-click a row to open the reel;
   right-click for copy/open shortcuts. Export with **Save CSV / Excel /
   JSON** or **Copy table**. A CSV is auto-saved to `results/` when done.

## CLI usage

```powershell
# 1) log in and save the session
python scraper.py --login

# 2) scrape a list of URLs
python scraper.py -f urls.txt -w 4 --delay 2 -o out.csv

# or scrape URLs passed directly
python scraper.py "https://www.instagram.com/reel/ABC/" "https://www.instagram.com/reels/XYZ/"

# import cookies from an extension export
python scraper.py --import-cookies cookies.json

# remove the saved session
python scraper.py --clear-session
```

Options: `--headless` (invisible browsers), `-w/--workers`, `--delay`,
`--state` (custom session file), `-o/--output`.

## How the session / cookies work

- The app never asks for your password. You log in yourself in the browser
  window the app opens.
- Your session (cookies + local storage) is stored **only locally** in
  `storage_state.json` (git-ignored). Delete it with **Clear session**.
- During scraping, every worker browser loads this state, so Instagram treats
  each window as you.

## Data-point extraction details

- **Username**: `og:title` / `meta description` / article header link.
- **Music**: preferred source is Instagram's embedded page JSON
  (`music_asset_info` -> title + display_artist); fallback is the
  `a[href*="/reels/audio/"]` DOM element (longest nested span text).
- **Likes / comments / plays**: DOM (`liked_by` / `comments` links) with
  embedded-JSON fallback.
- **Reel URL**: canonical link from the page.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Executable doesn't exist` | `python -m playwright install chromium` |
| "session expired / login wall" on every reel | Click **Login to Instagram** again (session cookie expired) |
| Empty music info for some reels | Expected for reels without licensed audio ("Original audio"). The reload-retry kicks in once for slow pages |
| Login times out | Complete login in the browser window; 2FA steps included - the app waits |
| Instagram challenge / "Confirm it's you" | Complete it in the visible browser window, then press nothing - the session saves automatically once logged in |

## Legal / fair-use note

Scraping is against Instagram's Terms of Service. This tool is intended for
**personal, educational, or research use on content you are allowed to access**
(e.g. your own reels or public ones you have rights to). Use responsibly and
respect rate limits; excessive automation can get accounts flagged. No
copyrighted content is downloaded by default - only metadata.

## AI Agent / MCP Usage

The tool ships an **MCP server** (`mcp_server.py`, stdio transport) so AI
agents can drive the scraper directly — no GUI needed.

### Tools (5)

| Tool | Params | Returns |
|---|---|---|
| `scrape_reels` | `urls: list[str]`, `workers?`, `delay?`, `headless?`, `with_profiles?` | `{results: [{reel_url, username, followers, music_title, music_artist, likes, comments, plays, status}]}` |
| `get_status` | — | `{session_ready, last_run: {total, ok}}` |
| `import_cookies` | `json_path: str` | `{imported, path}` |
| `stop_scrape` | — | `{stopped}` |
| `export_results` | `path: str`, `fmt: "csv"\|"xlsx"\|"json"` | `{exported, rows}` |

### Client config (Claude Desktop / Cursor / AionUi)

Add to your MCP client config (also shipped as `.mcp.json` in this repo):

```json
{
  "mcpServers": {
    "instagram-reel-scraper": {
      "command": "python",
      "args": ["mcp_server.py"],
      "cwd": "E:\\Download\\Code\\AionUi\\Work Directory\\conversations\\2026\\08\\06\\aionrs-temp-500e1eff\\instagram-reel-scraper",
      "env": { "IRS_HEADLESS": "true" }
    }
  }
}
```

Environment overrides (see `mcp.env.example`): `IRS_HEADLESS`,
`IRS_WORKERS`, `IRS_DELAY`, `IRS_WITH_PROFILES`.

### Example agent flow

1. `get_status` — verify `session_ready: true` (else `import_cookies` first).
2. `scrape_reels` with the reel URLs and `with_profiles: true` — results
   include each owner's followers count.
3. `export_results` to `results/agent_export.csv` (or `.xlsx`/`.json`).
4. If a scrape hangs, call `stop_scrape` — exactly one scrape runs at a time.

> Heads-up for agents: run reels with a **delay ≥ 1s** and modest `workers`
> (2-3) to avoid Instagram rate-limit walls. `session_expired` status means
> the saved cookies are stale — tell the user to re-login.

## Project layout

```
instagram-reel-scraper/
├── gui.py              # tkinter desktop app (python gui.py)
├── scraper.py          # engine + CLI (python scraper.py --help)
├── mcp_server.py       # MCP server for AI agents (python mcp_server.py)
├── theme.py            # UI design tokens (colors/fonts)
├── build_exe.py        # PyInstaller build (dist\InstagramReelScraper.exe)
├── InstagramReelScraper.spec
├── installer/          # Inno Setup installer (install.bat)
├── skills/             # agent SKILL.md (docs for AI agents)
├── requirements.txt
├── storage_state.json  # created at first login (git-ignored)
└── results/            # auto-saved CSVs (git-ignored)
```

## QA loop

```powershell
python -m pytest tests/ -v        # unit layer (no network)
python run_qa.py --workers 2 --delay 2.0   # full corpus run, visible browsers
python run_qa.py --quick          # fast 1-URL iteration (headless)
python run_qa.py --report-only    # show last report
```

Full runs write `results/qa/qa_report.json` + `qa_results.csv` and exit 0
only when every gate passes (ok_rate >= 0.75, username fill >= 0.80,
music fill >= 0.60 on licensed reels, no session_expired, runtime <= 1800s).
Decision rules: `session_expired` -> re-import cookies; `timeout`/`error` ->
backoff + retry (already built in); `unavailable` -> deleted/private reel,
expected; low music fill -> add a fixture + extend `parsers.parse_music_from_html`.
