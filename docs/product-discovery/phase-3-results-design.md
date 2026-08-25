# Phase 3 — Results / Data Explorer Design

**Status:** Designed and implemented.
**Scope:** Clean query layer over per-job results (the Data Explorer backend).
**Rule:** The frontend must never parse JSONL directly.

---

## 1. Why a service layer

`ResultStore` (Phase 2) persists bulk rows as JSONL. Exposing that file to the
UI would leak the storage format and force the UI to re-implement filtering,
sorting, and pagination. `ResultService` is the single typed entry point.

```
Future Desktop UI / Data Explorer
        ↓  (search / filter / sort / paginate / stats / export)
   ResultService.get_results / search_results / filter_results /
   sort_results / paginate_results / get_result_statistics / export_filtered
        ↓
   ResultStore.iter_results  (streams JSONL line-by-line)
        ↓
   data/jobs/<job_id>.jsonl
```

---

## 2. Query model

```python
class FilterOp(str, Enum):
    EQ / NE / CONTAINS / GTE / LTE / GT / LT / IN

@dataclass
class FilterCondition:  field: str; op: FilterOp; value: Any

@dataclass
class SortSpec:        field: str; descending: bool = False

@dataclass
class PageSpec:        page: int = 1; page_size: int = 50

@dataclass
class ResultQuery:     search, filters[], sort, page
```

`ResultService.query(job_id, ResultQuery) -> ResultSet`
`ResultSet` = `rows` (page), `total_matched`, `total_in_job`, `page`,
`page_size`, `has_next`, `has_prev`.

Convenience wrappers (`get_results`, `search_results`, `filter_results`,
`sort_results`, `paginate_results`, `get_result`) all delegate to `query`.

---

## 3. Supported fields & operators

| Field | Type | Notes |
|-------|------|-------|
| username | string | eq / ne / contains / in |
| full_name, bio | string | search + contains |
| caption | string | search |
| music_title, music_artist | string | eq / contains |
| status | string | eq / contains |
| scrape_ts | string | eq / contains |
| is_verified | bool | eq / ne |
| followers, likes, comments, **views** | count | numeric GTE/LTE/GT/LT/EQ; `views` is an alias for `plays` |
| reels_count | count | numeric |

Numeric values are parsed with `parse_count` so `"1.2M"`, `"345"`, `"12.3K"`
compare correctly. Unknown fields or operators raise `InvalidFilterError`.

---

## 4. Performance approach

- **Streaming, not bulk load.** `ResultStore.iter_results` yields one
  `ReelData` per line; we never read the whole file as one blob.
- **Pure pagination** (no search/filter/sort): we stream and keep *only the
  requested page* in memory — large jobs paginate without materialising
  everything.
- **Filtered / searched / sorted queries:** we materialise only the *matched
  subset* (stream → predicate → keep matches), then sort + slice. Unmatched
  rows are discarded immediately.
- **Statistics** are computed by a single streaming pass that aggregates
  counts and engagement without holding rows.
- For very large matched sets, sorting still requires holding the matched
  subset; this is acceptable for the local single-user tool and is documented
  as a known limitation. A future index (e.g. SQLite FTS / columnar store) is
  out of scope.

---

## 5. Statistics (`get_result_statistics`)

Derived strictly from data the engine already produces (no invented metrics):

- `total_rows`
- `successful_rows` (status == `"ok"`)
- `failed_rows` (status not ok / blocked / rate-limited)
- `blocked_rows` (status in `session_expired` / `unavailable` /
  `error: structure_change`)
- `rate_limited_rows` (status contains `rate_limited`)
- `verified_profiles` (`is_verified`)
- `partial_rows` (status ok but *no* engagement captured — `plays`/`likes`/
  `comments` all empty)
- `total_engagement` / `average_engagement` (sum/avg of parsed
  plays+likes+comments over successful rows)

---

## 6. Filtered export

`export_filtered(job_id, fmt, path, query=None)` collects the matched rows
(`ResultService.collect`) and delegates to the **existing** exporters in
`scraper.py` — `write_csv`, `export_json`, `export_excel`. No export logic is
duplicated; the engine remains the source of truth for file formats. Supported
formats: `csv`, `json`, `xlsx`.

---

## 7. Files introduced

| File | Responsibility |
|------|----------------|
| `results.py` | `ResultService`, query model, `parse_count`, `InvalidFilterError` |

`storage.py` gained a streaming `iter_results` helper (additive). `scraper.py`
exporters are reused, not modified.
