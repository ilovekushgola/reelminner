# Phase 3.6 — Performance Privacy

> What the performance system collects, what it never collects, and why it is
> safe to run on a local machine. Backend-only; no telemetry leaves the host.

## 1. Collected (local, non-sensitive)

All of the following is written only to the local, git-ignored SQLite DB under
the app `data_dir`. Nothing is uploaded.

**Machine profile (`perf_machine_profile`)**
- OS name / version, CPU architecture, Python version.
- CPU logical & physical core counts, total RAM bytes, total disk bytes.
- `gpu_available` (bool) and, only if an optional GPU library is present, a GPU
  model string (best-effort, never required).

**System snapshot (in-memory, not per-sample persisted)**
- cpu%, memory%, disk used%, net bytes sent/recv, optional gpu%.

**Process snapshot (in-memory)**
- Reelminner process cpu% / rss, child browser count, child cpu% / rss.

**Job performance (`perf_job_summary`, `perf_job_sample`, `perf_config_outcome`)**
- job_id, worker_count, delay, `network_mode`, `proxy_id` (a reference id only),
  and **counts**: processed / successful / failed / blocked / rate_limited, plus
  derived throughput (urls/min, avg sec/url, ETA).

**Events**
- `PERFORMANCE_MONITOR_STARTED/STOPPED`, `PERFORMANCE_WARNING`,
  `PERFORMANCE_RECOMMENDATION_AVAILABLE`, `JOB_PERFORMANCE_RECORDED` — payloads
  carry only aggregate metadata (`interval`, `scope`, `kind`, `basis`,
  `workers`, `urls_per_min`). No samples, no credentials.

## 2. Never collected (explicitly)

- **No PII / host identity:** no hostname, username, IP address, MAC address,
  serial number, geolocation, or machine GUID.
- **No credentials / secrets:** no proxy username/password, no proxy host/scheme,
  no cookies, no session tokens, no Instagram credentials. Only `proxy_id`
  (an opaque reference) is stored.
- **No scrape targets:** target URLs, usernames, or post IDs are never stored in
  performance tables — only aggregate counts.
- **No result content:** scraped media, captions, or profile data are out of
  scope; the result store handles those separately.
- **No file contents / browsing history** of the user.
- **No autonomous collection of personal system data** beyond the compute
  metrics listed in §1.

## 3. GPU handling

GPU detection is best-effort and optional. If `GPUtil` (or another GPU library)
is not installed, `gpu_available` is `False` and the GPU field is `None`. When
enabled, only a coarse load percentage / model string is read — never a dump of
GPU memory contents or anything personal.

## 4. Storage & isolation

- All performance data lives in the same local SQLite file as the rest of the
  app state, under `data/` which is git-ignored.
- The DB is local to the machine; the architecture has no network egress for
  performance data (no cloud telemetry, no API calls).
- `proxy_id` in samples is safe-by-construction: `Proxy.to_safe_dict()` is the
  only proxy representation that could leak, and the performance layer stores
  only the id, not the safe dict.

## 5. Leak tests

`tests/test_performance.py` asserts that no `password`, `cookie`, `secret`,
`token`, or `username` string appears in any performance summary/sample dict, and
that capability detection output contains none of `hostname` / `username` /
`user` / `mac` / `ip` / `serial`.
