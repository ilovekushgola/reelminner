---
name: instagram-reel-scraper
description: Scrape Instagram reels + followers via a Playwright user session. MCP tools: scrape_reels, get_status, import_cookies, stop_scrape, export_results. Use for reel metadata extraction, follower counts, and music info on Instagram reels.
---

# Instagram Reel Scraper

Scrape Instagram reels using the user's own logged-in session (cookies).
Two phases: **Phase 1** scrapes each reel (username, music, likes, status),
**Phase 2** (optional, default on) visits each owner's profile to fetch the
**followers count**.

## Prerequisites

- `storage_state.json` in the project folder (created by logging in once via
  the GUI, or by `import_cookies`). If missing, tools return
  `session_ready: false` and every reel comes back `session_expired`.
- Playwright Chromium installed (`python -m playwright install chromium`).
- Respect rate limits: keep `delay >= 1`, `workers <= 3` for large batches.

## MCP Tools

### **scrape_reels**

Signature: `scrape_reels(urls: list[str], workers?: int = 2, delay?: float = 1.0, headless?: bool = true, with_profiles?: bool = true) -> dict`

Scrapes the given reel URLs. Returns:

```json
{
  "results": [
    {
      "reel_url": "https://www.instagram.com/reel/ABC/",
      "username": "shubham__travels",
      "followers": "32K",
      "music_title": "Dilbar (From \"Satyameva Jayate\")",
      "music_artist": "Neha Kakkar",
      "likes": "12,345",
      "comments": "89",
      "plays": "1.2M",
      "status": "ok"
    }
  ]
}
```

| Param | Type | Default | Notes |
|---|---|---|---|
| `urls` | `list[str]` | — | Required. Full reel URLs (any Instagram URL form is normalized). |
| `workers` | `int` | 2 | Parallel browser windows, 1-8. Use 2-3 for big batches. |
| `delay` | `float` | 1.0 | Seconds between reels per worker. Raise to 2-3 on rate limits. |
| `headless` | `bool` | true | Agents should keep true (no visible browsers). |
| `with_profiles` | `bool` | true | Phase 2: fetch owner profile + followers. Adds time per reel. |

Status values: `ok`, `timeout` (retry already happened once), `error`,
`session_expired` (cookies stale — ask the user to re-login),
`unavailable` (deleted/private reel — expected).

Example call (via MCP client):

```json
{
  "urls": ["https://www.instagram.com/reel/ABC/", "https://www.instagram.com/reel/DEF/"],
  "with_profiles": true,
  "delay": 2
}
```

### **get_status**

Signature: `get_status() -> dict`

Readiness check — call this **first** in any workflow:

```json
{
  "session_ready": true,
  "last_run": { "total": 2, "ok": 2 }
}
```

If `session_ready` is false, use **import_cookies** or tell the user to open
the GUI and log in once.

### **import_cookies**

Signature: `import_cookies(json_path: str) -> dict`

Imports an EditThisCookie-format JSON cookie export into the saved session.
Returns `{"imported": true, "path": "..."}`. Only needed once per session
lifetime (cookies expire).

### **stop_scrape**

Signature: `stop_scrape() -> dict`

Gracefully stops the running scrape (if any). Exactly one scrape runs at a
time — a second `scrape_reels` while one is active returns
`{"error": "a scrape is already running"}`.

### **export_results**

Signature: `export_results(path: str, fmt: str = "csv") -> dict`

Exports the last scrape to `csv` | `xlsx` | `json`. Requires a prior
`scrape_reels` run:

```json
{ "path": "results/agent_export.xlsx", "fmt": "xlsx" }
```

## CLI Fallback (no MCP client)

```powershell
python scraper.py "https://www.instagram.com/reel/ABC/" "https://www.instagram.com/reel/DEF/" --workers 2 --delay 2
python scraper.py -f urls.txt -w 3 --delay 2 -o out.csv        # file input
python scraper.py --no-profiles "https://www.instagram.com/reel/ABC/"  # skip Phase 2
```

## Recommended Workflows

1. **Scrape a batch + report followers per reel**
   `get_status` → `scrape_reels(urls, with_profiles: true, delay: 2)` →
   summarize `results` (username, followers, music, status). Follow up with
   `export_results` if the user wants a file.

2. **Session health check first**
   `get_status` → if `session_ready: false`, tell the user to re-login before
   scraping (or call `import_cookies` with their export).

3. **Export to Excel for a sheet**
   `scrape_reels(...)` → `export_results(path: "results/reels.xlsx", fmt: "xlsx")`.

4. **Mid-run control**
   If a scrape takes too long: `stop_scrape`, then rerun the failed subset
   with higher `delay` / lower `workers`.

## Troubleshooting

| Symptom | Cause → Fix |
|---|---|
| All reels `session_expired` | Stale cookies → re-login (GUI) or `import_cookies`. |
| Empty `followers` for a reel | Profile fetch fallback failed (rare) → retry that URL, or run with `with_profiles: true`. |
| `timeout`/`error` statuses | Instagram slow/rate-limited → raise `delay` to 2-3, lower `workers`. |
| `unavailable` status | Deleted or private reel — expected, not an error. |
| Empty music fields | "Original audio" (no licensed music) — expected for some reels. |
| MCP returns `a scrape is already running` | Wait for it to finish or call `stop_scrape`. |
