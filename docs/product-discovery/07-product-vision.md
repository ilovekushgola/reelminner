# 07 — Product Vision

> A detailed vision of the **future Reelminner desktop application** — a premium,
> self-contained Windows desktop product comparable to modern SaaS desktop software.
> This is the target state; the migration path is in `10-migration-roadmap.md`.

---

## 7.1 Target users

1. **Growth & marketing analysts** — track competitor/reel performance, music trends.
2. **Content creators / agencies** — bulk-collect reels + metadata for research.
3. **Researchers / data journalists** — reproducible dataset collection.
4. **AI-agent builders** — drive scraping via MCP from their own tools.
5. **Non-technical operators** — want a double-click EXE, no Python/terminal.

## 7.2 Primary workflows

1. Install via one-click installer → launch Reelminner.
2. Log in to Instagram **or** import cookies (Session Manager).
3. Paste/import reel URLs → configure job (workers, delay, enrichment, headless).
4. Start job → watch **live progress** (current URL, success/failed/blocked counters).
5. Pause / resume / cancel / retry-failed.
6. Explore results in **Data Explorer** (search/filter/sort/dedup/export subset).
7. Review **Logs** (app, scraping, errors) with search/filter/export.
8. Configure **MCP** (start/stop server, copy client config, see connected clients).
9. Tune **Settings** (defaults, browser, storage, export).
10. Open dashboard for totals, success rate, recent activity.

## 7.3 Screens (multi-window where useful)

| Screen | Purpose | Key elements |
|--------|---------|--------------|
| **Dashboard** | At-a-glance health | Total jobs, reels scraped, success rate, active jobs, recent activity, usage analytics |
| **Scraper Workspace** | Run a scrape | URL paste/import, job settings, worker/delay/enrichment/headless, live progress, counters, stop/pause |
| **Job Management** | History & control | Persistent job list, queue, history, pause/resume/cancel, retry failed, job details, error history |
| **Data Explorer** | Browse results | Search, filter, sort, column management, saved filters, bulk select, copy, open IG, export filtered, dedup |
| **Session Manager** | Accounts | Active session status, login, cookie import, health, refresh, (future) multiple sessions / rotation |
| **MCP Manager** | AI integration | Start/stop server, status, URL, connected clients, available tools, config generator, copy config |
| **Logs** | Observability | App/scrape/error logs, search, filter, export |
| **Settings** | Configuration | Scraping defaults, browser config, storage, export, advanced |

Multi-window: Dashboard + Workspace can be separate windows; Job details, Data Explorer,
MCP Manager, Logs, Settings open as secondary windows/tabs.

## 7.4 Major features (future)

- Persistent jobs & history (SQLite).
- Real-time progress (WebSocket/SSE from backend → UI).
- Rich profile enrichment (full_name, bio, verified, reels_count, thumbnail, music_id, reel_id).
- Deduplication & saved filters.
- MCP manager UI + SSE/HTTP transport + live events.
- Structured logging + log viewer.
- Settings persistence.
- Auto-bundled Python + Playwright Chromium; code-signed installer.

## 7.5 Data flow

```
UI (React/TS)  ──IPC/WebSocket──▶  Local Backend (FastAPI + ScraperService)
                                        │
                                        ├─ JobManager  ─▶ SQLite
                                        ├─ SessionManager ─▶ storage_state(s)
                                        ├─ MCPManager  ─▶ exposes tools
                                        └─ ScraperEngine (existing) ─▶ Playwright/Chromium
                                        ▲
                              events (progress/status/log) ──WebSocket──▶ UI
```

## 7.6 User-experience principles

- **Premium, not utilitarian:** rich dark UI, smooth transitions, no terminal feel.
- **Always observable:** live progress, never a frozen "working…".
- **Forgiving:** pause/resume, retry-failed, clear error history.
- **Safe by default:** conservative rate limits; prominent ToS/ethical notice.
- **Zero-config install:** one installer, no manual Python/Playwright steps.
- **Reuse, don't rewrite:** the proven extraction engine stays; only the shell changes.
