# Phase 3.5 — MCP Tool Contract

All tools are registered on the FastMCP server in `mcp_server.py`. Every tool
resolves `ReelminnerApplication.get_instance()` and calls the appropriate service.
Tools return plain JSON-serialisable dicts (enums are serialised to `.value`).

The original 5-tool scraping contract is unchanged and still present:
`scrape_reels, get_status, import_cookies, stop_scrape, export_results`.

---

## Security invariants for all tools

- Never return raw cookies / session credentials.
- Never return proxy credentials (username/password).
- Never return internal file paths to credentials.
- Never load the entire results dataset for a job (always paginated).

---

## Jobs

### create_job
- args: `urls: list[str]`, `workers=3`, `delay=2.0`, `headless=False`,
  `with_profiles=True`, `session_id?`, `network_mode="direct"`, `proxy_id?`
- returns: full job dict (see shape below).

### start_job / pause_job / resume_job / stop_job / retry_job
- args: `job_id: str`
- returns: refreshed job dict.

### get_job
- args: `job_id: str` → job dict or `null`.

### list_jobs
- args: `status?`, `limit=50`
- returns: `{ "jobs": [...], "count": int }` (most-recent first).

### Job dict shape
```
{
  "id", "status", "session_id", "network_mode", "proxy_id",
  "total_urls", "processed", "successful", "failed",
  "blocked", "rate_limited",
  "created_at", "started_at", "ended_at", "updated_at", "error_summary"
}
```

---

## Sessions (metadata only)

- `list_sessions()` → `{ "sessions": [safe_dict], "count": int }`
- `get_session(session_id)` → safe dict or `null`
- `import_session(name, cookies_path, source="unknown", notes?)` → safe dict
- `test_session(session_id)` → `{ "session_id", "ok", "error"? , "valid"? }`
- `update_session(session_id, name?, username?, status?, notes?)` → safe dict
- `delete_session(session_id)` → `{ "session_id", "deleted": true }`

Safe dict keys: `id, name, username, source, status, created_at, updated_at,
validated_at, last_used_at, has_cookies, notes`. **No cookie contents.**

---

## Results (paginated)

- `get_result(job_id, reel_url)` → one row dict or `null`.
- `search_results(job_id, text, page=1, page_size=50)` → result-set dict.
- `filter_results(job_id, field, op, value, page=1, page_size=50)`.
- `sort_results(job_id, field, descending=False, page=1, page_size=50)`.
- `paginate_results(job_id, page=1, page_size=50)`.
- `get_result_statistics(job_id)` → statistics dict.

Result-set dict: `{ "total_matched", "total_in_job", "page", "page_size",
"has_next", "has_prev", "returned", "rows": [row.to_dict()] }`.
Default `page=1`, `page_size=50`; the service never loads the whole dataset.

---

## Settings

- `get_settings()` → `Settings.to_dict()` (nested sections).
- `update_settings(settings: dict)` → e.g. `{"scraping": {"workers": 6}}`;
  flattens to the validated flat-key format and flows through `SettingsService`.
- `reset_settings()` → resets to defaults.

---

## Status

- `get_application_status()` →
  ```
  {
    "jobs":     {"total", "by_status": {...}},
    "sessions": {"total", "by_status": {...}},
    "proxies":  {"total", "by_status": {...}},
    "recent_errors": [{"job_id","status","error"}, ...]   # max 10
  }
  ```

---

## Proxies (no credentials in responses)

- `list_proxies()` → `{ "proxies": [safe_dict], "count": int }`
- `get_proxy(proxy_id)` → safe dict or `null`
- `add_proxy(name?, scheme="http", host="127.0.0.1", port=8080, username?, password?, on_duplicate="skip")` → safe dict
- `import_proxies(items: list[dict])` → `{ "added", "skipped", "errors", counts }`
- `update_proxy(proxy_id, name?, scheme?, host?, port?, username?, password?, enabled?, status?)` → safe dict
- `delete_proxy(proxy_id)` → `{ "proxy_id", "deleted": true }`
- `enable_proxy(proxy_id)` / `disable_proxy(proxy_id)` → safe dict
- `test_proxy(proxy_id)` → safe dict with `status` from a browser-free health check.

Proxy safe dict: `id, name, scheme, host, port, status, enabled, created_at,
updated_at, last_checked_at, last_used_at, success_count, failure_count,
error_summary, has_credentials`. **No username/password ever.**
