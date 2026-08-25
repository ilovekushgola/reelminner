# Phase 3.6 — Test Report

> Final verification for the Performance Intelligence & Compute Monitoring system.

## 1. Test count (before → after)

| Suite | Before (end of Phase 3.5) | After (Phase 3.6) |
|---|---|---|
| `tests/` total | **204 passed, 18 subtests passed** | **225 passed, 18 subtests passed** |
| New Phase 3.6 tests | — | **+21** (`tests/test_performance.py`) |
| Regression | green | green (exit 0) |

Run: `python -m pytest tests/` → `225 passed, 18 subtests passed in ~25s`.

## 2. What the new tests cover

`tests/test_performance.py` (21 tests) maps to the Definition of Done:

| Area | Tests |
|---|---|
| Capability detection (no PII) | `test_capabilities_detected_without_pii` |
| Store round-trip + survive restart | `test_store_summary_roundtrip`, `test_store_config_outcome_and_history_survives_reload` |
| Sample cap (efficient writes) | `test_store_samples_capped` |
| Worker comparison | `test_analyzer_compare_workers` |
| Diminishing returns (Observed/Estimated) | `test_analyzer_diminishing_returns_observed`, `..._insufficient_with_one_level` |
| Conservative bottleneck labels | `test_detect_bottleneck_network_likely` (LIKELY), `..._memory_possible` (POSSIBLE), `..._unknown_when_clean` (UNKNOWN) |
| Recommendation engine | `test_recommendation_insufficient_data`, `test_recommendation_does_not_claim_causation` |
| Settings validation | `test_settings_performance_section_defaults`, `test_settings_performance_validation_rejects_out_of_range` |
| Facade via `ReelminnerApplication` | `test_app_performance_capabilities_and_monitoring`, `test_app_worker_recommendation_insufficient_without_jobs`, `test_app_performance_history_empty`, `test_app_records_job_performance_on_end` |
| No sensitive-data leak | `test_app_records_job_performance_on_end`, `test_app_no_sensitive_data_in_samples` |
| MCP tool surface | `test_mcp_performance_tools_registered`, `test_mcp_performance_tools_smoke` |

Additional checks satisfied by existing tests:
- `test_mcp_server.EXPECTED_TOOLS` now lists all 44 tools (incl. 6 new).
- `test_skill_matches_mcp` (both repo + mirror SKILL.md) still passes because the
  6 tools are documented as `**name**` entries; the mirror copy is synced.

## 3. Regression result

- **Full suite green, zero failures, zero errors, exit code 0.**
- No existing test was modified except `tests/test_mcp_server.py`
  (`EXPECTED_TOOLS` extended by 6 names) to track the new surface.
- No behavior change to any pre-3.6 tool or module.

## 4. Known limitations (honest)

- **Bottleneck CPU/MEMORY confidence is `POSSIBLE`, not `LIKELY`** unless memory
  pressure ≥ 90% — by design (conservative; correlation ≠ causation).
- **Per-job `urls_per_min_current` reports the running average** rather than a
  per-tick delta, because the scraper progress callback exposes only cumulative
  `done`/`total` (no per-tick timing). This is documented in monitoring-design.
- **GPU monitoring requires an optional library** (`GPUtil`); without it GPU is
  `None`/unavailable. GPU is never a hard dependency.
- **No automatic retention cron** — `purge_old(days)` exists and is tested but is
  not invoked on a timer in this phase (no auto-changes). A future scheduler/UI
  can call it.
- **Diminishing-returns `Observed` requires ≥3 distinct worker levels** of real
  job data; with less data the basis is `Estimated` or `Insufficient-Data`.
- **Process peaks are session-scoped** (since `start_monitoring`), so a restart
  before job finalize loses the peak window for that job's bottleneck signal.

## 5. Files created / modified

**Created**
- `performance.py` — full subsystem (capabilities, monitors, store, analyzer,
  recommendation engine, facade).
- `tests/test_performance.py` — 21 tests.
- `docs/product-discovery/phase-3.6-*.md` (8 docs: architecture, monitoring-design,
  performance-storage, analysis-rules, recommendation-engine, performance-privacy,
  mcp-performance, this test-report).

**Modified**
- `settings.py` — `PerformanceSettings` dataclass + validation.
- `app_events.py` — 5 `PERFORMANCE_*` event kinds.
- `app.py` — `PerformanceService` facade wired as `app.performance`, monitoring
  auto-started, closed on `close()`.
- `job_manager.py` — `performance_recorder` hook (start/progress/end).
- `mcp_server.py` — 6 read-only performance tools.
- `skills/reelminner/SKILL.md` (+ mirror) — documented 6 tools.
- `tests/test_mcp_server.py` — `EXPECTED_TOOLS` +6.
