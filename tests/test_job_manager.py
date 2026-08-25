import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from events import EventKind, ScraperEvent
from jobs import JobStatus
from scraper import ReelData
from app_events import ApplicationEventBus, AppEventKind
from job_manager import JobManager

URLS = [
    "https://www.instagram.com/reel/AAAA/",
    "https://www.instagram.com/reel/BBBB/",
    "https://www.instagram.com/reel/CCCC/",
    "https://www.instagram.com/reel/DDDD/",
    "https://www.instagram.com/reel/EEEE/",
    "https://www.instagram.com/reel/FFFF/",
]


class FakeScraperService:
    """Mimics ScraperService without a browser; honours cooperative stop."""

    def __init__(self, *, headless=False, workers=3, delay=2.0, state_file=None,
                 event_sink=None, log=None, raise_on_scrape=False):
        self.headless = headless
        self.workers = workers
        self.delay = delay
        self.state_file = state_file
        self.event_sink = event_sink
        self.log = log
        self.raise_on_scrape = raise_on_scrape
        self._stop = threading.Event()
        self.last_targets = None

    def scrape(self, urls, with_profiles=True, progress_cb=None, row_cb=None):
        self.last_targets = list(urls)
        if self.raise_on_scrape:
            raise RuntimeError("fake scrape boom")
        results = []
        total = len(urls)
        done = 0
        first = True
        for u in urls:
            # Cooperative: never abort the in-flight item, but refuse new ones.
            if not first and self._stop.is_set():
                break
            first = False
            time.sleep(self.delay)
            rd = ReelData(reel_url=u, status="ok")
            results.append(rd)
            done += 1
            if row_cb:
                row_cb(rd)
            if self.event_sink is not None:
                self.event_sink.emit(ScraperEvent(EventKind.ROW, {"reel_url": u}))
            if progress_cb:
                progress_cb(done, total)
            if self.event_sink is not None:
                self.event_sink.emit(
                    ScraperEvent(EventKind.PROGRESS, {"done": done, "total": total})
                )
        return results

    def stop(self):
        self._stop.set()


def make_factory(delay=0.05, raise_on_scrape=False):
    def factory(**kwargs):
        kwargs.pop("delay", None)  # use the fast test delay, not the job's
        return FakeScraperService(delay=delay, raise_on_scrape=raise_on_scrape,
                                  **kwargs)
    return factory


class JobManagerTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.bus = ApplicationEventBus()
        self.events = []
        self.bus.subscribe(lambda e: self.events.append(e))
        self.jm = JobManager(
            data_dir=self.tmp,
            db_name="test.db",
            event_bus=self.bus,
            scraper_factory=make_factory(delay=0.03),
        )

    def tearDown(self):
        try:
            self.jm.wait_for_idle()
            self.jm.close()
        except Exception:
            pass
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _wait(self, job_id, timeout=20):
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = self.jm.get_job(job_id)
            if job is not None and job.status in JobStatus.terminal_states():
                self.jm.wait_for_job(job_id)
                return job.status
            time.sleep(0.02)
        self.jm.wait_for_job(job_id)
        return self.jm.get_job(job_id).status


class TestLifecycle(JobManagerTestBase):
    def test_create_job_normalizes_and_emits(self):
        job = self.jm.create_job(URLS[:2])
        self.assertEqual(len(job.config.urls), 2)
        kinds = [e.kind for e in self.events]
        self.assertIn(AppEventKind.JOB_CREATED, kinds)

    def test_start_to_completion(self):
        job = self.jm.create_job(URLS)
        self.jm.start_job(job.id)
        status = self._wait(job.id)
        self.assertEqual(status, JobStatus.COMPLETED)
        reloaded = self.jm.get_job(job.id)
        self.assertEqual(reloaded.processed_items, 6)
        self.assertEqual(reloaded.successful_items, 6)
        self.assertEqual(len(self.jm.get_job_results(job.id)), 6)
        self.assertIn(AppEventKind.JOB_COMPLETED, [e.kind for e in self.events])
        self.assertIn(AppEventKind.JOB_PROGRESS, [e.kind for e in self.events])
        self.assertIn(AppEventKind.ROW_PROCESSED, [e.kind for e in self.events])

    def test_events_carry_job_context(self):
        job = self.jm.create_job(URLS[:1])
        self.jm.start_job(job.id)
        self._wait(job.id)
        for kind in (AppEventKind.JOB_CREATED, AppEventKind.JOB_STARTED,
                     AppEventKind.JOB_COMPLETED, AppEventKind.JOB_PROGRESS):
            evs = [e for e in self.events if e.kind == kind]
            self.assertTrue(evs, f"missing {kind}")
            self.assertEqual(evs[0].job_id, job.id)

    def test_pause_then_resume_merges_results(self):
        job = self.jm.create_job(URLS)
        self.jm.start_job(job.id)
        time.sleep(0.08)  # let a few items process
        self.jm.pause_job(job.id)
        paused_status = self._wait_until(job.id, JobStatus.PAUSED)
        self.assertEqual(paused_status, JobStatus.PAUSED)
        paused = self.jm.get_job(job.id)
        processed = paused.processed_items
        pending = len(paused.config.pending_urls)
        # cooperative pause: at least one done, not all, remainder persisted
        self.assertGreaterEqual(processed, 1)
        self.assertGreaterEqual(pending, 1)
        self.assertEqual(processed + pending, 6)

        self.jm.resume_job(job.id)
        status = self._wait(job.id)
        self.assertEqual(status, JobStatus.COMPLETED)
        results = self.jm.get_job_results(job.id)
        self.assertEqual(len(results), 6)
        self.assertEqual(len({r.reel_url for r in results}), 6)  # no dupes
        reloaded = self.jm.get_job(job.id)
        self.assertEqual(reloaded.successful_items, 6)
        self.assertIn(AppEventKind.JOB_RESUMED, [e.kind for e in self.events])
        self.assertIn(AppEventKind.JOB_PAUSED, [e.kind for e in self.events])

    def test_stop_persists_partial_results(self):
        job = self.jm.create_job(URLS)
        self.jm.start_job(job.id)
        time.sleep(0.08)
        self.jm.stop_job(job.id)
        status = self._wait(job.id)
        self.assertEqual(status, JobStatus.STOPPED)
        reloaded = self.jm.get_job(job.id)
        self.assertLess(reloaded.processed_items, 6)
        self.assertGreater(reloaded.processed_items, 0)
        self.assertEqual(len(self.jm.get_job_results(job.id)),
                         reloaded.processed_items)
        self.assertIn(AppEventKind.JOB_STOPPED, [e.kind for e in self.events])

    def test_failure_marks_failed(self):
        self.jm._factory = make_factory(delay=0.01, raise_on_scrape=True)
        job = self.jm.create_job(URLS[:2])
        self.jm.start_job(job.id)
        status = self._wait(job.id)
        self.assertEqual(status, JobStatus.FAILED)
        self.assertIsNotNone(self.jm.get_job(job.id).error_summary)
        self.assertIn(AppEventKind.JOB_FAILED, [e.kind for e in self.events])

    def test_retry_creates_new_job(self):
        self.jm._factory = make_factory(delay=0.01, raise_on_scrape=True)
        job = self.jm.create_job(URLS[:2])
        self.jm.start_job(job.id)
        self._wait(job.id)
        new_job = self.jm.retry_job(job.id)
        self.assertNotEqual(new_job.id, job.id)
        self.assertEqual(new_job.status, JobStatus.CREATED)
        self.assertEqual(new_job.config.urls, job.config.urls)

    def _wait_until(self, job_id, target, timeout=20):
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = self.jm.get_job(job_id)
            if job is not None and job.status == target:
                self.jm.wait_for_job(job_id)
                return job.status
            time.sleep(0.02)
        self.jm.wait_for_job(job_id)
        return self.jm.get_job(job_id).status


class TestInvalidTransitions(JobManagerTestBase):
    def test_start_from_completed_raises(self):
        from jobs import IllegalTransitionError

        job = self.jm.create_job(URLS[:1])
        self.jm.start_job(job.id)
        self._wait(job.id)
        with self.assertRaises(IllegalTransitionError):
            self.jm.start_job(job.id)

    def test_pause_from_created_raises(self):
        from jobs import IllegalTransitionError

        job = self.jm.create_job(URLS[:1])
        with self.assertRaises(IllegalTransitionError):
            self.jm.pause_job(job.id)

    def test_resume_from_non_paused_raises(self):
        from jobs import IllegalTransitionError

        job = self.jm.create_job(URLS[:1])
        with self.assertRaises(IllegalTransitionError):
            self.jm.resume_job(job.id)

    def test_retry_from_created_raises(self):
        from jobs import IllegalTransitionError

        job = self.jm.create_job(URLS[:1])
        with self.assertRaises(IllegalTransitionError):
            self.jm.retry_job(job.id)


class TestPersistenceAcrossRestart(JobManagerTestBase):
    def test_job_survives_restart(self):
        job = self.jm.create_job(URLS)
        self.jm.start_job(job.id)
        self._wait(job.id)
        count_before = len(self.jm.get_job_results(job.id))
        self.jm.close()

        jm2 = JobManager(data_dir=self.tmp, db_name="test.db",
                         event_bus=ApplicationEventBus())
        reopened = jm2.get_job(job.id)
        self.assertEqual(reopened.status, JobStatus.COMPLETED)
        self.assertEqual(len(jm2.get_job_results(job.id)), count_before)
        self.assertEqual(jm2.list_jobs()[0].id, job.id)
        jm2.close()

    def test_running_job_marked_interrupted_on_restart(self):
        # Use a slow factory so the job is still RUNNING at "crash".
        self.jm._factory = make_factory(delay=5.0)
        job = self.jm.create_job(URLS[:2])
        self.jm.start_job(job.id)
        time.sleep(0.1)  # ensure it entered RUNNING
        # Simulate a crash: a brand new manager opens the same DB.
        jm2 = JobManager(data_dir=self.tmp, db_name="test.db",
                         event_bus=ApplicationEventBus())
        reopened = jm2.get_job(job.id)
        self.assertEqual(reopened.status, JobStatus.INTERRUPTED)
        jm2.close()
        self.jm.close()


if __name__ == "__main__":
    unittest.main()
