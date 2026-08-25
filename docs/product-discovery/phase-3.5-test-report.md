# Phase 3.5 — Test Report

## Summary

Phase 3.5 (MCP Enhancement + Proxy Management) is complete. The original 5-tool
MCP contract is preserved, the MCP server now manages jobs / sessions / results /
settings / status / proxies through the service layer, and a self-contained
Proxy Management system is wired into jobs via `network_mode` + `proxy_id`.

- **Before:** 169 passed.
- **After:** 204 passed (167 original + 37 added).
- **Regressions:** none.

---

## New test files

| File | Focus | Approx. count |
|------|-------|---------------|
| `tests/test_proxies.py` | `ProxyManager`/`ProxyStore`/`ProxySecretStore`: parse, add/import, list/get/update/delete, enable/disable, browser-free health check, usage tracking, **no-credential-leak events** | 16 |
| `tests/test_job_proxy_integration.py` | `network_mode`/`proxy_id` on jobs, DIRECT default, proxy_id cleared for DIRECT, resolver wiring, missing/disabled proxy → DIRECT fallback, existing jobs still work, usage recorded on finish | 8 |
| `tests/test_mcp_jobs.py` | MCP job + session + settings + status tools via the service layer | 6 |
| `tests/test_mcp_proxies.py` | MCP proxy tools return safe dicts, no credentials leak, import/list/enable/disable/delete/test | 7 |

(Plus the split `test_original_five_tools_preserved` + `test_registered_tools_full_surface`
in `tests/test_mcp_server.py`, replacing the single exact-surface test.)

---

## Regression & contract coverage

- `test_original_five_tools_preserved` asserts the 5 original tools still exist.
- `test_registered_tools_full_surface` asserts the full tool list (5 + 28 new).
- `test_skill_matches_mcp` (with mirror copy) confirms `SKILL.md` documents every
  tool name — both copies were updated and re-synced.
- `_tmp_*.py` scratch files used for ground-truth reads were removed.

---

## What is verified

1. **Backward compatibility** — original 5 tools unchanged; all 169 prior tests still green.
2. **Jobs** — create/start/pause/resume/stop/retry/get/list through `JobManager`.
3. **Sessions** — list/get/import/test/update/delete via `SessionManager`; only safe metadata exposed.
4. **Results** — get/search/filter/sort/paginate/statistics; dataset never loaded whole.
5. **Settings** — get/update (bulk nested dict → validated flat keys)/reset.
6. **Status** — `get_application_status` overview.
7. **Proxies** — full lifecycle; credentials stored separately; **never returned**.
8. **Security** — events and safe dicts contain no credentials; redaction helpers present.
9. **Proxy + Job wiring** — `FIXED_PROXY` resolves to a Playwright dict; missing/disabled/unhealthy/deleted → DIRECT fallback; usage tracked on finish.
10. **Playwright integration** — `proxy` injected into every `new_context` call.

---

## Known limitations (see design docs)

- No proxy rotation / pools / auto-switching (non-goal).
- No CAPTCHA bypass / fingerprint spoofing (non-goal).
- Rate-limited observations are recorded but never assumed to be the proxy's fault.
- MCP framework may log tool arguments; operators should treat transport logs as sensitive.
