# Phase 3.5 — Proxy Runtime Design

How a proxy is selected and consumed by the scraper at runtime.

---

## Network modes (`NetworkMode`)

- `DIRECT` (default) — no proxy; the job scrapes from the machine's real egress.
- `FIXED_PROXY` — the job uses exactly one proxy, identified by `proxy_id`.

A `JobConfig` carries `network_mode` and `proxy_id`. These live in the job's
JSON config blob, so **no schema migration** was needed and pre-existing jobs
(always `DIRECT`, `proxy_id=None`) keep working unchanged.

---

## Resolution flow

```
create_job(network_mode=FIXED_PROXY, proxy_id="proxy_x")
        │
        ▼
JobManager.create_job → JobConfig(network_mode, proxy_id)
        │  (job persisted)
        ▼
start_job(job)
        │
        ▼
JobManager._resolve_proxy(job)
        │  - if mode != FIXED_PROXY or no proxy_id → None
        │  - else call self._proxy_resolver(proxy_id)
        │       (wired to ProxyManager.build_scrape_proxy)
        │  - if resolver returns None → emit PROXY_FAILED warning,
        │    fall back to DIRECT
        ▼
_build_scraper(job, proxy_dict)  → factory(**kwargs, proxy=proxy_dict)
        │
        ▼
ScraperService(headless=…, …, proxy=proxy_dict)
        │
        ▼
Reelminner(…, proxy=proxy_dict)
        │  new_context(**kwargs, proxy=self._proxy)  ← Playwright proxy dict
        ▼
Playwright browser context routes traffic through the proxy.
```

---

## `build_scrape_proxy(proxy_id)` contract

Returns a Playwright proxy dict:

```python
{"server": "scheme://host:port", "username": …, "password": …}
```

…or `None` when the proxy is **missing**, **disabled**, or in `ERROR` state.
It is the *only* place proxy credentials leave the secret store, and it never
feeds logs / events / MCP responses.

---

## Behaviour for missing / disabled / unhealthy / deleted proxy

| Case | Behaviour |
|------|-----------|
| `proxy_id` absent | `DIRECT` (no proxy). |
| proxy missing/deleted | resolver → `None` → fall back to `DIRECT` + `PROXY_FAILED` warning event. |
| proxy `disabled` (`DISABLED`) | `build_scrape_proxy` → `None` → `DIRECT` fallback. |
| proxy `ERROR` | `None` → `DIRECT` fallback. |
| proxy `UNHEALTHY` | **still attempted** (may be transient); not blocked. |
| proxy `HEALTHY`/`UNKNOWN` | used normally. |

Rationale: silently failing the whole job because a proxy is unavailable is
harsher than transparently falling back to a direct connection — the user keeps
getting data, and the fallback is surfaced via an event + the job's error
summary.

---

## Playwright integration points

`Reelminner.__init__(…, proxy=None)` stores `self._proxy`. Every
`browser.new_context(...)` call injects `proxy=self._proxy`:

- `launch_browser`
- per-worker `_launch_worker`
- `_login`

Playwright accepts `proxy` per-context, so each worker/browser gets the same
fixed proxy. No global/process-wide proxy is set.

---

## Usage tracking (Step 13)

After a FIXED_PROXY job finishes, `JobManager._run` (finally-block) calls
`self._on_proxy_used(proxy_id, success, error_summary)` **only if the proxy was
actually used** (i.e. resolution succeeded). `ReelminnerApplication._on_proxy_used`
forwards to `ProxyManager.record_usage` + `record_success`/`record_failure`.

Important: a blocked / rate-limited result is recorded as an *observation*
(`mark_rate_limited` sets `RATE_LIMITED` status) but is **never assumed to mean
the proxy is broken** — Instagram-side limits are captured separately from proxy
health.

---

## Resource limits

- One proxy per job (no pools, no fan-out across proxies).
- Health checks run in-process (urllib), so no extra browser per test.
- `ProxySecretStore` writes atomically (temp file + `os.replace`) to avoid
  corrupting credentials if the process is interrupted.
