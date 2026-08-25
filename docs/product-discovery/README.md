# Reelminner — Product Discovery (Master Index)

> **Goal of this folder:** create a precise map from the **current working Reelminner**
> to a **premium, self-contained Reelminner desktop application** — *without* changing
> the working project yet.
>
> These are **discovery & planning documents only**. No code was modified during
> Phase 0. The Tk GUI, scraper engine, and MCP server remain exactly as they were.

---

## 1. What does Reelminner currently do?
A Python/Tkinter **Instagram Reel & Profile scraping toolkit**. Its core engine
(`Reelminner`) extracts reel metadata (username, music, caption, likes,
comments, plays, upload date, video URL, original-audio flag) plus **follower count**,
and exports to CSV/JSON/Excel. It is exposed via **Desktop GUI, CLI, Python API, and an
MCP server (5 tools)**. See [`01-current-system.md`](01-current-system.md).

## 2. What is the current architecture?
Four thin front-ends → one engine → `parsers.py` (pure) + Playwright Chromium.
Concurrency = `queue.Queue` + N `threading.Thread` workers (each with its own browser),
guarded by a lock, stopped via an `Event`. No backend, no DB, no structured logging.
See [`02-file-analysis.md`](02-file-analysis.md) and [`09-proposed-architecture.md`](09-proposed-architecture.md).

## 3. What parts are strong and reusable?
- `parsers.py` (pure, tested) — **KEEP**.
- `ReelData` + CSV/JSON/Excel exporters — **KEEP** (extend).
- `scrape()` orchestration pattern, `save_cookies_from_file`, `backoff_delay`,
  `should_retry` — **KEEP WITH REFACTOR**.
- MCP tool contracts, `run_qa.py` gates, unit tests + fixtures, PyInstaller/Inno base.
See [`08-gap-analysis.md`](08-gap-analysis.md) → "Already Exists".

## 4. What are the biggest weaknesses?
🔴 No persistent storage/job history · 🔴 No auto-managed runtime for end users ·
🔴 No structured logging · 🟠 Business logic embedded in `gui.py` · 🟠 Single session,
no rotation · 🟠 Per-worker full browser · 🟠 MCP stdio-only · 🟠 No CI.
Full register in [`05-technical-debt.md`](05-technical-debt.md).

## 5. What capabilities are missing?
Persistent jobs, pause/resume, dedupe, Data Explorer (search/filter/sort), Dashboard,
Session health/rotation, MCP Manager UI + real-time events, structured logs, settings
persistence, backend/IPC layer, premium multi-window frontend, auto-bundled
Python+Chromium, code-signed installer, rich profile fields (full_name/bio/verified/
reels_count/thumbnail/music_id/reel_id/profile_url/scrape_ts). See
[`04-capability-matrix.md`](04-capability-matrix.md) and [`08-gap-analysis.md`](08-gap-analysis.md).

## 6. What exactly are we building in the future?
A premium, self-contained **Windows desktop application**: React/TS frontend → local
FastAPI backend (WebSocket/SSE) → `ScraperService` → **existing engine preserved** →
Playwright. With SQLite-backed jobs/history/logs, Session/MCP Managers, and an
installer that bundles Python + Chromium. Vision in [`07-product-vision.md`](07-product-vision.md);
architecture in [`09-proposed-architecture.md`](09-proposed-architecture.md).

## 7. What should happen first?
**Phase 1 — Core Engine Stabilization**: close the field-coverage gap and harden the
engine (low risk, high value), *before* any UI/backend work. Roadmap in
[`10-migration-roadmap.md`](10-migration-roadmap.md).

## 8. What should NOT be changed yet?
- Do **not** rewrite/replace the scraper engine (`scraper.py`).
- Do **not** replace the Tk GUI yet (Phase 7 only, after the service layer exists).
- Do **not** remove existing functionality.
- Do **not** make architectural changes on assumption — every claim here is sourced
  from the actual repository.

## 9. What is the recommended migration path?
Current → **Migration** (extract `ScraperService` + add SQLite/structured logging while
Tk GUI still works) → **Final** (React/TS + Electron + FastAPI backend + bundled
runtime). Phased over 11 phases (0–10). See [`09-proposed-architecture.md`](09-proposed-architecture.md)
and [`10-migration-roadmap.md`](10-migration-roadmap.md).

---

## Document index

| # | Document | Purpose |
|---|----------|---------|
| 01 | [Current System](01-current-system.md) | How Reelminner works today + architecture map |
| 02 | [File Analysis](02-file-analysis.md) | Per-file/component classification (KEEP/REFACTOR/REPLACE…) |
| 03 | [Feature Inventory](03-feature-inventory.md) | Every feature: where, maturity, exposure, future |
| 04 | [Capability Matrix](04-capability-matrix.md) | Current vs desired, by capability |
| 05 | [Technical Debt](05-technical-debt.md) | Risks ranked Critical→Low + actions |
| 06 | [Testing Analysis](06-testing-analysis.md) | Coverage gaps + future test pyramid |
| 07 | [Product Vision](07-product-vision.md) | Target users, screens, UX principles |
| 08 | [Gap Analysis](08-gap-analysis.md) | Reuse / Improve / Missing |
| 09 | [Proposed Architecture](09-proposed-architecture.md) | Current → Migration → Final |
| 10 | [Migration Roadmap](10-migration-roadmap.md) | 11 phased plan with criteria/risks |

---

## ⚠️ Notable finding
The original product brief listed capabilities the **current code does not implement**
(full_name, bio, verification, reels count, thumbnail, music ID, reel ID, profile URL,
scrape timestamp). Today `ReelData` has exactly 14 fields (see `01-current-system.md`
§1.12). This gap is the top input to Phase 1.
