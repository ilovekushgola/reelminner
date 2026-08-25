# Phase 3.5 — MCP Architecture

**Goal:** Upgrade the Reelminner MCP server so an AI agent can manage the whole
application (jobs, sessions, results, settings, status, proxies) through a
clean service-layer contract, and add a self-contained Proxy Management system
that jobs can opt into.

**Status:** Implemented. 204 tests pass (was 169), no regressions.

---

## Layered boundaries (unchanged principle)

```
Agent / MCP client
      │  (tool calls only)
      ▼
mcp_server.py   ──  thin tool layer; validates args, returns plain dicts
      │
      ▼
ReelminnerApplication  (composition root: .jobs .results .sessions
      │                 .settings .proxies .event_bus)
      ▼
Service layer: JobManager, ResultService, SessionManager,
               SettingsService, ProxyManager
      │
      ▼
Persistence: JobStore/ResultStore/ProxyStore (SQLite + JSONL)  •  ProxySecretStore (file)
```

**Hard rule:** the MCP layer only ever calls into the application/service layer.
It never touches SQLite, JSONL files, cookie contents, proxy secret files, or
scraper internals directly. This keeps the agent boundary auditable and keeps
the storage format a private implementation detail.

---

## Composition root changes (`app.py`)

`ReelminnerApplication` gains a `.proxies` facade:

```python
self._proxy_store   = ProxyStore(self._db_path)               # metadata in the shared DB
self._proxy_secrets = ProxySecretStore(self.data_dir / "proxy_secrets.json")  # credentials
self.proxies        = ProxyManager(self._proxy_store, self._proxy_secrets,
                                   event_bus=self.event_bus)
self.jobs.proxy_resolver = self.proxies.build_scrape_proxy   # FIXED_PROXY -> Playwright dict
self.jobs.on_proxy_used  = self._on_proxy_used               # usage + success/failure tracking
```

`_on_proxy_used(proxy_id, success, error_summary)` records usage through the
`ProxyManager` and never sees raw credentials.

A process-wide singleton was (re)introduced for the MCP server:

```python
ReelminnerApplication.get_instance(data_dir=None, db_name="reelminner.db")
```

`get_instance()` is the only entry point the MCP tools use, mirroring the
original 5-tool design. It constructs the full facade lazily; no browser is
launched at construction time.

---

## Tool surface

The original 5-tool scraping contract is preserved verbatim. Phase 3.5 adds:

- **Jobs:** `create_job, start_job, pause_job, resume_job, stop_job,
  retry_job, get_job, list_jobs`
- **Sessions:** `list_sessions, get_session, import_session, test_session,
  update_session, delete_session`
- **Results:** `get_result, search_results, filter_results, sort_results,
  paginate_results, get_result_statistics` (plus the existing `export_results`)
- **Settings:** `get_settings, update_settings, reset_settings`
- **Status:** `get_application_status`
- **Proxies:** `list_proxies, get_proxy, add_proxy, import_proxies,
  update_proxy, delete_proxy, enable_proxy, disable_proxy, test_proxy`

See `phase-3.5-mcp-tool-contract.md` for the full argument/return spec.

---

## Event bus

`ProxyManager` emits application events (`PROXY_CREATED/UPDATED/TESTED/
ENABLED/DISABLED/FAILED`) through `ApplicationEventBus.emit_app`. These payloads
contain **only safe metadata** (no credentials, no host:port auth URLs). No
events are emitted for read-only operations.

---

## Non-goals (explicitly out of scope)

- Proxy rotation, pools, or automatic switching.
- CAPTCHA solving / bypass.
- Fingerprint / user-agent spoofing beyond what a fixed proxy already provides.
- UI / desktop / installer work (deferred to a later phase).
