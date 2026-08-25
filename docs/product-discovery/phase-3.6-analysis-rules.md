# Phase 3.6 — Analysis Rules

> The rule set behind `PerformanceAnalyzer`. Conservative by design: it reports
> *correlation*, never asserts *causation*, and labels confidence as
> `LIKELY` / `POSSIBLE` / `UNKNOWN`.

## 1. Worker-count comparison (`compare_workers`)

Groups every `perf_config_outcome` row by `workers` and reports, per level:
`mean_urls_per_min`, `mean_successful`, `mean_processed`, `mean_blocked`,
`mean_rate_limited`, and `samples`. Thread-safe `.get(...)` access is used so a
row missing `blocked`/`rate_limited` does not raise.

## 2. Diminishing returns (`diminishing_returns`)

Across worker levels sorted ascending, the marginal throughput gain is:

```
marginal_gain = (cur_mean_urls_per_min - prev_mean_urls_per_min) / prev
```

The "safe max" worker count is the highest level before the marginal gain drops
**below 10%**. The basis is:
- `Observed` — ≥ 3 distinct worker levels have data (a real plateau is visible).
- `Estimated` — only 1–2 levels have data (extrapolation, explicitly labelled).

This guards against overfitting to a single noisy job.

## 3. Bottleneck detection (`detect_bottleneck`)

Inputs: the `JobPerformanceSummary`, the process peak CPU% and peak RSS (captured
during the monitoring session), total RAM, and the worker comparison. Output:
`(label, confidence)`.

| Condition | Label | Confidence |
|---|---|---|
| `(blocked + rate_limited) / max(1, processed) >= 0.30` | `NETWORK_LIMITED` | `LIKELY` |
| `(blocked + rate_limited) / max(1, processed) >= 0.10` | `NETWORK_LIMITED` | `POSSIBLE` |
| `process_peak_rss / total_ram >= 0.90` | `MEMORY_BOUND` | `LIKELY` |
| `process_peak_rss / total_ram >= 0.75` | `MEMORY_BOUND` | `POSSIBLE` |
| `process_peak_cpu >= 90.0` | `CPU_BOUND` | `POSSIBLE` |
| safe-max workers `<` this job's worker count (plateau) | `SCRAPER_LIMITED` | `POSSIBLE` |
| none of the above | `UNKNOWN` | `UNKNOWN` |

Key properties:
- **Conservative.** High block/rate-limit ratio is the only thing that reaches
  `LIKELY`; everything else is `POSSIBLE` or `UNKNOWN`.
- **No causation claimed.** The label is a *possible* contributor. The
  recommendation text always includes a hedge ("observed", "may", "correlation
  only").
- **Evidence-gated.** With insufficient data the detector returns `UNKNOWN /
  UNKNOWN` rather than guessing.
- **CPU/MEMORY use process peaks, not system-wide averages**, so a busy
  background OS process does not falsely pin the scraper as CPU-bound.

## 4. Language rules (enforced in text)

- Every recommendation and label says "observed" / "may" / "likely" — never
  "caused by".
- Confidence is one of `LIKELY` / `POSSIBLE` / `UNKNOWN`; never fabricated as a
  percentage.
- Basis is one of `Observed` / `Estimated` / `Insufficient-Data`; when data is
  thin the basis is `Insufficient-Data` and the message states exactly what is
  missing (e.g. "run jobs with different worker counts").

## 5. What is explicitly NOT done

- No automatic worker scaling or job mutation.
- No synthetic/artificial benchmarks or autonomous stress testing.
- No ML model, no external API call, no cloud telemetry.
- No assertion that a bottleneck *caused* low throughput.
