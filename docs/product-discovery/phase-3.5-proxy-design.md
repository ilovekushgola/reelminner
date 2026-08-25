# Phase 3.5 — Proxy Design

This document covers the domain model and management layer for outbound proxies.

---

## Typed model (`Proxy`)

| Field | Type | Notes |
|------|------|-------|
| `id` | `str` | generated (`proxy_<12 hex>`) |
| `name` | `str` | defaults to `scheme://host:port` |
| `scheme` | `str` | `http` / `https` / `socks4` / `socks5` |
| `host` | `str` | |
| `port` | `int` | |
| `status` | `ProxyStatus` | see below |
| `enabled` | `bool` | |
| `created_at/updated_at` | `str` (ISO) | |
| `last_checked_at` | `str?` | from health check |
| `last_used_at` | `str?` | from job usage |
| `success_count` | `int` | |
| `failure_count` | `int` | |
| `error_summary` | `str` | redacted, never contains creds |
| `has_credentials` | `bool` | flag only; creds live elsewhere |

### ProxyStatus

`UNKNOWN, HEALTHY, UNHEALTHY, RATE_LIMITED, DISABLED, ERROR`.

---

## Status model & transitions

- New proxy → `UNKNOWN`.
- `test_proxy` → `HEALTHY` / `UNHEALTHY` / `RATE_LIMITED` (probe returns 429).
- `disable_proxy` → `DISABLED` (and `enabled=False`); `enable_proxy` → back to
  `UNKNOWN` if it was disabled.
- Usage tracking (`record_failure`) emits `PROXY_FAILED` but does **not** clobber
  the health status; `mark_rate_limited` sets `RATE_LIMITED` as an observed
  signal (it is *not* assumed to mean the proxy is at fault — see runtime doc).
- `build_scrape_proxy` returns `None` for `DISABLED`/`ERROR` (caller falls back
  to DIRECT).

---

## Input parsing & validation (`parse_proxy_input`)

Accepts both compact and URL forms:

- `127.0.0.1:8080` → `http://127.0.0.1:8080`
- `http://127.0.0.1:8080`
- `http://user:pass@127.0.0.1:8080` (optional credentials)

Invalid schemes (`ftp://…`) raise `ValueError`. Missing host/port raise
`ValueError`. The importer (`import_proxies`) never raises on a single bad row;
it records the error and continues.

---

## Duplicate handling

`ProxyStore.get_by_address(scheme, host, port)` is the dedup key. `add_proxy`
behaviour is controlled by `on_duplicate`:

- `skip` (default) → return existing proxy, no event.
- `error` → raise `DuplicateProxyError`.
- `replace` → overwrite credentials + reset status to `UNKNOWN`, emit
  `PROXY_UPDATED`.

`import_proxies` always uses `skip` and reports `added` vs `skipped` counts.

---

## Persistence

- **Metadata** → `proxies` table in the shared SQLite store (`ProxyStore`).
- **Credentials** → a separate git-ignored JSON file `data/proxy_secrets.json`
  keyed by proxy id (`ProxySecretStore`). See `phase-3.5-proxy-security.md`.

This mirrors the existing session hybrid model (cookies in git-ignored files,
metadata in SQLite).

---

## Operations (`ProxyManager`)

`add_proxy, import_proxies, list_proxies, get_proxy, update_proxy,
delete_proxy, enable_proxy, disable_proxy, test_proxy` plus usage tracking
(`record_usage, record_success, record_failure, mark_rate_limited`).

`test_proxy` runs a **browser-free** liveness check (urllib through the proxy,
default probe `https://www.google.com/generate_204`, configurable timeout) so it
does not require Instagram access or a Playwright browser.

---

## Events

`PROXY_CREATED, PROXY_UPDATED, PROXY_TESTED, PROXY_ENABLED, PROXY_DISABLED,
PROXY_FAILED`. Payloads contain only safe metadata. No events for read ops.

---

## Out of scope (non-goals)

- No rotation, pools, or automatic proxy switching.
- No CAPTCHA solving / bypass.
- No fingerprint or user-agent spoofing.
- `RATE_LIMITED` is recorded as an *observed* signal; the system never assumes a
  rate limit means the proxy is broken.
