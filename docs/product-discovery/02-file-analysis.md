# 02 — File-by-File Analysis

> Classification legend:
> **KEEP** · **KEEP WITH REFACTOR** · **REPLACE** · **DEPRECATE** · **INVESTIGATE**
> "Reusable" = can be carried into the future desktop app with little/no change.

---

## 2.1 Core engine & front-ends

| File | Purpose | Important components | Deps | Reusable | Refactor | Notes |
|------|---------|----------------------|------|----------|----------|-------|
| `scraper.py` | Core engine + CLI | `Reelminner`, `scrape()`, `_scrape_one`/`_attempt_one`, `_extract`, `_scrape_profile`, session helpers, `backoff_delay`, `should_retry`, `ReelData`, `write_csv`/`export_json`/`export_excel`, `DEFAULT_STATE_FILE` | playwright, bs4?, json, queue, threading | ✅ High | KEEP WITH REFACTOR | The crown jewel. Business logic is mixed into one class; no DI, no persistence hook. Split into services in future. |
| `parsers.py` | Pure HTML/URL extraction | `normalize_reel_url`, `parse_username_*`, `parse_music_*`, `parse_counts_*`, `parse_caption/date/url`, `_extract_json_object` | re, json, html | ✅✅ Very high | KEEP | No browser dependency → trivially reusable & testable. No changes needed. |
| `gui.py` | Tkinter desktop app | `ReelScraperApp(tk.Tk)`, `COLUMN_ORDER`, `_run_scrape`, `_poll`, `_q` queue, `_log_from_thread`, export/copy/open handlers | tkinter, scraper, parsers | ⚠️ Partial | REPLACE (future) | Entire app logic lives in one `tk.Tk` subclass → tight coupling. Queue-marshaling pattern is good and worth reusing as a pattern. Will be replaced by premium frontend per product direction. |
| `theme.py` | GUI dark styling | `apply_dark_theme(root)`, color constants | tkinter.ttk | ⚠️ | DEPRECATE (future) | Tk-specific; dies with the Tk GUI. |
| `mcp_server.py` | MCP server (5 tools) | `FastMCP`, `ScraperManager`, `_scrape_lock`, tools `scrape_reels`/`get_status`/`import_cookies`/`stop_scrape`/`export_results` | mcp, scraper | ✅ High | KEEP WITH REFACTOR | stdio only; no real-time events; single in-memory lock. Keep the tool contract, wrap with a service layer later. |
| `build_exe.py` | PyInstaller build | `EXE`, `COLLECT`/`Analysis` | pyinstaller | ✅ | KEEP | One-file build. Will be superseded by installer+runtime bundling strategy. |
| `Reelminner.spec` | PyInstaller spec | one-file config | pyinstaller | ✅ | KEEP | Matches `build_exe.py`. |

---

## 2.2 QA, config, packaging

| File | Purpose | Components | Reusable | Refactor | Notes |
|------|---------|-----------|----------|----------|-------|
| `run_qa.py` | E2E QA harness | `compute_metrics`, `evaluate_gates`, `GATES`, `main` | ✅ High | KEEP | Excellent gate design; reuse as the QA core in CI. |
| `pytest.ini` | pytest config | `testpaths=tests` | ✅ | KEEP | — |
| `requirements.txt` | Runtime deps | requests, beautifulsoup4, lxml, playwright, mcp[cli], openpyxl | ✅ | KEEP | Excel needs openpyxl. |
| `requirements-dev.txt` | Dev deps | pytest, (coverage) | ✅ | KEEP | thin |
| `tests/conftest.py` | import shim | adds project root to `sys.path` | ✅ | KEEP | — |
| `tests/corpus.txt` | fixed URL corpus | 12 reel URLs | ✅ | KEEP | live-run fixture |
| `tests/fixtures/*.html` | parser fixtures | reel_full, original_audio, stress_music, login_wall | ✅✅ | KEEP | gold for parser tests |
| `installer/Reelminner.iss` | Inno Setup installer | AppId, Source `dist/*.exe`, signing hook | ✅ | KEEP WITH REFACTOR | Good base; needs runtime/browser bundling + code-signing step. |
| `installer/install.bat` | helper | — | ⚠️ | INVESTIGATE | purpose/usage unclear; document or remove. |
| `installer/SIGNING.md` | signing guide | — | ✅ | KEEP | valuable for "professional installer" goal. |
| `installer/assets/` | installer art | — | ✅ | KEEP | — |
| `assets/make_icon.py` | icon generator | Pillow script | ✅ | KEEP | — |
| `assets/icon.ico` | app icon | — | ✅ | KEEP | referenced by README + EXE. |
| `.mcp.json` | MCP client config | `python mcp_server.py`, `cwd:"."` | ✅ | KEEP | path fixed to relative in this repo prep. |
| `mcp.env.example` | MCP env template | `IRS_*` | ✅ | KEEP | — |
| `manifest.json` | build manifest | — | ⚠️ | INVESTIGATE | confirm needed; currently git-ignored by `*.json`. |
| `.gitignore` | ignore rules | ignores storage_state, results, dist, `*.json` (with `!.mcp.json`) | ✅ | KEEP | secrets stay local ✅ |

---

## 2.3 Docs & skill

| File | Purpose | Reusable | Refactor | Notes |
|------|---------|----------|----------|-------|
| `README.md` | project readme (rewritten) | ✅ | KEEP | good; will need screenshot/branding later. |
| `docs/SKILL.md` | agent skill doc | ✅ | KEEP | — |
| `docs/E2E_TEST_FIX_LOOP_PLAN.md` | e2e test/fix loop plan | ✅ | KEEP | already executed; keep as history. |
| `docs/superpowers/plans/2026-08-06-exe-frontend-mcp-skill.md` | **future architecture plan** | ✅✅ | KEEP | contains tech-stack proposal + risk register; the proposed-architecture doc (`09`) builds on it. |
| `docs/superpowers/plans/2026-08-06-e2e-test-fix-improve-loop.md` | e2e loop plan (executed) | ✅ | KEEP | — |
| `docs/qa/run-1-notes.md`, `run-2-notes.md` | QA baselines | ✅ | KEEP | local data evidence. |
| `skills/reelminner/` | agent skill def | ✅ | KEEP | — |

---

## 2.4 Component-level classification summary

| Component | Verdict | Why |
|-----------|---------|-----|
| `parsers.py` (all) | **KEEP** | Pure, tested, no deps. Drop-in reusable. |
| `ReelData` + export helpers | **KEEP** | Solid data contract; extend (don't break) with new fields later. |
| `Reelminner.scrape` orchestration | **KEEP WITH REFACTOR** | Works; extract session/job/browser as services. |
| `save_cookies_from_file` | **KEEP** | Robust dual-format import. |
| `backoff_delay` / `should_retry` | **KEEP** | Clean, unit-tested. |
| `mcp_server.py` tool contracts | **KEEP WITH REFACTOR** | Keep 5 tools; add SSE/HTTP + events later. |
| `run_qa.py` gates | **KEEP** | Reuse in CI. |
| `gui.py` whole class | **REPLACE** (future) | Will be swapped for premium frontend; queue pattern is the reusable idea. |
| `theme.py` | **DEPRECATE** (future) | Tk-only. |
| `installer/install.bat`, `manifest.json` | **INVESTIGATE** | Confirm purpose before next phase. |
