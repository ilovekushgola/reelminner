# 04 — Capability Matrix

> Comparison of **current Reelminner** vs the **desired premium desktop application**.
> Legend: ✅ = present/working · 🟡 = partial · ❌ = absent.

| Capability | Exists | Working | Tested | GUI | CLI | MCP | Future Desktop |
|------------|:------:|:-------:|:------:|:---:|:---:|:---:|:--------------:|
| Reel URL normalization | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Reel metadata extraction (caption, music, likes, comments, plays, date, video) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Original-audio detection | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Follower count extraction | ✅ | ✅ | 🟡 | ✅ | ✅ | ✅ | ✅ |
| Full name / bio / verified / reels count / Profile URL / reel ID / thumbnail / music ID / scrape_ts | ✅ | ✅ | 🟡 | ✅ (export) | ✅ (export) | ✅ (export) | ✅ |
| Profile URL / reel ID / thumbnail / music ID | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Session validity check | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Cookie import (2 formats) | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ |
| Interactive login (QR) | ✅ | ✅ | 🟡 | ✅ | ✅ | ❌ | ✅ |
| Clear session | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Session health / refresh / rotation | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Concurrent scraping (workers) | ✅ | ✅ | 🟡 | ✅ | ✅ | ✅ | ✅ |
| Stop / cancel | ✅ | ✅ | 🟡 | ✅ | ✅ | ✅ | ✅ |
| Pause / resume | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Delay + jitter | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Adaptive backoff | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Blocked / rate-limit status | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| CSV export | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| JSON export | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Excel export | ✅ | 🟡 | 🟡 | ✅ | ✅ | ✅ | ✅ |
| Filtered export | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Deduplication | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Search / filter / sort | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Persistent job history | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Real-time progress events | 🟡 | 🟡 | 🟡 | ✅(poll) | ❌ | ❌ | ✅ |
| MCP server (5 tools) | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ |
| MCP real-time / SSE / HTTP | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| MCP manager UI | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Structured logging | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Log search / filter / export | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Settings persistence | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Dashboard / analytics | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Multi-window / rich screens | ❌ | ❌ | ❌ | 🟡(1 win) | ❌ | ❌ | ✅ |
| Premium dark UI / animations | ❌ | ❌ | ❌ | 🟡(basic) | ❌ | ❌ | ✅ |
| One-click installer (auto deps) | 🟡 | 🟡 | ❌ | ❌ | ❌ | ❌ | ✅ |
| Auto-bundled Python + Chromium | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Code signing | 🟡 | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Structured logging (engine) | ✅ | ✅ | 🟡 | ❌ (no Logs screen) | ✅ (CLI) | ❌ | ✅ |
| Typed events / EventSink | ✅ | ✅ | 🟡 | ❌ | ❌ | ✅ (plumbed) | ✅ |
| Clean service boundary (`ScraperService`) | ✅ | ✅ | 🟡 | ✅ | ✅ | ✅ | ✅ |
| Derived media fields (reel_id / music_id / thumbnail / scrape_ts) | ✅ | ✅ | 🟡 | ✅ (export) | ✅ (export) | ✅ (export) | ✅ |

### Key takeaways
- **Strong today:** extraction engine, parsers, session import, concurrency, backoff, 3 export formats, MCP tool contract, unit tests, QA gates.
- **Claimed but absent (now implemented in Phase 1):** rich profile fields (full_name, bio, verified, reels_count, thumbnail, music_id, reel_id, profile_url, scrape_ts) — now extracted; structured logging + typed events + `ScraperService` boundary also added. **Still missing:** dedupe, search/filter, job history, dashboard, MCP manager UI, settings persistence, auto-bundled runtime.
- **Partially there:** Excel export (needs openpyxl), real-time progress (poll-based), installer (manual deps), code signing (docs only).
