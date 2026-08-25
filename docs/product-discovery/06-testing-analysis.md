# 06 — Testing & QA Analysis

---

## 6.1 Current test coverage (strengths)

The project already has a **solid, network-free unit layer** plus a **live QA harness**:

- `tests/test_parsers.py` — `parse_username`, `parse_music` (incl. original audio),
  `parse_counts`, `parse_caption/date/url`, `normalize_reel_url` against fixtures.
- `tests/test_session_and_export.py` — cookie import (Playwright + EditThisCookie),
  `has_session` expiry, CSV/JSON/Excel round-trips.
- `tests/test_adaptive_parsing.py`, `test_backoff.py`, `test_retry.py`,
  `test_caption_fallback.py`, `test_counts_parser.py`, `test_meta_parsers.py`,
  `test_music_parser.py`, `test_normalize_url.py`, `test_followers.py`,
  `test_corpus.py`, `test_extract_wiring.py`, `test_qa_metrics.py` — engine internal
  behaviors with no network.
- `tests/test_mcp_server.py` — registers tools, exercises the manager + lock.
- `tests/test_theme.py` — theme application.
- `tests/test_gui_columns.py` — **mocked** GUI column mapping only.
- `tests/fixtures/*.html` — reel_full, original_audio, stress_music, login_wall → gold
  parser inputs.
- `run_qa.py` — **integration** run over `tests/corpus.txt` with fill-rate gates
  (`ok_rate≥0.75`, `username≥0.80`, `music≥0.60`, no `session_expired`, `runtime≤1800s`);
  writes `results/qa/qa_report.json` + CSV; exits non-zero on failure.

> Coverage is genuinely good for **pure logic**. The architecture (queue, parsers,
> session, backoff) is well protected.

---

## 6.2 Untested / weak areas

| Area | Status | Risk |
|------|--------|------|
| **Concurrency / race conditions** | ❌ none | Shared `results` + callbacks could mask races; no stress test |
| **Real network flows** | 🟡 only via manual `run_qa.py` | Live IG changes caught late |
| **GUI behavior** | 🟡 mocked columns only | No click/flow tests; will be replaced anyway |
| **Installer / EXE on clean Windows** | ❌ none | "No deps" promise unverified |
| **MCP over real transport (SSE/HTTP)** | ❌ none | Future transport untested |
| **Session rotation / health** | ❌ none | Not built yet |
| **DB / job persistence** | ❌ none | Not built yet |
| **CI** | ❌ none | No automated gate |

---

## 6.3 Test reliability & external dependencies

- Unit tests are **deterministic** (fixtures, no network) → reliable in CI.
- `run_qa.py` depends on **live Instagram** + a valid session → flaky, slow, must stay
  out of the fast CI path; run as a scheduled/nightly job.
- `openpyxl` import in `export_excel` is a hidden dependency for Excel tests.

---

## 6.4 Future testing strategy

A layered pyramid. Lower layers run on every push; higher layers run nightly / on release.

```
Unit Tests                 (parsers, session, export, backoff, retry, qa metrics)
        ↓
Parser Tests              (fixtures: reel_full, original_audio, stress_music, login_wall)
        ↓
Service Tests             (ScraperService orchestration, no browser — mocked engine)
        ↓
Job System Tests          (create/pause/resume/cancel/retry, DB state)
        ↓
Session Tests             (import, expiry, health, rotation, refresh)
        ↓
Integration Tests         (real engine + bundled Chromium on staging account)
        ↓
End-to-End Tests          (run_qa.py gates over corpus — nightly, live)
        ↓
Desktop Application Tests (UI flows via Playwright/Electron test harness)
```

### Concrete next-test additions (before/with migration)
1. **Concurrency test** — run `scrape()` with 5 workers over 20 fake URLs using a
   mock browser; assert no lost rows, deterministic counts, clean stop.
2. **Service-layer tests** — wrap engine behind `ScraperService`; test pause/resume
   state machine without a browser.
3. **Job/DB tests** — SQLite repository: insert results, dedupe, query filters.
4. **MCP transport tests** — SSE/HTTP smoke once added.
5. **Installer smoke** — install EXE in a clean VM, assert launch + "browser missing"
   graceful message if Chromium not bundled.
6. **CI** — GitHub Actions: `pytest` (fast) on push; `run_qa.py --quick` nightly.
