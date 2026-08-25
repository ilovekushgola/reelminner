# Phase 3.6 — Recommendation Engine

> Rule-based, data-driven, non-binding. `PerformanceRecommendationEngine` never
> changes a running job or a setting.

## 1. Principles

- **Real data only.** Recommendations are derived from `perf_config_outcome`
  rows produced by *actual* finished jobs. There are no synthetic benchmarks,
  no autonomous stress tests, no fake metrics.
- **Honest basis.** Each recommendation carries a `basis` of `Observed`,
  `Estimated`, or `Insufficient-Data`.
- **No fabricated confidence.** Confidence is `LIKELY` / `POSSIBLE` / `UNKNOWN`
  (never a made-up percentage). When evidence is thin, basis is
  `Insufficient-Data` and the message says exactly what to collect next.
- **No side effects.** The engine is pure: it reads analyzer output + capabilities
  and returns `PerformanceRecommendation` objects. The MCP tools return them;
  nothing mutates `workers`, `delay`, or running jobs.

## 2. Worker-count recommendation (`recommend_workers`)

Input: list of `perf_config_outcome` rows.

- **No data** → `basis = Insufficient-Data`, `suggested_workers = None`, message:
  *"run jobs with different worker counts to receive a data-driven worker
  recommendation."*
- **Data present** → compare workers, compute the diminishing-returns safe max
  (`diminishing_returns`). `suggested_workers = min(safe_max, logical_cpus)`.
  - `basis = Observed` when ≥3 worker levels exist; else `Estimated`.
  - `confidence = LIKELY` if Observed, else `POSSIBLE`.
  - Message ends with: *"This is a recommendation only — no running job or
    setting is changed automatically."*

The `logical_cpus` cap comes from `SystemCapabilities.cpu_logical` so the engine
never suggests more workers than the host realistically has.

## 3. Per-job recommendations (`recommend_from_summary`)

Given a finished job's summary + the outcome dataset, the engine may also emit:
- `NETWORK` recommendation when `NETWORK_LIMITED` was detected (suggest higher
  delay / proxy rotation; explicitly "correlation only").
- `MEMORY` recommendation when `MEMORY_BOUND` detected (fewer workers / headless).
- `CPU` recommendation when `CPU_BOUND` detected (fewer workers).
- Always appends the worker-count recommendation from §2.

Each carries `basis`/`confidence` and hedged language.

## 4. Current-capacity recommendation (PART 13)

`get_worker_recommendation()` returns the global worker recommendation from all
historical outcomes — answering "what worker count should I try next?" without
touching anything. This satisfies the "current capacity recommendation, no
auto-changes" requirement.

## 5. Benchmark support (PART 14)

Only *real-job comparison* is supported: reusing `perf_config_outcome` to compare
throughput across different worker/delay/network configurations. There is **no**
synthetic benchmark runner and **no** autonomous stress testing — those are
explicit non-goals.

## 6. Output shape

```python
PerformanceRecommendation(
    kind="worker_count",            # or "network" / "memory" / "cpu"
    basis="Observed",               # Observed | Estimated | Insufficient-Data
    confidence="LIKELY",            # LIKELY | POSSIBLE | UNKNOWN
    message="...",                  # hedged, never asserts causation
    suggested_workers=3,            # None when Insufficient-Data
)
```
