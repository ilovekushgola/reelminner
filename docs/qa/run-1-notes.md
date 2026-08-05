# QA Run 1 — Baseline Data Collection (Task 8)

Versioned baseline notes (moved from `results/qa/run-1-notes.md` during Task 11 closure). No cookie/session contents included.

## 1. Command + runtime + timestamp

| Item | Value |
|---|---|
| Command | `python run_qa.py --workers 2 --delay 2.0` |
| Timestamp (report) | 2026-08-06T03:39:12 |
| runtime_s (report) | 235.6 |
| Wall runtime (measured) | 235.9 s |
| Exit code | 1 (gate failure — expected, report written) |
| Console log | `results/qa/run-1-console.txt` (47 lines, teed live) |
| Report file | `results/qa/qa_report.json` (exists) |
| CSV file | `results/qa/qa_results.csv` (exists) |

Pre-run session check: `has_session()` returned `session ok` (no cookie re-import needed).

## 2. Per-gate results

| # | Gate | Threshold | Actual | Result |
|---|---|---|---|---|
| 1 | engine completed (crash-free) | must complete | completed, 12/12 scraped | PASS |
| 2 | ok_rate | >= 0.75 | 1.0 (12/12) | PASS |
| 3 | username fill | >= 0.80 | 0.75 (9/12) | FAIL |
| 4 | music fill (licensed only) | >= 0.60 | 1.0 (12/12 licensed) | PASS |
| 5 | no session_expired | 0 | 0 | PASS |
| 6 | runtime | <= 1800 s | 235.6 s | PASS |

**Overall: GATES FAILED (1 of 6 failed) — engine healthy, one data-quality gate under threshold.**

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
| username | 0.75 |
| music_title | 1.0 |
| music_artist | 1.0 |
| likes | 1.0 |
| comments | 1.0 |
| caption | 1.0 |
| uploaded_at | 0.0 |

## 5. Root-cause analysis per failed gate

### Gate 3 FAIL — username fill 0.75 < 0.80

- **Observation:** 3 of 12 reels returned empty `username`:
  - `DbpvQ1fR_HA` (poster handle `realdefender.india` visible in caption)
  - `Dbps6koultg` (poster handle `rollsroyesofficial` visible in caption)
  - `Dbpt7UhzHIv` (poster handle `defendersofindia` visible in caption)
- **Root cause:** These are profile-less/"recommended" reel pages where the profile-header username element is absent from the DOM at scrape time; the primary username selector returns nothing and the existing DOM fallback also misses. The handle is nevertheless present in the caption string (available in all 3 rows), so the data is recoverable from the caption.
- **Not** a session/throttle problem: all 12 rows status `ok`, likes/comments/caption fully populated.
- **Maps to:** **Task 10 review (username fill < 0.80 → DOM fallback already exists).** Fix direction: strengthen username fallback chain — e.g. parse poster handle from caption (`"<handle> on <date>"` pattern already present in caption text) when the profile-header selector misses.

### Non-failed observations (no gate, informational)

- **uploaded_at fill = 0.0:** the `uploaded_at` column is empty for all 12 rows even though captions contain date strings (`"on August 5, 2026"`, `"on August 4, 2026"`). No gate covers this field in `run_qa.py`, so it did not affect the gate result, but it is a parsing gap worth flagging for a future Task 10-style review (date extraction from caption).
- **music parsing:** `music_title`/`music_artist` = 1.0 — the shared-audio corpus (all 12 reels use "Tough" by Krish Rao, audio 27298004019891395) exercises the licensed path cleanly; no Task 10 music edge case observed in this sample.

## 6. Failures list from qa_report.json

`"failures": []` — zero failure entries (no session_expired / timeout / unavailable rows). No retry/backoff (Task 9) and no session re-import needed based on this run.

## 7. Session / infra notes

- Session valid throughout the run; no login-wall re-encountered.
- 2 workers × 2.0 s delay completed 12 URLs in 235.6 s (~19.6 s/reel average across workers).
- No cookies, storage_state, or auth material captured in these notes (per constraints).
