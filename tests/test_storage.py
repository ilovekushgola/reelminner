import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jobs import Job, JobConfig, JobStatus
from scraper import ReelData
from storage import JobStore, ResultStore, StorageError


class TestJobStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "reelminner.db")
        self.store = JobStore(self.db)

    def tearDown(self):
        self.store.close()
        # cleanup
        for f in os.listdir(self.tmp):
            try:
                os.remove(os.path.join(self.tmp, f))
            except OSError:
                pass
        os.rmdir(self.tmp)

    def _make_job(self, status=JobStatus.CREATED):
        j = Job(config=JobConfig(urls=["https://instagram.com/reel/a"]))
        if status != JobStatus.CREATED:
            j.transition_to(JobStatus.STARTING)
            if status != JobStatus.STARTING:
                j.transition_to(JobStatus.RUNNING)
                if status != JobStatus.RUNNING:
                    j.transition_to(status)
        return j

    def test_create_and_get(self):
        j = self._make_job()
        self.store.create_job(j)
        got = self.store.get_job(j.id)
        self.assertIsNotNone(got)
        self.assertEqual(got.id, j.id)
        self.assertEqual(got.status, JobStatus.CREATED)

    def test_update_persists_config(self):
        j = self._make_job()
        self.store.create_job(j)
        j.config.workers = 9
        j.config.pending_urls = ["https://instagram.com/reel/b"]
        j.transition_to(JobStatus.STARTING)
        self.store.update_job(j)
        got = self.store.get_job(j.id)
        self.assertEqual(got.config.workers, 9)
        self.assertEqual(got.config.pending_urls, ["https://instagram.com/reel/b"])
        self.assertEqual(got.status, JobStatus.STARTING)

    def test_list_jobs_ordered(self):
        for _ in range(3):
            self.store.create_job(self._make_job())
        jobs = self.store.list_jobs()
        self.assertEqual(len(jobs), 3)
        # newest first
        self.assertGreaterEqual(jobs[0].created_at, jobs[-1].created_at)

    def test_list_jobs_filter_by_status(self):
        self.store.create_job(self._make_job(JobStatus.COMPLETED))
        self.store.create_job(self._make_job(JobStatus.CREATED))
        completed = self.store.list_jobs(status=JobStatus.COMPLETED)
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0].status, JobStatus.COMPLETED)

    def test_settings_round_trip(self):
        self.store.set_setting("headless", True)
        self.store.set_setting("delay", 3.5)
        self.assertTrue(self.store.get_setting("headless"))
        self.assertEqual(self.store.get_setting("delay"), 3.5)
        self.assertEqual(self.store.get_setting("missing", "x"), "x")

    def test_recovery_marks_running_interrupted(self):
        # First store creates a RUNNING job, then closes.
        j = self._make_job(JobStatus.RUNNING)
        self.store.create_job(j)
        self.store.close()
        # Simulate an application restart on the same DB file.
        store2 = JobStore(self.db)
        reopened = store2.get_job(j.id)
        self.assertEqual(reopened.status, JobStatus.INTERRUPTED)
        store2.close()


class TestResultStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.results = ResultStore(self.tmp)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_append_and_load(self):
        self.results.append_result("job1", ReelData(reel_url="u1", status="ok"))
        self.results.append_result("job1", ReelData(reel_url="u2", status="ok"))
        loaded = self.results.load_results("job1")
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0].reel_url, "u1")
        self.assertEqual(self.results.count("job1"), 2)

    def test_write_overwrites(self):
        self.results.append_result("job2", ReelData(reel_url="u1"))
        self.results.write_results("job2", [ReelData(reel_url="x")])
        self.assertEqual(self.results.count("job2"), 1)
        self.assertEqual(self.results.load_results("job2")[0].reel_url, "x")

    def test_round_trip_fields(self):
        rd = ReelData(username="bob", reel_url="u3", likes="12", status="ok")
        self.results.append_result("job3", rd)
        loaded = self.results.load_results("job3")[0]
        self.assertEqual(loaded.username, "bob")
        self.assertEqual(loaded.likes, "12")

    def test_load_missing_returns_empty(self):
        self.assertEqual(self.results.load_results("nope"), [])


if __name__ == "__main__":
    unittest.main()
