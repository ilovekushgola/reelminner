"""Result Service — clean query layer over the Data Explorer backend.

Frontends must go through :class:`ResultService` and never parse the JSONL
result files directly. See ``docs/product-discovery/phase-3-results-design.md``.

Performance approach: results are streamed row-by-row from the JSONL file
(``ResultStore.iter_results``). For queries that need filtering/search/sorting
we materialise only the *matched* subset; for pure pagination (no filter/search/
sort) we stream and keep only the requested page, so we never load the whole
dataset into memory unnecessarily.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from scraper import ReelData
from storage import ResultStore, StorageError

# Fields whose values are human-formatted counts ("1.2M", "345").
NUMERIC_FIELDS = {"followers", "likes", "comments", "plays", "reels_count"}
# Friendly aliases used by the UI/query layer.
FIELD_ALIASES = {"views": "plays"}
# Text fields scanned by free-text search.
SEARCH_FIELDS = [
    "username", "full_name", "caption", "music_title", "music_artist",
    "bio", "reel_url", "profile_url",
]


class InvalidFilterError(Exception):
    """Raised when a filter references an unknown field or operator."""


class FilterOp(str, Enum):
    EQ = "eq"
    NE = "ne"
    CONTAINS = "contains"
    GTE = "gte"
    LTE = "lte"
    GT = "gt"
    LT = "lt"
    IN = "in"


@dataclass
class PageSpec:
    page: int = 1
    page_size: int = 50

    @property
    def offset(self) -> int:
        return (max(1, self.page) - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


@dataclass
class SortSpec:
    field: str
    descending: bool = False


@dataclass
class FilterCondition:
    field: str
    op: FilterOp
    value: Any


@dataclass
class ResultQuery:
    search: Optional[str] = None
    filters: list[FilterCondition] = field(default_factory=list)
    sort: Optional[SortSpec] = None
    page: PageSpec = field(default_factory=PageSpec)


@dataclass
class ResultSet:
    rows: list
    total_matched: int
    total_in_job: int
    page: int
    page_size: int
    has_next: bool
    has_prev: bool

    def to_dict(self) -> dict:
        return {
            "total_matched": self.total_matched,
            "total_in_job": self.total_in_job,
            "page": self.page,
            "page_size": self.page_size,
            "has_next": self.has_next,
            "has_prev": self.has_prev,
            "returned": len(self.rows),
            "rows": [getattr(r, "to_dict", lambda: r)() for r in self.rows],
        }


@dataclass
class ResultStatistics:
    total_rows: int = 0
    successful_rows: int = 0
    failed_rows: int = 0
    partial_rows: int = 0
    blocked_rows: int = 0
    rate_limited_rows: int = 0
    verified_profiles: int = 0
    total_engagement: int = 0
    average_engagement: float = 0.0

    def to_dict(self) -> dict:
        return {
            "total_rows": self.total_rows,
            "successful_rows": self.successful_rows,
            "failed_rows": self.failed_rows,
            "partial_rows": self.partial_rows,
            "blocked_rows": self.blocked_rows,
            "rate_limited_rows": self.rate_limited_rows,
            "verified_profiles": self.verified_profiles,
            "total_engagement": self.total_engagement,
            "average_engagement": self.average_engagement,
        }


def parse_count(text: Any) -> int:
    """Parse Instagram-style counts ('1.2M', '345', '12.3K') to int."""
    if text is None:
        return 0
    s = str(text).strip().replace(",", "")
    if not s:
        return 0
    low = s.lower().rstrip(" ")
    mult = 1
    if low.endswith("k"):
        mult, low = 1_000, low[:-1]
    elif low.endswith("m"):
        mult, low = 1_000_000, low[:-1]
    elif low.endswith("b"):
        mult, low = 1_000_000_000, low[:-1]
    try:
        return int(float(low) * mult)
    except ValueError:
        return 0


class ResultService:
    """Typed access to per-job results: query, stats, filtered export."""

    def __init__(
        self,
        result_store: ResultStore,
        default_page_size: int = 50,
    ) -> None:
        self._store = result_store
        self._default_page_size = default_page_size

    # ------------------------------------------------------------------ #
    # metadata
    # ------------------------------------------------------------------ #
    def get_available_columns(self) -> list[str]:
        return ReelData.csv_columns()

    # ------------------------------------------------------------------ #
    # core query
    # ------------------------------------------------------------------ #
    def query(self, job_id: str, query: ResultQuery) -> ResultSet:
        page = query.page
        if page.page_size is None or page.page_size <= 0:
            page = PageSpec(page=page.page, page_size=self._default_page_size)

        needs_full = bool(query.search) or bool(query.filters) or query.sort
        if needs_full:
            matched = [
                r for r in self._store.iter_results(job_id)
                if self._matches(r, query)
            ]
            total_in_job = self._store.count(job_id)
            total_matched = len(matched)
            if query.sort is not None:
                matched.sort(
                    key=self._sort_key(query.sort), reverse=query.sort.descending
                )
            start = page.offset
            end = start + page.limit
            return ResultSet(
                rows=matched[start:end],
                total_matched=total_matched,
                total_in_job=total_in_job,
                page=page.page,
                page_size=page.page_size,
                has_next=end < total_matched,
                has_prev=page.page > 1,
            )
        # Pure pagination: stream and keep only the requested page.
        page_rows: list = []
        total_in_job = 0
        start, end = page.offset, page.offset + page.limit
        for r in self._store.iter_results(job_id):
            total_in_job += 1
            if start < total_in_job <= end:
                page_rows.append(r)
        return ResultSet(
            rows=page_rows,
            total_matched=total_in_job,
            total_in_job=total_in_job,
            page=page.page,
            page_size=page.page_size,
            has_next=end < total_in_job,
            has_prev=page.page > 1,
        )

    def collect(self, job_id: str, query: ResultQuery) -> list:
        """Return all matched rows (no pagination) — used for export."""
        if not (query.search or query.filters or query.sort):
            return list(self._store.iter_results(job_id))
        return [
            r for r in self._store.iter_results(job_id) if self._matches(r, query)
        ]

    # ------------------------------------------------------------------ #
    # convenience wrappers
    # ------------------------------------------------------------------ #
    def get_results(
        self,
        job_id: str,
        page: int = 1,
        page_size: Optional[int] = None,
        search: Optional[str] = None,
        filters: Optional[list[FilterCondition]] = None,
        sort: Optional[SortSpec] = None,
    ) -> ResultSet:
        return self.query(
            job_id,
            ResultQuery(
                search=search,
                filters=filters or [],
                sort=sort,
                page=PageSpec(page=page, page_size=page_size or self._default_page_size),
            ),
        )

    def search_results(self, job_id: str, text: str, page: int = 1,
                       page_size: Optional[int] = None) -> ResultSet:
        return self.query(
            job_id,
            ResultQuery(
                search=text,
                page=PageSpec(page=page, page_size=page_size or self._default_page_size),
            ),
        )

    def filter_results(self, job_id: str, filters: list[FilterCondition],
                       page: int = 1, page_size: Optional[int] = None) -> ResultSet:
        return self.query(
            job_id,
            ResultQuery(
                filters=filters,
                page=PageSpec(page=page, page_size=page_size or self._default_page_size),
            ),
        )

    def sort_results(self, job_id: str, field: str, descending: bool = False,
                     page: int = 1, page_size: Optional[int] = None) -> ResultSet:
        return self.query(
            job_id,
            ResultQuery(
                sort=SortSpec(field=field, descending=descending),
                page=PageSpec(page=page, page_size=page_size or self._default_page_size),
            ),
        )

    def paginate_results(self, job_id: str, page: int = 1,
                         page_size: Optional[int] = None) -> ResultSet:
        return self.query(
            job_id,
            ResultQuery(page=PageSpec(page=page, page_size=page_size or self._default_page_size)),
        )

    def get_result(self, job_id: str, reel_url: str) -> Optional[ReelData]:
        for r in self._store.iter_results(job_id):
            if getattr(r, "reel_url", None) == reel_url:
                return r
        return None

    # ------------------------------------------------------------------ #
    # statistics
    # ------------------------------------------------------------------ #
    def get_result_statistics(self, job_id: str) -> ResultStatistics:
        stats = ResultStatistics()
        for r in self._store.iter_results(job_id):
            stats.total_rows += 1
            status = (getattr(r, "status", "") or "").lower()
            if status == "ok":
                stats.successful_rows += 1
                eng = (
                    parse_count(getattr(r, "plays", ""))
                    + parse_count(getattr(r, "likes", ""))
                    + parse_count(getattr(r, "comments", ""))
                )
                stats.total_engagement += eng
                # "partial" = ok but no engagement captured at all
                if not (getattr(r, "plays", "") or getattr(r, "likes", "")
                        or getattr(r, "comments", "")):
                    stats.partial_rows += 1
            elif "rate_limited" in status:
                stats.rate_limited_rows += 1
            elif status in ("session_expired", "unavailable",
                            "error: structure_change"):
                stats.blocked_rows += 1
            else:
                stats.failed_rows += 1
            if getattr(r, "is_verified", False):
                stats.verified_profiles += 1
        if stats.successful_rows > 0:
            stats.average_engagement = round(
                stats.total_engagement / stats.successful_rows, 2
            )
        return stats

    # ------------------------------------------------------------------ #
    # filtered export
    # ------------------------------------------------------------------ #
    def export_filtered(
        self,
        job_id: str,
        fmt: str,
        path: str,
        query: Optional[ResultQuery] = None,
    ) -> str:
        rows = self.collect(job_id, query or ResultQuery())
        fmt = (fmt or "csv").lower()
        if fmt == "csv":
            from scraper import write_csv

            write_csv(rows, path)
        elif fmt == "json":
            from scraper import export_json

            export_json(rows, path)
        elif fmt == "xlsx":
            from scraper import export_excel

            export_excel(rows, path)
        else:
            raise ValueError(f"Unsupported export format: {fmt}")
        return path

    # ------------------------------------------------------------------ #
    # matching internals
    # ------------------------------------------------------------------ #
    def _matches(self, row: ReelData, query: ResultQuery) -> bool:
        if query.search and not self._matches_search(row, query.search):
            return False
        for cond in query.filters:
            if not self._matches_condition(row, cond):
                return False
        return True

    def _matches_search(self, row: ReelData, text: str) -> bool:
        needle = text.lower()
        for f in SEARCH_FIELDS:
            val = str(getattr(row, f, "") or "").lower()
            if needle in val:
                return True
        return False

    def _matches_condition(self, row: ReelData, cond: FilterCondition) -> bool:
        field = FIELD_ALIASES.get(cond.field, cond.field)
        if field not in self.get_available_columns():
            raise InvalidFilterError(f"Unknown filter field: {cond.field}")
        try:
            op = FilterOp(cond.op)
        except ValueError:
            raise InvalidFilterError(f"Unknown filter operator: {cond.op}")
        raw = getattr(row, field, "")

        if field in NUMERIC_FIELDS:
            lhs = parse_count(raw)
            if op in (FilterOp.GTE, FilterOp.LTE, FilterOp.GT, FilterOp.LT):
                rhs = parse_count(cond.value)
                if op is FilterOp.GTE:
                    return lhs >= rhs
                if op is FilterOp.LTE:
                    return lhs <= rhs
                if op is FilterOp.GT:
                    return lhs > rhs
                return lhs < rhs
            # EQ / NE / CONTAINS on numeric -> compare parsed ints for eq/ne,
            # raw string for contains.
            if op is FilterOp.CONTAINS:
                return str(cond.value).lower() in str(raw).lower()
            rhs = parse_count(cond.value)
            return (lhs == rhs) if op is FilterOp.EQ else (lhs != rhs)

        if field == "is_verified":
            target = str(cond.value).lower() in ("true", "1", "yes")
            actual = bool(raw)
            return (actual == target) if op in (FilterOp.EQ, FilterOp.NE) else False

        sval = str(raw).lower()
        scond = str(cond.value).lower()
        if op is FilterOp.EQ:
            return sval == scond
        if op is FilterOp.NE:
            return sval != scond
        if op is FilterOp.CONTAINS:
            return scond in sval
        if op is FilterOp.IN:
            members = cond.value if isinstance(cond.value, list) else [cond.value]
            return sval in [str(m).lower() for m in members]
        # GTE/LTE/GT/LT on strings -> lexicographic
        if op is FilterOp.GTE:
            return sval >= scond
        if op is FilterOp.LTE:
            return sval <= scond
        if op is FilterOp.GT:
            return sval > scond
        return sval < scond

    def _sort_key(self, sort: SortSpec):
        field = FIELD_ALIASES.get(sort.field, sort.field)
        numeric = field in NUMERIC_FIELDS

        def key(row: ReelData):
            val = getattr(row, field, "")
            if numeric:
                return parse_count(val)
            return str(val).lower()

        return key
