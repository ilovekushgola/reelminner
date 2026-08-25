# 09 — Proposed Architecture

> Built from the **actual repository analysis**, not assumptions. It extends the
> existing plan `docs/superpowers/plans/2026-08-06-exe-frontend-mcp-skill.md`.
> Three stages: **Current → Migration → Final**. Do **not** implement yet.

---

## 9.1 Current Architecture (today)

```
[Tk GUI] [CLI] [MCP stdio] [Python API]
        │  │      │            │
        └──┴──────┴────────────┘
                     ▼
        Reelminner (scraper.py)   ← one class, all logic
                     │
        parsers.py (pure)  +  Playwright Chromium (N browsers)
                     │
        ReelData → CSV/JSON/Excel (in-memory, flat files)
        (no DB, no backend, no events, single session, print logging)
```

**Verdict:** the engine is strong; everything around it (state, UI, transport, logging)
is minimal or missing.

---

## 9.2 Migration Architecture (interim — de-risk before the big UI swap)

Goal: keep the Tk GUI working, but **extract a reusable service layer** and add
persistence + a local backend, so the future UI can be dropped in without touching the engine.

```
┌──────────────────────────────────────────────────────────────┐
│  Existing Tk GUI (unchanged)  │  New: tiny FastAPI/WebSocket  │
│  calls → ScraperService        │  backend (local, 127.0.0.1)   │
└───────────────┬────────────────┴───────────────┬──────────────┘
                │ (in-process or localhost)       │
                ▼                                  ▼
        ┌──────────────────────────────────────────────┐
        │  ScraperService (NEW, thin orchestration)      │
        │   • wraps Reelminner (KEEP)          │
        │   • JobManager (NEW) ─▶ SQLite (NEW)           │
        │   • SessionManager (NEW)                       │
        │   • LoggingService (NEW, structured)            │
        │   • MCPManager (wraps existing mcp_server)      │
        └──────────────────────────────────────────────┘
                │
                ▼
   Reelminner (KEEP) + parsers.py (KEEP) + Playwright
```

- **No UI rewrite yet.** Tk GUI is refactored only to call `ScraperService` instead of
  the engine directly.
- **SQLite** introduced for jobs/results/logs/sessions.
- **Structured logging** replaces `print`.
- **MCP** keeps its 5 tools but is served by `MCPManager` (still stdio; SSE optional).
- This stage is testable with the existing unit + QA suites plus new service/DB tests.

---

## 9.3 Final Architecture (target desktop app)

```
┌──────────────────────────────────────────────────────────────┐
│  Premium Frontend  (React + TypeScript + animation system)     │
│  • Dashboard · Workspace · Jobs · Data Explorer · Sessions     │
│  • MCP Manager · Logs · Settings  (multi-window / tabs)        │
│  Rendered in Electron (or WebView2) on Windows                 │
└───────────────────────────┬──────────────────────────────────┘
                            │  IPC (Electron) / WebSocket / REST
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  Local Backend  (Python + FastAPI + WebSocket/SSE)             │
│   ├─ ScraperService       (orchestrates engine)                │
│   ├─ JobManager           (persistent jobs, pause/resume)      │
│   ├─ SessionManager       (accounts, health, rotation)         │
│   ├─ MCPManager           (SSE/HTTP + stdio; live events)      │
│   ├─ LoggingService       (structured, file + query)           │
│   └─ SQLite               (jobs/results/logs/sessions)         │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  Reelminner Scraping Engine  (EXISTING — preserved)             │
│   Reelminner + parsers.py + Playwright/Chromium      │
└──────────────────────────────────────────────────────────────┘

Packaging:  Installer (Inno Setup) bundles
   • Packaged Python runtime
   • Playwright + Chromium
   • Pre-flight check → graceful "browser missing" if needed
   • Code-signed (SIGNING.md automated)
```

### Component responsibilities (final)

| Component | Based on | Action |
|-----------|----------|--------|
| Frontend | new | REPLACE Tk (`gui.py` → React/TS) |
| Desktop runtime | Electron/WebView2 | NEW |
| Backend | FastAPI + WebSocket | NEW (wraps engine) |
| Scraper engine | `scraper.py` | **KEEP** |
| Parsers | `parsers.py` | **KEEP** |
| Job manager | new | NEW (SQLite) |
| Database | SQLite | NEW |
| Session manager | extends session helpers | NEW (multi-account) |
| MCP manager | `mcp_server.py` | KEEP contract + add SSE/HTTP |
| Real-time events | WebSocket/SSE | NEW |
| Logging | `logging` module | REPLACE print callback |
| Testing | pytest + new layers | EXTEND (see 06) |
| Packaging | PyInstaller + Inno | KEEP + bundle runtime |

### Why this direction (justified by the repo)
- The engine + parsers are **proven and tested** → preserve them; the value is in the
  shell, not the core. Rewriting the engine would risk regressions for zero UX gain.
- The **queue + lock + stop** pattern already isolates concurrency → it maps cleanly
  onto a `ScraperService` that a backend can drive.
- Tk GUI is the **only** hard blocker for a premium UX → replace last, after the
  service layer exists, so the swap is a renderer change, not a rewrite.
- Adding a **backend + SQLite** early (migration stage) de-risks the final UI swap and
  immediately enables job history, logs, and settings the brief demands.

> Alternative considered: rewrite everything in Electron+Node. Rejected — it would
> discard the working Python engine and the test suite. The Python backend keeps the
> proven core while delivering the premium UI.
