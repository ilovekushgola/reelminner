# QA Run 2 — Loop Closure Verification (Task 11)

Final live QA re-run on branch `e2e-qa-loop` after Tasks 9 / 10 / 10b fixes.
Versioned alongside the run-1 baseline (`docs/qa/run-1-notes.md`). No cookie/session contents included.

## 1. Command + runtime + timestamp

| Item | Value |
|---|---|
| Command | `python scraper.py --import-cookies cookies_export.json` (fresh session), then `python run_qa.py --workers 2 --delay 2.0` |
| Cookie import | `[OK] Cookies imported` (fresh session, new `storage_state.json`) |
| Timestamp (report) | 2026-08-06T03:55:23 |
| runtime_s (report) | 237.1 |
| Exit code | 0 (all gates pass) |
| Report file | `results/qa/qa_report.json` (exists) |
| CSV file | `results/qa/qa_results.csv` (exists) |

## 2. Per-gate results

| # | Gate | Threshold | Actual | Result |
|---|---|---|---|---|
| 1 | engine completed (crash-free) | must complete | completed, 12/12 scraped | PASS |
| 2 | ok_rate | >= 0.75 | 1.0 (12/12) | PASS |
| 3 | username fill | >= 0.80 | 1.0 (12/12) | PASS |
| 4 | music fill (licensed only) | >= 0.60 | 1.0 (12/12 licensed) | PASS |
| 5 | no session_expired | 0 | 0 | PASS |
| 6 | runtime | <= 1800 s | 237.1 s | PASS |

**Overall: ALL GATES PASS — loop closed, run exits 0.**

## 3. status_counts

```json
{"ok": 12}
```

- ok: 12
- session_expired: 0
- timeout: 0
- unavailable: 0
- original_audio rows: 0 (all 12 reels licensed)

## 4. Field fill rates (ok rows; music = licensed only)

| Field | Fill rate |
|---|---|
| username | 1.0 |
| music_title | 1.0 |
| music_artist | 1.0 |
| likes | 1.0 |
| comments | 1.0 |
| caption | 1.0 |
| uploaded_at | 1.0 |

## 5. Before / after — run-1 (baseline) vs run-2 (post-fix)

| Metric | Run-1 (baseline, pre-fix) | Run-2 (post-fix) | Delta | Moved by |
|---|---|---|---|---|
| ok_rate | 1.0 (12/12) | 1.0 (12/12) | 0 | — (held; protected by Task 9 backoff + Task 10 retry) |
| username fill | 0.75 (9/12) | 1.0 (12/12) | +0.25 | **Task 10b** `9e37f50` caption-based username fallback (poster handle parsed from `"<handle> on <date>"` caption pattern when profile-header element is absent) |
| music fill (licensed) | 1.0 (12/12) | 1.0 (12/12) | 0 | — (held; licensed shared-audio corpus) |
| uploaded_at fill | 0.0 (0/12) | 1.0 (12/12) | +1.0 | **Task 10b** `9e37f50` upload-date fallback from caption date string |
| failures by status | `{"ok": 12}` — 0 failures | `{"ok": 12}` — 0 failures | 0 | — (Task 9 backoff `55a0f0c` + Task 10 retry `262d8b3` keep transient timeout/error reels from entering failures; none occurred in either run) |
| session_expired | 0 | 0 | 0 | — |
| runtime_s | 235.6 | 237.1 | +1.5 | — (noise; same 2 workers × 2.0 s delay, ~19.8 s/reel) |

### Fix attribution (commits on `e2e-qa-loop`)

- **Task 9** `55a0f0c` — exponential backoff between reels after consecutive failures: makes ok_rate/no-failures robust against throttling; no failure cascade observed in either run.
- **Task 10** `262d8b3` — single auto-retry for transient timeout/error reels: retries transient failures before they land in `failures`/gate metrics; no retry path triggered in run-2 (all `ok` first pass).
- **Task 10b** `9e37f50` — caption-based username + upload-date fallbacks for profile-less reels: the metric mover. The 3 run-1 misses (`DbpvQ1fR_HA` → `realdefender.india`, `Dbps6koultg` → `rollsroyesofficial`, `Dbpt7UhzHIv` → `defendersofindia`) all now resolve via caption handle parsing; same pattern lifts `uploaded_at` 0.0 → 1.0.

## 6. Failures list from qa_report.json

`"failures": []` — zero failure entries. No session_expired / timeout / unavailable rows in either run.

## 7. Session / infra notes

- Fresh session re-imported immediately before the run (`[OK] Cookies imported`); session valid throughout — no login wall re-encountered.
- 2 workers × 2.0 s delay completed 12 URLs in 237.1 s (~19.8 s/reel average across workers).
- No cookies, storage_state, or auth material captured in these notes (per constraints).
