import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jobs import (
    IllegalTransitionError,
    Job,
    JobConfig,
    JobStatus,
)


class TestJobStatus(unittest.TestCase):
    def test_terminal_states(self):
        for s in (JobStatus.COMPLETED, JobStatus.FAILED,
                  JobStatus.STOPPED, JobStatus.INTERRUPTED):
            self.assertTrue(s in JobStatus.terminal_states())
        self.assertFalse(JobStatus.RUNNING in JobStatus.terminal_states())

    def test_is_terminal(self):
        j = Job()
        self.assertFalse(j.is_terminal())
        j.transition_to(JobStatus.STARTING)
        j.transition_to(JobStatus.RUNNING)
        j.transition_to(JobStatus.COMPLETED)
        self.assertTrue(j.is_terminal())


class TestTransitions(unittest.TestCase):
    def test_valid_chain(self):
        j = Job()
        j.transition_to(JobStatus.QUEUED)
        j.transition_to(JobStatus.STARTING)
        j.transition_to(JobStatus.RUNNING)
        j.transition_to(JobStatus.PAUSED)
        j.transition_to(JobStatus.RUNNING)
        j.transition_to(JobStatus.COMPLETED)
        self.assertEqual(j.status, JobStatus.COMPLETED)

    def test_illegal_transition_raises(self):
        j = Job()
        with self.assertRaises(IllegalTransitionError):
            j.transition_to(JobStatus.COMPLETED)  # CREATED -> COMPLETED
        with self.assertRaises(IllegalTransitionError):
            j.transition_to(JobStatus.RUNNING)    # CREATED -> RUNNING
        j.transition_to(JobStatus.STARTING)
        j.transition_to(JobStatus.RUNNING)
        with self.assertRaises(IllegalTransitionError):
            j.transition_to(JobStatus.QUEUED)     # RUNNING -> QUEUED

    def test_completed_cannot_move(self):
        j = Job()
        j.transition_to(JobStatus.STARTING)
        j.transition_to(JobStatus.RUNNING)
        j.transition_to(JobStatus.COMPLETED)
        with self.assertRaises(IllegalTransitionError):
            j.transition_to(JobStatus.STARTING)

    def test_timestamps_set_on_transition(self):
        j = Job()
        self.assertIsNone(j.started_at)
        self.assertIsNone(j.completed_at)
        j.transition_to(JobStatus.STARTING)
        j.transition_to(JobStatus.RUNNING)
        self.assertIsNotNone(j.started_at)
        self.assertIsNone(j.completed_at)
        j.transition_to(JobStatus.COMPLETED)
        self.assertIsNotNone(j.completed_at)


class TestStats(unittest.TestCase):
    def test_record_result_categorises(self):
        j = Job()
        for _ in range(3):
            j.record_result("ok")
        j.record_result("error: structure_change")
        j.record_result("session_expired")
        j.record_result("rate_limited")
        j.record_result("timeout")
        self.assertEqual(j.successful_items, 3)
        self.assertEqual(j.failed_items, 1)        # timeout
        self.assertEqual(j.blocked_items, 2)       # structure_change + expired
        self.assertEqual(j.rate_limited_items, 1)
        self.assertEqual(j.processed_items, 7)

    def test_reset_stats(self):
        j = Job()
        j.record_result("ok")
        j.reset_stats()
        self.assertEqual(j.processed_items, 0)
        self.assertEqual(j.successful_items, 0)


class TestConfigSerialization(unittest.TestCase):
    def test_json_round_trip(self):
        cfg = JobConfig(
            urls=["https://instagram.com/reel/a"],
            workers=5,
            delay=1.5,
            headless=True,
            with_profiles=False,
            pending_urls=["https://instagram.com/reel/b"],
        )
        text = cfg.to_json()
        back = JobConfig.from_json(text)
        self.assertEqual(back.urls, cfg.urls)
        self.assertEqual(back.workers, 5)
        self.assertEqual(back.delay, 1.5)
        self.assertTrue(back.headless)
        self.assertFalse(back.with_profiles)
        self.assertEqual(back.pending_urls, cfg.pending_urls)


class TestJobDbRoundTrip(unittest.TestCase):
    def test_row_round_trip(self):
        j = Job(config=JobConfig(urls=["https://instagram.com/reel/a"]))
        j.transition_to(JobStatus.STARTING)
        j.transition_to(JobStatus.RUNNING)
        j.record_result("ok")
        j.result_location = "/tmp/x.jsonl"
        row = j.to_db_row()
        restored = Job.from_db_row(row)
        self.assertEqual(restored.id, j.id)
        self.assertEqual(restored.status, JobStatus.RUNNING)
        self.assertEqual(restored.config.urls, j.config.urls)
        self.assertEqual(restored.successful_items, 1)
        self.assertEqual(restored.result_location, "/tmp/x.jsonl")


if __name__ == "__main__":
    unittest.main()
