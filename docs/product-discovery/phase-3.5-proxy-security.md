# Phase 3.5 — Proxy Security

Security design for proxy credentials and sensitive metadata. **This is the
authoritative constraint for all proxy work.**

---

## Core rule

> Proxy credentials (username / password) are **never** exposed in:
> - MCP tool responses,
> - application events (event bus),
> - log records,
> - exception messages / tracebacks,
> - the SQLite proxy metadata table.

---

## Credential storage (separate from metadata)

- **Metadata** (`id, name, scheme, host, port, status, enabled, counts,
  timestamps, error_summary, has_credentials`) is stored in the `proxies` table
  of the shared SQLite store (`ProxyStore`). It contains **no** secret.
- **Credentials** are stored in a **separate, git-ignored JSON file**
  `data/proxy_secrets.json`, keyed by proxy id (`ProxySecretStore`). `data/` is
  already git-ignored. The file is written atomically (`temp` + `os.replace`).

This mirrors the session model: cookies live in git-ignored files, only metadata
in SQLite.

---

## Where credentials may exist in memory

`ProxyManager.build_scrape_proxy(proxy_id)` is the **only** code that loads a
credential and returns it — and it returns it *inside a Playwright proxy dict*
consumed by the scraper. That dict is never logged, evented, or returned to MCP.

---

## Sanitisation helpers

`proxies.py` provides `_redact(text)` and guards every external surface:

- `parse_proxy_input` never echoes the password.
- `add_proxy` / `update_proxy` arguments that contain credentials are written
  only to the secret store; the return value is a **safe dict** (`to_safe_dict`)
  that omits username/password.
- Event payloads (`PROXY_CREATED/UPDATED/TESTED/ENABLED/DISABLED/FAILED`) contain
  only `id`, `name`, `scheme`, `host`, `port`, `status`, `error_summary`.
- `error_summary` values are passed through `_redact` and truncated to 300 chars.
  `_redact` strips `user:pass@`, `password=…`, and `username=…` patterns as a
  belt-and-suspenders guard against accidental leakage.

---

## MCP surface guarantees

Every proxy MCP tool returns `Proxy.to_safe_dict()` (or a list of them), which
has **no** credential keys. `add_proxy`/`import_proxies`/`update_proxy` accept
credentials as arguments but never echo them back. `test_proxy` returns only the
health `status` and a redacted `error_summary`.

---

## Known gaps & operator guidance

1. **MCP framework argument logging.** FastMCP / the transport may log the raw
   tool *arguments* (which include the proxy password for `add_proxy` /
   `update_proxy`). We do not re-log them, but operators should ensure MCP
   transport logs are treated as sensitive. Prefer passing credentials via
   `import_proxies` from a trusted, non-logged source where possible.
2. **TLS to the proxy.** For `http` scheme proxies, credentials traverse the
   network in cleartext to the proxy. Use `https`/`socks5` proxies for
   credentialed connections in production.
3. **File permissions.** `data/proxy_secrets.json` should be restricted to the
   running user (the application does not widen permissions; operators should
   ensure the data dir is not world-readable).
4. **No secrets in backups of SQLite.** Because credentials are in a separate
   file, backing up only the DB does not leak passwords.
