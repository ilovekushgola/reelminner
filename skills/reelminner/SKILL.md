---
name: reelminner
description: Scrape Instagram reels + followers via a Playwright user session. MCP tools manage the full application — jobs, sessions, results, settings, proxies, and status — plus the core scraping tools scrape_reels, get_status, import_cookies, stop_scrape, export_results. Use for reel metadata extraction, follower counts, music info, and end-to-end job/proxy orchestration on Instagram reels.
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

## Management Tools (Phase 3.5)

These tools let an agent drive the whole Reelminner application through the
service layer (never touching SQLite, JSONL, cookies, or scraper internals).

### Jobs
- **create_job**(urls, workers?, delay?, headless?, with_profiles?, session_id?, network_mode?, proxy_id?) → full job state dict.
- **start_job**(job_id) — run a created job.
- **pause_job**(job_id) — cooperative pause (workers finish current reel).
- **resume_job**(job_id) — resume from the last processed reel.
- **stop_job**(job_id) — graceful stop.
- **retry_job**(job_id) — re-run a failed/interrupted job.
- **get_job**(job_id) → single job state (status, totals, processed, successful/failed/blocked/rate-limited counts, session used, proxy used, timestamps, error summary).
- **list_jobs**(status?, limit?) → jobs most-recent first.

### Sessions (metadata only — never raw cookies)
- **list_sessions**() → safe session metadata.
- **get_session**(session_id) → safe metadata for one session.
- **import_session**(name, cookies_path, source?, notes?) → import a cookie file as a named session.
- **test_session**(session_id) → validate the cookie file parses.
- **update_session**(session_id, name?, username?, status?, notes?) → edit metadata.
- **delete_session**(session_id) → remove the cookie file.

### Results (never load the whole dataset; paginated)
- **get_result**(job_id, reel_url) → one stored row.
- **search_results**(job_id, text, page?, page_size?) → full-text search.
- **filter_results**(job_id, field, op, value, page?, page_size?) → field filter.
- **sort_results**(job_id, field, descending?, page?, page_size?) → sorted page.
- **paginate_results**(job_id, page?, page_size?) → plain page (default 1/50).
- **get_result_statistics**(job_id) → aggregates (successful/failed/blocked/rate-limited, engagement).

### Settings
- **get_settings**() → current settings.
- **update_settings**(settings: dict) → update via `{"section": {"key": value}}` (validated).
- **reset_settings**() → restore defaults.

### Status
- **get_application_status**() → jobs/sessions/proxies by status + recent errors.

### Proxies (credentials stored separately; never returned)
- **list_proxies**() → proxy metadata.
- **get_proxy**(proxy_id) → one proxy's metadata.
- **add_proxy**(name?, scheme, host, port, username?, password?, on_duplicate?) → add one.
- **import_proxies**(items) → bulk import (raw strings or structured dicts).
- **update_proxy**(proxy_id, name?, scheme?, host?, port?, username?, password?, enabled?, status?) → edit.
- **delete_proxy**(proxy_id) → remove proxy + its stored credentials.
- **enable_proxy**(proxy_id) / **disable_proxy**(proxy_id) — toggle.
- **test_proxy**(proxy_id) → browser-free health check; records status.

### Performance (Phase 3.6) — read-only observability
- **get_system_capabilities**() → host profile (OS / CPU logical+physical / RAM / disk / GPU best-effort). No PII (no host/user/IP/MAC).
- **get_system_performance**(include_process?) → latest system snapshot + optional Reelminner process & child-browser snapshot.
- **get_job_performance**(job_id) → job performance summary + latest sample + live system/process snapshots.
- **get_performance_history**(job_id?, limit?, offset?) → paginated job summaries and/or samples.
- **get_worker_recommendation**() → data-driven worker-count suggestion (basis: Observed / Estimated / Insufficient-Data).
- **get_performance_recommendations**(job_id?) → recommendations only. Never mutates running jobs or settings.

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
