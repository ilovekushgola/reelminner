# Phase 3.6 — MCP Performance Tools

> The six read-only MCP tools added for the Performance Intelligence system.
> App-layer only; backward compatible (strictly additive); no credential exposure.

## 1. Surface

All tools are registered via `@mcp.tool()` in `mcp_server.py` and appear in
`registered_tools()`. The MCP server surface grew from 38 → 44 tools; existing
tools are unchanged (backward compatible). `test_mcp_server.EXPECTED_TOOLS`
and `skills/reelminner/SKILL.md` (plus its mirror) list all six.

## 2. Tools

### `get_system_capabilities() -> dict`
Host profile. Returns `SystemCapabilities.to_dict()` (OS, CPU logical/physical,
RAM, disk, GPU-best-effort). **No PII.**

### `get_system_performance(include_process: bool = True) -> dict`
```json
{ "system": { ...snapshot }, "process": { ...snapshot } }
```
`process` is omitted when `include_process=False`. Snapshots are the latest
captured by the monitors (may be `null` before the first tick).

### `get_job_performance(job_id: str) -> dict | None`
```json
{
  "job_id": "...",
  "summary": { ... } | null,
  "latest_sample": { ... } | null,
  "system_snapshot": { ... } | null,
  "process_snapshot": { ... } | null
}
```
Returns `null` summary/sample for an unknown job. Never raises on missing jobs.

### `get_performance_history(job_id: Optional[str] = None, limit: int = 50, offset: int = 0) -> dict`
- With `job_id`: returns that job's `summaries` (one) + paginated `samples`,
  plus `total_samples`.
- Without `job_id`: returns recent job `summaries` (paginated) with `count` and
  `total`.
- `limit` is clamped to 1–500. This keeps responses bounded (no raw-sample
  flooding).

### `get_worker_recommendation() -> dict`
Global, data-driven worker-count suggestion:
```json
{ "kind": "worker_count", "basis": "...", "confidence": "...",
  "message": "...", "suggested_workers": 3 | null }
```
`basis` ∈ `Observed` / `Estimated` / `Insufficient-Data`.

### `get_performance_recommendations(job_id: Optional[str] = None) -> dict`
- With `job_id`: returns that job's recommendations (`network`/`memory`/`cpu`/
  `worker_count`).
- Without `job_id`: returns the global worker recommendation in a list.
- Always returns a list; never mutates jobs or settings.

## 3. Guarantees

- **Read-only.** No tool writes settings, starts/stops jobs, or touches proxies.
- **App-layer only.** Each tool calls `ReelminnerApplication.get_instance()
  .performance.*` — it never reaches into storage or credentials directly.
- **No secrets.** Returned dicts contain at most `proxy_id` (a reference), never
  proxy host/credentials, cookies, or target URLs.
- **Backward compatible.** The six tools are additive; no existing tool's name,
  signature, or behavior changed.
- **Pagination / summarization.** History is capped and paginated; samples are
  not streamed in full.

## 4. Example (via MCP client)

```
get_system_capabilities()
  -> { "os_name": "Windows", "cpu_logical": 8, "total_ram_bytes": 17179869184, ... }

get_worker_recommendation()
  -> { "kind": "worker_count", "basis": "Insufficient-Data",
       "confidence": "UNKNOWN",
       "message": "Insufficient data: run jobs with different worker counts ...",
       "suggested_workers": null }
```
