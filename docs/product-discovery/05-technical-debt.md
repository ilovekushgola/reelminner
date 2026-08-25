# 05 — Technical Debt & Risks

> Priority: 🔴 Critical · 🟠 High · 🟡 Medium · 🟢 Low.
> **Nothing here is to be fixed in this discovery phase.** These are future actions.

---

## 🔴 Critical

| Issue | Sev | Location | Why it matters | Recommended future action |
|-------|-----|----------|----------------|---------------------------|
| **No persistent storage / job history** | 🔴 | whole app | Results live only in memory + flat CSV; no DB → no history, resume, dashboards, analytics | Introduce SQLite (`jobs`, `results`, `logs`, `sessions` tables) behind a repository interface |
| **No auto-managed runtime for end users** | 🔴 | packaging (`build_exe.py`, `installer/*.iss`) | The "download EXE, no Python/Playwright install" goal is unmet; users still run `playwright install chromium` | Bundle packaged Python + Playwright Chromium in installer; verify at launch; fail gracefully |
| **No structured logging** | 🔴 | `scraper.py` (`self.log=print`), `gui.py`, `mcp_server.py` | Only a print callback; no levels, no files, no per-job logs → impossible to debug production issues or build a Logs screen | Add `logging`-based logger with levels + file sink + JSON lines; engine emits structured events |

---

## 🟠 High

| Issue | Sev | Location | Why it matters | Recommended future action |
|-------|-----|----------|----------------|---------------------------|
| **Business logic embedded in `gui.py`** | 🟠 | `gui.py` `ReelScraperApp` | Orchestration still lives in a `tk.Tk` subclass. **Mitigated in Phase 1**: a `ScraperService` facade now isolates the engine; GUI/MCP call it. Full Tk→premium swap remains Phase 7. | Keep `ScraperService` as the only boundary; replace Tk shell in Phase 7 |
| **Single session, no rotation/health** | 🟠 | `scraper.py` session helpers | One `storage_state.json`, one account; no health check, refresh, or rotation → fragile at scale, easy blocks | `SessionManager` with multiple accounts, health ping, auto-refresh, rotation |
| **Per-worker full browser (N browsers)** | 🟠 | `scrape()` worker_fn | Each worker launches its own Chromium → high RAM/CPU; doesn't scale past ~5 workers | Shared browser/context pool with worker semaphore; or async backend |
| **MCP is stdio-only, no real-time events** | 🟠 | `mcp_server.py` | AI clients cannot receive live progress; no SSE/HTTP transport | Add SSE/HTTP transport + progress events; keep stdio for local |
| **No CI** | 🟠 | repo | Tests exist but no automated gate on push → regressions slip | GitHub Actions: pytest + `run_qa.py --quick` smoke |

---

## 🟡 Medium

| Issue | Sev | Location | Why it matters | Recommended future action |
|-------|-----|----------|----------------|---------------------------|
| **No pause/resume/cancel-per-URL** | 🟡 | `self._stop` Event | Only stop-all; cannot pause or retry individual failures | Job model with per-item states (queued/running/done/failed) + retry |
| **Inconsistent field coverage** | 🟢 Resolved | `ReelData` vs brief | **Resolved in Phase 1**: `ReelData`/parsers extended with all 9 missing fields (full_name, bio, is_verified, reels_count, thumbnail, music_id, reel_id, profile_url, scrape_ts); regression tests green. | None — keep coverage in sync with brief |
| **No deduplication** | 🟡 | engine | Re-scraping same reel duplicates rows | Dedup key = reel_id/username+reel_url in DB |
| **Thread-safety of shared results** | 🟡 | `scrape()` `with lock: results.append` | Append is guarded, but progress callbacks fire outside lock; acceptable today, fragile if logic grows | Move to thread-safe queue + service layer |
| **Settings not persisted** | 🟡 | `gui.py` | Workers/delay/headless reset each launch | Settings store (SQLite or JSON) |
| **Excel export depends on openpyxl** | 🟡 | `export_excel` | ImportError if missing; no graceful fallback | Bundle openpyxl; or lazy-import with clear error |
| **Brittle DOM fallback** | 🟡 | `_extract` DOM path | Markup changes break fallback; no versioned selectors | Centralize selectors; add fixture regression on each IG change |
| **No metrics/telemetry for health** | 🟡 | n/a | Can't tell if a block is global or per-account | Emit structured status events to logging/DB |

---

## 🟢 Low

| Issue | Sev | Location | Why it matters | Recommended future action |
|-------|-----|----------|----------------|---------------------------|
| `installer/install.bat` purpose unclear | 🟢 | installer | Dead/confusing artifact | Document or remove |
| `manifest.json` ignored by `*.json` | 🟢 | `.gitignore` | Unknown necessity | Confirm; either un-ignore or delete |
| No `LICENSE`/`CONTRIBUTING` in some views | 🟢 | repo | Open-source hygiene | Already added LICENSE; add CONTRIBUTING |
| Hardcoded viewport/UA | 🟢 | `scrape()` | Fine for now; may need per-account UA pool | Move to config |

---

## Risk register (summary)

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Instagram markup change breaks extraction | High | High | Parser fixture regression + monitor |
| Account blocked during heavy scrape | Med | High | SessionManager + rotation + adaptive backoff |
| EXE fails on clean Windows (missing browser) | High | Critical | Bundle Chromium + pre-flight check |
| Tk GUI cannot meet premium UX bar | High | High | Plan already replaces it (doc 09) |
| Logic-coupled GUI blocks backend reuse | Med | High | Extract service layer early (Phase 1–2) |
