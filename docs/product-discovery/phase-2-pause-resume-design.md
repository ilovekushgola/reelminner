# Phase 2 — Pause / Resume Design

**Status:** Investigation complete before implementation.
**Question:** Can Reelminner do *real* pause/resume, or only cooperative pause?

---

## 1. Current architecture (as built in Phase 1)

```
Reelminner.scrape(urls, …)
  • builds a queue.Queue of targets
  • spawns N threading.Thread workers (each opens its own browser)
  • each worker runs _worker():
        while not self._stop.is_set():
            try: item = self._q.get(timeout=1)
            except Empty: break
            _phase_one(...) ; _scrape_profile(...) ; _extract(...)
            self._q.task_done()
  • stop() sets self._stop  (cooperative "soft stop")
```

Key facts:

- Workers loop until `_stop` is set **or** the queue is empty.
- `stop()` does **not** kill threads; it politely asks them to finish the
  current item and exit. This is already a *cooperative* stop.
- Browsers are owned per-worker; there is no global "pause the page" hook.

---

## 2. Can we do "true" pause?

**No — not safely.** Python's `threading` has no `Thread.suspend()` /
`Thread.resume()`, and even if it did, suspending a thread that holds a
Playwright browser/CDP connection mid-navigation would corrupt that connection
and leak resources. There is no OS- or library-supported safe suspension of a
running scrape.

So the only safe pause is **cooperative**:

1. Let the current item finish.
2. Prevent workers from pulling new items.
3. Persist the remaining queue.
4. Resume later from the remainder.

This is exactly what the existing `stop()` + queue-empty exit already gives us
for step 1–2. We extend it with persistence (3) and a restart-from-remainder
(4).

---

## 3. Chosen design: cooperative pause with persisted remainder

```
pause_job(job_id)
   ├─ set runtime.pause_requested = True
   └─ scraper.stop()                 # soft stop: finish current item, no new items

  (workers drain current items, scrape() returns)

_run() after scrape returns:
   ├─ if stop_requested  → STOPPED
   ├─ elif pause_requested:
   │     pending = submitted_urls - completed_urls
   │     persist pending into config.pending_urls
   │     status → PAUSED
   └─ else → COMPLETED

resume_job(job_id)   [only from PAUSED]
   ├─ urls = config.pending_urls
   ├─ status → STARTING → RUNNING
   ├─ NEW ScraperService (fresh browsers)
   └─ scrape(pending_urls)  → rows appended to same result file
```

### Why resume needs a *new* ScrapeService

The paused run's browsers were closed by the soft stop. Resume therefore starts
a fresh engine and submits **only the unprocessed URLs**. This is genuine resume,
not a fake "pause":

- Nothing is pretended to be suspended.
- Only reels not yet scraped are re-run.
- Previously scraped rows are already on disk (JSONL) and are not duplicated.

### Persistence of the queue

`pending_urls` lives in SQLite (`config_json`), so resume works **across process
restarts** too — not just within a single session.

---

## 4. Stop vs Pause (intentional distinction)

| Action | Engine | Status | Remainder kept? | Auto-resume? |
|--------|--------|--------|-----------------|--------------|
| `stop_job` | `stop()` (soft) | `STOPPED` (terminal) | yes (for retry) | no |
| `pause_job` | `stop()` (soft) | `PAUSED` | yes | yes (explicit `resume_job`) |

Both use the same safe soft-stop mechanism; the difference is the *intent flag*
the `JobManager` inspects when `scrape()` returns.

---

## 5. Edge cases / honesty notes

- **In-flight item completes.** A pause does not abort the reel currently being
  scraped. This is by design (cooperative). Documented as a known limitation.
- **No per-item checkpointing.** We persist at the URL granularity, not
  mid-reel. A crash during an item loses that one item (re-scraped on retry).
- **We never claim a frozen thread.** The status flips to `PAUSED` only after
  the engine has actually stopped.
- **Crash while RUNNING** → on restart the job is marked `INTERRUPTED` (per the
  recovery contract). It is *not* silently resumed; the user must retry/resume.

---

## 6. Test strategy

`tests/test_job_manager.py` uses an injected `FakeScraperService` (no real
browser) that:

- iterates the submitted URLs with a tiny delay,
- honors a `stop()` event (breaks the loop early — mimicking cooperative stop),
- invokes `row_cb`/`progress_cb` for each item.

This lets us assert:

- pause mid-run → some rows done, `pending_urls` == remainder, status `PAUSED`.
- resume → only remainder scraped, results merged, status `COMPLETED`.
- stop → status `STOPPED`, remainder retained.
- crash simulation (process restart) → non-terminal job becomes `INTERRUPTED`.
