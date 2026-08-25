import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper import ReelData
from storage import ResultStore
from results import (
    FilterCondition,
    FilterOp,
    InvalidFilterError,
    PageSpec,
    ResultQuery,
    ResultService,
    SortSpec,
)

URLS = ["https://www.instagram.com/reel/{0:04d}/".format(i) for i in range(40)]


def make_row(i):
    status = "ok"
    if i % 7 == 0:
        status = "error: structure_change"
    elif i % 11 == 0:
        status = "rate_limited"
    return ReelData(
        username=f"user{i}",
        reel_url=f"https://www.instagram.com/reel/{i:04d}/",
        status=status,
        plays=str((i + 1) * 100),
        likes=str((i + 1) * 10),
        comments=str(i),
        followers=str((i + 1) * 5),
        is_verified=(i % 2 == 0),
        music_title=f"Song {i}",
        music_artist=("Artist X" if i % 3 == 0 else "Artist Y"),
        full_name=f"Full Name {i}",
    )


class TestResultService(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = ResultStore(self.tmp)
        self.svc = ResultService(self.store, default_page_size=10)
        self.rows = [make_row(i) for i in range(25)]
        self.store.write_results("job1", self.rows)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_get_available_columns(self):
        cols = self.svc.get_available_columns()
        for f in ("username", "plays", "likes", "comments", "is_verified",
                 "music_title", "music_artist", "status"):
            self.assertIn(f, cols)

    def test_pagination(self):
        r1 = self.svc.paginate_results("job1", page=1, page_size=10)
        self.assertEqual(len(r1.rows), 10)
        self.assertEqual(r1.total_in_job, 25)
        self.assertTrue(r1.has_next)
        self.assertFalse(r1.has_prev)
        r2 = self.svc.paginate_results("job1", page=2, page_size=10)
        self.assertEqual(len(r2.rows), 10)
        self.assertTrue(r2.has_next)
        r3 = self.svc.paginate_results("job1", page=3, page_size=10)
        self.assertEqual(len(r3.rows), 5)
        self.assertFalse(r3.has_next)
        self.assertTrue(r3.has_prev)
        # pages are non-overlapping
        self.assertNotEqual(
            {x.reel_url for x in r1.rows}, {x.reel_url for x in r2.rows}
        )

    def test_search(self):
        res = self.svc.search_results("job1", "user5")
        self.assertGreater(res.total_matched, 0)
        for r in res.rows:
            self.assertIn("user5", r.username)

    def test_filter_is_verified(self):
        res = self.svc.filter_results(
            "job1",
            [FilterCondition(field="is_verified", op=FilterOp.EQ, value=True)],
        )
        self.assertEqual(res.total_matched, 13)  # even i in 0..24
        for r in res.rows:
            self.assertTrue(r.is_verified)

    def test_filter_numeric_gte(self):
        res = self.svc.filter_results(
            "job1",
            [FilterCondition(field="plays", op=FilterOp.GTE, value=500)],
        )
        # (i+1)*100 >= 500 -> i >= 4
        self.assertEqual(res.total_matched, 21)
        for r in res.rows:
            self.assertGreaterEqual(int(r.plays), 500)

    def test_filter_contains(self):
        res = self.svc.filter_results(
            "job1",
            [FilterCondition(field="music_artist", op=FilterOp.CONTAINS,
                             value="Artist X")],
        )
        # i % 3 == 0 in 0..24 -> 9 rows
        self.assertEqual(res.total_matched, 9)

    def test_filter_views_alias(self):
        res = self.svc.filter_results(
            "job1",
            [FilterCondition(field="views", op=FilterOp.GTE, value=300)],
        )
        self.assertEqual(res.total_matched, 23)  # (i+1)*100>=300 -> i>=2

    def test_sort_descending(self):
        res = self.svc.sort_results("job1", "plays", descending=True, page_size=25)
        plays = [int(r.plays) for r in res.rows]
        self.assertEqual(plays, sorted(plays, reverse=True))

    def test_empty_dataset(self):
        self.store.write_results("empty", [])
        res = self.svc.paginate_results("empty", page=1)
        self.assertEqual(res.total_in_job, 0)
        self.assertEqual(len(res.rows), 0)
        stats = self.svc.get_result_statistics("empty")
        self.assertEqual(stats.total_rows, 0)

    def test_large_mock_dataset(self):
        big = [make_row(i) for i in range(1000)]
        self.store.write_results("big", big)
        res = self.svc.paginate_results("big", page=2, page_size=100)
        self.assertEqual(res.total_in_job, 1000)
        self.assertEqual(len(res.rows), 100)
        self.assertTrue(res.has_next)

    def test_statistics(self):
        stats = self.svc.get_result_statistics("job1")
        self.assertEqual(stats.total_rows, 25)
        # i%7==0 -> structure_change (blocked): i=0,7,14,21 = 4
        # i%11==0 and not already blocked -> rate_limited: i=11,22 = 2
        # successful = 25 - 4 - 2 = 19
        self.assertEqual(stats.successful_rows, 19)
        self.assertEqual(stats.blocked_rows, 4)       # error: structure_change
        self.assertEqual(stats.rate_limited_rows, 2)  # rate_limited
        self.assertEqual(stats.verified_profiles, 13)
        self.assertGreater(stats.total_engagement, 0)
        self.assertGreater(stats.average_engagement, 0)

    def test_invalid_filter_field(self):
        with self.assertRaises(InvalidFilterError):
            self.svc.filter_results(
                "job1",
                [FilterCondition(field="not_a_field", op=FilterOp.EQ, value="x")],
            )

    def test_invalid_filter_op(self):
        with self.assertRaises(InvalidFilterError):
            self.svc.filter_results(
                "job1",
                [FilterCondition(field="username", op="bogus", value="x")],
            )

    def test_export_filtered(self):
        import json

        out = os.path.join(self.tmp, "filtered.csv")
        path = self.svc.export_filtered(
            "job1", "csv", out,
            ResultQuery(filters=[FilterCondition(field="is_verified",
                                                 op=FilterOp.EQ, value=True)]),
        )
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertGreater(len(lines), 1)  # header + rows


if __name__ == "__main__":
    unittest.main()
