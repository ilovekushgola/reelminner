import json
import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app_events import ApplicationEventBus, AppEventKind
from jobs import JobStatus
from scraper import ReelData
from sessions import (
    SessionManager,
    SessionStatus,
    SessionStore,
    _default_session_validator,
)
from job_manager import JobManager
from jobs import Job, JobConfig


def write_cookies(path, *, expired=False):
    exp = 1 if expired else int(time.time()) + 999999
    data = {"cookies": [{"name": "sessionid", "value": "abc", "expires": exp}]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


class FakeScraperService:
    instances = []

    def __init__(self, *, headless=False, workers=3, delay=2.0, state_file=None,
                 event_sink=None, log=None, **_):
        self.headless = headless
        self.workers = workers
        self.delay = delay
        self.state_file = state_file
        self.event_sink = event_sink
        self.log = log
        self._stop = threading.Event()
        FakeScraperService.instances.append(self)

    def scrape(self, urls, with_profiles=True, progress_cb=None, row_cb=None):
        results = []
        for i, u in enumerate(urls, 1):
            rd = ReelData(reel_url=u, status="ok")
            results.append(rd)
            if row_cb:
                row_cb(rd)
            if progress_cb:
                progress_cb(i, len(urls))
        return results

    def stop(self):
        self._stop.set()


def fake_factory(**kwargs):
    return FakeScraperService(**kwargs)


class TestSessionLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.bus = ApplicationEventBus()
        self.events = []
        self.bus.subscribe(lambda e: self.events.append(e))
        self.sm = SessionManager(
            data_dir=self.tmp, event_bus=self.bus,
            validator=lambda p: (SessionStatus.HEALTHY, None),
        )
        self.cookies = os.path.join(self.tmp, "cookies.json")
        write_cookies(self.cookies)

    def tearDown(self):
        self.sm.close()
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_import_persists_metadata_not_cookies(self):
        sess = self.sm.import_session("My IG", self.cookies, source="editthiscookie")
        self.assertIsNotNone(sess.cookies_path)
        reloaded = self.sm.get_session(sess.id)
        self.assertEqual(reloaded.name, "My IG")
        self.assertEqual(reloaded.status, SessionStatus.UNKNOWN)
        # cookies content must not be in the metadata record
        self.assertNotIn("sessionid", reloaded.__dict__)
        self.assertIn(AppEventKind.SESSION_CREATED, [e.kind for e in self.events])

    def test_reload_from_store(self):
        sess = self.sm.import_session("A", self.cookies)
        sm2 = SessionManager(data_dir=self.tmp, event_bus=ApplicationEventBus(),
                             validator=lambda p: (SessionStatus.HEALTHY, None))
        reloaded = sm2.get_session(sess.id)
        self.assertEqual(reloaded.id, sess.id)
        sm2.close()

    def test_health_state_changes(self):
        sess = self.sm.import_session("A", self.cookies)
        tested = self.sm.test_session(sess.id)
        self.assertEqual(tested.status, SessionStatus.HEALTHY)
        self.assertIsNotNone(tested.last_checked_at)
        self.assertIn(AppEventKind.SESSION_TESTED, [e.kind for e in self.events])

    def test_expired_cookies_detected_by_default_validator(self):
        exp = os.path.join(self.tmp, "exp.json")
        write_cookies(exp, expired=True)
        sess = self.sm.import_session("Exp", exp)
        # use the REAL default validator (no browser)
        self.sm._validator = _default_session_validator
        tested = self.sm.test_session(sess.id)
        self.assertEqual(tested.status, SessionStatus.EXPIRED)

    def test_update_metadata_emits(self):
        sess = self.sm.import_session("A", self.cookies)
        updated = self.sm.update_session(sess.id, name="Renamed", username="bob")
        self.assertEqual(updated.name, "Renamed")
        self.assertEqual(updated.username, "bob")
        reloaded = self.sm.get_session(sess.id)
        self.assertEqual(reloaded.name, "Renamed")
        self.assertIn(AppEventKind.SESSION_UPDATED, [e.kind for e in self.events])

    def test_delete_removes_session(self):
        sess = self.sm.import_session("A", self.cookies)
        self.sm.delete_session(sess.id)
        self.assertIsNone(self.sm.get_session(sess.id))
        self.assertIsNone(self.sm.get_cookies_path(sess.id))

    def test_invalid_state_handling(self):
        with self.assertRaises(KeyError):
            self.sm.test_session("nope")
        with self.assertRaises(KeyError):
            self.sm.update_session("nope", name="x")


class TestJobSessionReference(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.bus = ApplicationEventBus()
        self.sm = SessionManager(
            data_dir=self.tmp, event_bus=self.bus,
            validator=lambda p: (SessionStatus.HEALTHY, None),
        )
        self.cookies = os.path.join(self.tmp, "cookies.json")
        write_cookies(self.cookies)
        self.jm = JobManager(
            data_dir=self.tmp, event_bus=self.bus,
            scraper_factory=fake_factory,
            session_state_resolver=self.sm.get_cookies_path,
            on_session_used=self.sm.mark_used,
        )
        FakeScraperService.instances.clear()

    def tearDown(self):
        self.jm.close()
        self.sm.close()
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_job_uses_session_cookies(self):
        sess = self.sm.import_session("A", self.cookies)
        job = self.jm.create_job(
            ["https://www.instagram.com/reel/AAAA/"], session_id=sess.id
        )
        self.assertEqual(job.session_id, sess.id)
        self.jm.start_job(job.id)
        self.jm.wait_for_job(job.id)
        # the engine was constructed with the session's cookies file
        scraper = FakeScraperService.instances[-1]
        self.assertEqual(scraper.state_file, sess.cookies_path)
        # session marked used
        self.assertIsNotNone(self.sm.get_session(sess.id).last_used_at)

    def test_deleted_session_falls_back_does_not_corrupt(self):
        sess = self.sm.import_session("A", self.cookies)
        job = self.jm.create_job(
            ["https://www.instagram.com/reel/BBBB/"], session_id=sess.id
        )
        self.sm.delete_session(sess.id)
        self.assertIsNone(self.sm.get_cookies_path(sess.id))  # resolver safe
        # job still starts (falls back to default state file), no crash
        self.jm.start_job(job.id)
        self.jm.wait_for_job(job.id)
        self.assertEqual(self.jm.get_job(job.id).status, JobStatus.COMPLETED)
        # historical job record keeps its session_id reference
        self.assertEqual(self.jm.get_job(job.id).session_id, sess.id)

    def test_job_without_session_backward_compatible(self):
        job = self.jm.create_job(["https://www.instagram.com/reel/CCCC/"])
        self.assertIsNone(job.session_id)
        self.jm.start_job(job.id)
        self.jm.wait_for_job(job.id)
        self.assertEqual(self.jm.get_job(job.id).status, JobStatus.COMPLETED)


if __name__ == "__main__":
    unittest.main()
