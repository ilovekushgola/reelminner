# 03 — Feature Inventory

> Status tags:
> ✅ Existing & working · 🟡 Existing but incomplete · 🧪 Experimental/unreliable ·
> ❌ Missing (claimed in brief but not in code)

Each feature lists where it is implemented, how it works, maturity, limitations, and
which interfaces expose it (GUI / CLI / MCP), plus whether it belongs in the future desktop app.

---

## 3.1 Scraping

| Feature | Where | How it works | Maturity | Limits | GUI | CLI | MCP | Future |
|---------|-------|--------------|----------|--------|-----|-----|-----|--------|
| Reel URL normalization | `parsers.normalize_reel_url` | canonicalize + validate `/reel/`,`/reels/`,`/p/` | ✅ solid | none | ✅ | ✅ | ✅ | ✅ |
| Single reel metadata (username, music, caption, likes, comments, plays, uploaded_at, video_url) | `scraper._extract` + `parsers.*` | layered: parsers first, DOM fallback | ✅ solid | DOM fallback brittle if IG markup changes | ✅ | ✅ | ✅ | ✅ |
| Original-audio detection | `parsers.parse_music_from_html` | `is_original_audio` flag | ✅ | — | ✅ | ✅ | ✅ | ✅ |
| Per-reel retry (1×) | `scraper._scrape_one` + `should_retry` | retry timeout/error once | ✅ | only 1 retry; no backoff across retries | ✅ | ✅ | ✅ | ✅ |
| Reload-on-empty | `scraper._attempt_one` | reload if no username & no music | ✅ | heuristic | ✅ | ✅ | ✅ | ✅ |

## 3.2 Profile Enrichment

| Feature | Where | Maturity | Limits | GUI | CLI | MCP | Future |
|---------|-------|----------|--------|-----|-----|-----|--------|
| Follower count | `scraper._scrape_profile` (Phase 2) | ✅ working | single value; pagination only when capped | ✅ | ✅ (toggle `--no-profiles`) | ✅ (`with_profiles`) | ✅ |
| **Full name / Bio / Verified / Reels count / Profile URL** | `scraper._scrape_profile` + `parsers.parse_profile_card_from_html` | ✅ working (Phase 1) | same source as follower count; best-effort when profile markup changes | ✅ (export) | ✅ (export) | ✅ (export) | ✅ |
| **Derived media fields** (reel_id, profile_url, music_id, thumbnail, scrape_ts) | `_extract` + `parsers.parse_reel_id_from_url` / `parse_thumbnail_from_html` / `parse_music_id_from_html` | ✅ working (Phase 1) | reel_id from URL, thumbnail from og:image, music_id from music JSON, scrape_ts from timestamp | ✅ (export) | ✅ (export) | ✅ (export) | ✅ |

## 3.3 Session Management

| Feature | Where | Maturity | Limits | GUI | CLI | MCP | Future |
|---------|-------|----------|--------|-----|-----|-----|--------|
| Has-valid-session check | `has_session()` | ✅ | only checks `sessionid` expiry | ✅ | ✅ | ✅ | ✅ |
| Cookie import (Playwright + EditThisCookie) | `save_cookies_from_file` | ✅ robust | — | ❌ (GUI uses login) | ✅ | ✅ | ✅ |
| Interactive login (QR) | `login()` | ✅ | visible browser only | ✅ | ✅ | ❌ | ✅ |
| Clear session | `clear_session()` | ✅ | — | ✅ | ✅ | ❌ | ✅ |
| **Session health monitoring / refresh / multi-account rotation** | — | ❌ missing | one file, one account, no rotation | ❌ | ❌ | ❌ | ✅ (planned) |

## 3.4 Browser Management

| Feature | Where | Maturity | Limits | Future |
|---------|-------|----------|--------|--------|
| Per-worker Chromium context | `scrape()` worker_fn | ✅ works | N workers = N browsers (RAM heavy) | ✅ but optimize (shared context pool) |
| Overlay dismissal | `_dismiss_overlays` | ✅ | heuristic | ✅ |
| Login-wall detection | `_is_login_wall` | ✅ | markup-based | ✅ |
| **Headless default / bundled browser** | `headless` flag | 🟡 manual | browser not auto-bundled for end users | ✅ (auto-bundle) |

## 3.5 Concurrency

| Feature | Where | Maturity | Limits | Future |
|---------|-------|----------|--------|--------|
| Worker pool (queue + threads) | `scrape()` | ✅ | thread-per-worker, no async | ✅ (keep or move to async backend) |
| Stop signal | `self._stop` Event | ✅ | only stop-all, no pause/resume | ✅ + pause/resume |

## 3.6 Rate Limiting

| Feature | Where | Maturity | Limits | Future |
|---------|-------|----------|--------|--------|
| Inter-request delay + jitter | `scrape()` | ✅ | fixed base + random jitter | ✅ + adaptive per-account |
| Exponential backoff on failures | `backoff_delay` | ✅ unit-tested | capped 30s | ✅ |
| Blocked / rate-limit status | status strings | ✅ | string only, no structured reason | ✅ structured |

## 3.7 Data Processing

| Feature | Where | Maturity | Limits | Future |
|---------|-------|----------|--------|--------|
| Structured record (`ReelData`) | `scraper.ReelData` | ✅ 14 fields | missing rich profile fields (see 3.2) | ✅ extend |
| **Deduplication / duplicate detection** | — | ❌ missing | GUI dedupes input URLs only | ✅ (planned) |
| **Search / filter / sort** | — | ❌ missing | none in engine | ✅ (Data Explorer) |

## 3.8 Exporting

| Feature | Where | Maturity | Limits | GUI | CLI | MCP | Future |
|---------|-------|----------|--------|-----|-----|-----|--------|
| CSV | `write_csv` | ✅ | utf-8-sig | ✅ | ✅ | ✅ (`export_results`) | ✅ |
| JSON | `export_json` | ✅ | — | ✅ | ✅ | ✅ | ✅ |
| Excel | `export_excel` | ✅ (needs openpyxl) | styling basic | ✅ | ✅ | ✅ | ✅ |
| **Export filtered subset** | — | ❌ missing | export is all-or-nothing | ❌ | ❌ | ❌ | ✅ |

## 3.9 MCP

| Feature | Where | Maturity | Limits | Future |
|---------|-------|----------|--------|--------|
| 5 tools (scrape/get_status/import_cookies/stop/export) | `mcp_server.py` | ✅ | stdio only | ✅ + SSE/HTTP |
| Single-scrape lock | `_scrape_lock` | ✅ | in-memory | ✅ |
| **Real-time progress events** | — | ❌ missing | request/response only | ✅ (WebSocket/SSE) |
| **MCP manager UI** | — | ❌ missing | no UI to start/stop/config | ✅ (MCP Manager screen) |

## 3.10 GUI

| Feature | Where | Maturity | Limits | Future |
|---------|-------|----------|--------|--------|
| Paste URLs + scrape | `gui.py` | ✅ | monolithic class | 🔄 replace |
| Live results table + log | `gui.py` + `_q` | ✅ | poll 120ms | ✅ reimplement |
| Right-click copy/open | `gui.py` | ✅ | — | ✅ |
| Export buttons | `gui.py` | ✅ | — | ✅ |
| Workers/delay/headless toggles | `gui.py` | ✅ | not persisted | ✅ + persisted settings |
| **Dashboard / Job history / Data Explorer / Settings / MCP UI** | — | ❌ missing | — | ✅ (planned screens) |

## 3.11 CLI

| Feature | Where | Maturity | Future |
|---------|-------|----------|--------|
| Full flag set | `scraper.main` | ✅ | ✅ keep |
| **Persistent config / profiles** | — | ❌ missing | ✅ (optional) |

## 3.12 Testing

| Feature | Where | Maturity | Future |
|---------|-------|----------|--------|
| Unit tests (parsers/session/export/backoff/retry/qa) | `tests/` | ✅ strong, no-network | ✅ expand |
| E2E QA gates | `run_qa.py` | ✅ | ✅ CI |
| **GUI tests** | `test_gui_columns.py` (mocked) | 🟡 thin | ✅ (future desktop tests) |
| **Concurrency / race tests** | — | ❌ missing | ✅ |
| **CI pipeline** | — | ❌ missing | ✅ |

## 3.13 Packaging

| Feature | Where | Maturity | Limits | Future |
|---------|-------|----------|--------|--------|
| One-file EXE | `build_exe.py` | ✅ | — | ✅ |
| Windows installer | `installer/*.iss` | ✅ base | no auto browser/runtime bundle | ✅ + bundle |
| **Auto-managed Python/Playwright/Chromium** | — | ❌ missing | end user must install deps | ✅ critical |
| **Code signing** | `SIGNING.md` (guide only) | 🟡 doc | not wired into build | ✅ automate |
