import json
import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app_events import AppEventKind
from app import ReelminnerApplication
from results import FilterCondition, FilterOp, ResultQuery
from scraper import ReelData
from sessions import SessionStatus


def write_cookies(path):
    data = {"cookies": [{"name": "sessionid", "value": "x",
                         "expires": int(time.time()) + 999999}]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def make_row(i, url):
    status = "ok"
    if i % 4 == 0:
        status = "rate_limited"
    return ReelData(
        username=f"user{i}", reel_url=url, status=status,
        plays=str((i + 1) * 100), likes=str((i + 1) * 10),
        comments=str(i), followers=str((i + 1) * 5),
        is_verified=(i % 2 == 0), music_title=f"Song {i}",
        music_artist=("Artist X" if i % 3 == 0 else "Artist Y"),
        full_name=f"Full Name {i}",
    )


class FakeScraperService:
    def __init__(self, *, headless=False, workers=3, delay=2.0, state_file=None,
                 event_sink=None, log=None, **_):
        self.state_file = state_file
        self.event_sink = event_sink
        self.log = log
        self._stop = threading.Event()

    def scrape(self, urls, with_profiles=True, progress_cb=None, row_cb=None):
        results = []
        for i, u in enumerate(urls):
            rd = make_row(i, u)
            results.append(rd)
            if row_cb:
                row_cb(rd)
            if progress_cb:
                progress_cb(i + 1, len(urls))
        return results

    def stop(self):
        self._stop.set()


def fake_factory(**kwargs):
    return FakeScraperService(**kwargs)


URLS = [
    "https://www.instagram.com/reel/0001/",
    "https://www.instagram.com/reel/0002/",
    "https://www.instagram.com/reel/0003/",
    "https://www.instagram.com/reel/0004/",
    "https://www.instagram.com/reel/0005/",
    "https://www.instagram.com/reel/0006/",
    "https://www.instagram.com/reel/0007/",
    "https://www.instagram.com/reel/0008/",
]


class TestPhase3Integration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = ReelminnerApplication(
            data_dir=self.tmp, scraper_factory=fake_factory
        )
        self.events = []
        self.app.event_bus.subscribe(lambda e: self.events.append(e))
        self.cookies = os.path.join(self.tmp, "cookies.json")
        write_cookies(self.cookies)

    def tearDown(self):
        self.app.close()
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_full_flow(self):
        # 1. Session
        sess = self.app.sessions.import_session(
            "Main", self.cookies, source="editthiscookie"
        )
        tested = self.app.sessions.test_session(sess.id)
        self.assertEqual(tested.status, SessionStatus.HEALTHY)
        self.assertEqual(len(self.app.sessions.list_sessions()), 1)

        # 2. Job with session
        job = self.app.jobs.create_job(URLS, session_id=sess.id)
        self.assertEqual(job.session_id, sess.id)

        # 3. Run (simulated)
        self.app.jobs.start_job(job.id)
        self.app.jobs.wait_for_job(job.id)
        reloaded = self.app.jobs.get_job(job.id)
        self.assertEqual(reloaded.status.value, "completed")

        # 4. Persist results
        stats = self.app.results.get_result_statistics(job.id)
        self.assertEqual(stats.total_rows, len(URLS))

        # 5. Query results
        res = self.app.results.filter_results(
            job.id,
            [FilterCondition(field="is_verified", op=FilterOp.EQ, value=True)],
        )
        self.assertEqual(res.total_matched, 4)  # even i in 0..7

        sorted_res = self.app.results.sort_results(
            job.id, "plays", descending=True, page_size=len(URLS)
        )
        plays = [int(r.plays) for r in sorted_res.rows]
        self.assertEqual(plays, sorted(plays, reverse=True))

        # 6. Export filtered results
        out = os.path.join(self.tmp, "out.csv")
        self.app.results.export_filtered(
            job.id, "csv", out,
            ResultQuery(filters=[FilterCondition(field="is_verified",
                                                 op=FilterOp.EQ, value=True)]),
        )
        self.assertTrue(os.path.exists(out))
        with open(out, encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertEqual(len(lines), 5)  # header + 4 verified

    def test_events_emitted(self):
        sess = self.app.sessions.import_session("Main", self.cookies)
        self.app.sessions.test_session(sess.id)
        job = self.app.jobs.create_job(URLS, session_id=sess.id)
        self.app.jobs.start_job(job.id)
        self.app.jobs.wait_for_job(job.id)
        kinds = [e.kind for e in self.events]
        self.assertIn(AppEventKind.SESSION_CREATED, kinds)
        self.assertIn(AppEventKind.SESSION_TESTED, kinds)
        self.assertIn(AppEventKind.JOB_CREATED, kinds)
        self.assertIn(AppEventKind.RESULTS_AVAILABLE, kinds)

    def test_settings_service_available(self):
        # settings defaults available through the facade
        self.assertEqual(self.app.settings.get().scraping.workers, 3)
        self.app.settings.update(scraping_workers=6)
        self.assertEqual(self.app.settings.get().scraping.workers, 6)


if __name__ == "__main__":
    unittest.main()
