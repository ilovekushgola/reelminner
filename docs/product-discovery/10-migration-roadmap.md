# 10 — Migration Roadmap

> Phased plan derived from the repository analysis (docs 01–09). **Do not start
> Phase 1 until the discovery documents are approved.** Each phase lists goal,
> files affected, new components, dependencies, testing, completion criteria, and risks.

---

## Phase 0 — Repository Discovery ✅ (this task)
- **Goal:** understand the repo, document current state, gaps, debt, and target.
- **Files:** `docs/product-discovery/*` (created).
- **New components:** none (documentation only).
- **Testing:** N/A.
- **Completion:** all 11 discovery docs + terminal report delivered.
- **Risks:** none (read-only).

---

## Phase 1 — Core Engine Stabilization (low risk, high value)
- **Goal:** harden the engine without changing behavior; fix the field-coverage gap.
- **Files affected:** `scraper.py`, `parsers.py`, `tests/*`.
- **New components:** extended `ReelData` fields (full_name, bio, verified, reels_count,
  thumbnail, music_id, reel_id, profile_url, scrape_ts); parser additions.
- **Dependencies:** none new.
- **Testing:** extend parser + engine unit tests; add fixtures.
- **Completion:** all brief-claimed fields extracted & tested; no regression in `run_qa.py`.
- **Risks:** Instagram markup changes → mitigated by fixture regression.

---

## Phase 2 — Backend Service Architecture (de-coupling)
- **Goal:** extract `ScraperService` so UI/CLI/MCP all call it; remove logic from `gui.py`.
- **Files affected:** `scraper.py` (wrap), `gui.py` (refactor to call service), new `service.py`.
- **New components:** `ScraperService` (orchestration wrapper), clear interfaces.
- **Dependencies:** none (in-process).
- **Testing:** service-layer unit tests (mock engine); keep Tk GUI working.
- **Completion:** Tk GUI still works but via `ScraperService`; engine untouched.
- **Risks:** behavior drift → covered by existing QA gates.

---

## Phase 3 — Job System & Persistence (SQLite)
- **Goal:** persistent jobs, history, pause/resume/cancel, retry-failed, dedupe.
- **Files affected:** new `db.py`, `jobs.py`; `service.py`.
- **New components:** SQLite schema (jobs/results/logs/sessions), `JobManager`,
  repository layer, job state machine.
- **Dependencies:** `sqlite3` (stdlib).
- **Testing:** DB + job-state unit tests; concurrency test (5 workers, no lost rows).
- **Completion:** jobs survive restart; pause/resume/cancel work; dedup verified.
- **Risks:** concurrency races → stress test before merge.

---

## Phase 4 — Testing & QA Hardening
- **Goal:** CI + nightly + coverage of new layers.
- **Files affected:** `.github/workflows/*`, `pytest.ini`, new tests.
- **New components:** GitHub Actions (pytest on push; `run_qa.py --quick` nightly).
- **Dependencies:** CI provider.
- **Testing:** the suite itself.
- **Completion:** green CI on push; nightly live QA report.
- **Risks:** live QA flakiness → isolate from fast path.

---

## Phase 5 — API / IPC Layer
- **Goal:** local backend (FastAPI) + WebSocket/SSE for real-time progress/logs.
- **Files affected:** new `backend/`, `service.py` (expose over API).
- **New components:** FastAPI app, WebSocket hub, event bus.
- **Dependencies:** `fastapi`, `uvicorn`, `websockets`.
- **Testing:** API contract tests; event-delivery tests.
- **Completion:** backend serves scrape + streams progress to a test client.
- **Risks:** port conflicts → bind 127.0.0.1, configurable port.

---

## Phase 6 — UI/UX Specification
- **Goal:** design system + screen specs for the premium frontend.
- **Files affected:** `docs/design/*` (new), no code yet.
- **New components:** component library spec, theme tokens, interaction specs.
- **Dependencies:** design tooling (Figma/MD).
- **Testing:** design review.
- **Completion:** signed-off specs for all 8 screens.
- **Risks:** scope creep → freeze scope to vision doc.

---

## Phase 7 — Premium Frontend (replace Tk)
- **Goal:** React/TS + animation desktop UI talking to the backend.
- **Files affected:** new `frontend/`, `gui.py` → DEPRECATE, `theme.py` → DEPRECATE.
- **New components:** Dashboard, Workspace, Jobs, Data Explorer, Session Manager,
  MCP Manager, Logs, Settings (multi-window/tabs).
- **Dependencies:** Node, React, TS, Electron/WebView2, animation lib.
- **Testing:** frontend component + E2E (Playwright for UI).
- **Completion:** all 8 screens functional against backend; Tk removed.
- **Risks:** large effort → phase behind backend; keep Tk until parity reached.

---

## Phase 8 — Desktop Integration
- **Goal:** bundle Python runtime + Playwright Chromium; pre-flight checks.
- **Files affected:** `build_exe.py`, `installer/*.iss`, `backend/` packaging.
- **New components:** runtime bundling, browser download/bundle step, launch check.
- **Dependencies:** PyInstaller, Inno Setup, Chromium download.
- **Testing:** clean-VM installer smoke test.
- **Completion:** install on clean Windows → launches with no manual deps.
- **Risks:** bundle size / AV false-positives → code signing + EV cert.

---

## Phase 9 — Packaging & Installer
- **Goal:** professional, code-signed installer + auto-update readiness.
- **Files affected:** `installer/Reelminner.iss`, `SIGNING.md` (automate).
- **New components:** signing pipeline, versioned installer.
- **Dependencies:** code-sign cert, CI secrets.
- **Testing:** signed-install smoke; upgrade path test.
- **Completion:** signed EXE + Setup ship from CI.
- **Risks:** cert cost/provisioning → plan early.

---

## Phase 10 — GitHub Release
- **Goal:** public, documented release of the desktop app.
- **Files affected:** `README.md` (update with screenshots), `docs/`, releases.
- **New components:** release notes, install guide.
- **Dependencies:** Phase 9 artifacts.
- **Testing:** final QA + manual UAT.
- **Completion:** tagged release + installer download.
- **Risks:** legal/ToS → include prominent disclaimer (already in README).

---

## Sequencing rationale
Phases 1–4 build the **durable core** (engine + service + DB + CI) while the Tk GUI
keeps working — lowest risk, highest learning. Phases 5–7 add the **backend + premium
UI** only after the core is stable, so the UI swap is a renderer change, not a rewrite.
Phases 8–10 turn it into a **shippable product**. This matches the "preserve working
functionality" mandate and the existing `exe-frontend-mcp-skill` plan.
