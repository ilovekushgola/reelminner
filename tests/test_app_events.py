import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from events import EventKind, ScraperEvent
from app_events import (
    ApplicationEvent,
    ApplicationEventBus,
    AppEventKind,
)


class TestApplicationEventBus(unittest.TestCase):
    def setUp(self):
        self.bus = ApplicationEventBus()
        self.seen = []
        self.bus.subscribe(lambda e: self.seen.append(e))

    def test_engine_progress_translated_with_job_context(self):
        self.bus.set_active_job("job-42")
        self.bus.emit(ScraperEvent(EventKind.PROGRESS, {"done": 1, "total": 5}))
        self.assertEqual(len(self.seen), 1)
        ev = self.seen[0]
        self.assertIsInstance(ev, ApplicationEvent)
        self.assertEqual(ev.kind, AppEventKind.JOB_PROGRESS)
        self.assertEqual(ev.job_id, "job-42")
        self.assertEqual(ev.payload["done"], 1)

    def test_row_event_translated(self):
        self.bus.set_active_job("job-1")
        self.bus.emit(ScraperEvent(EventKind.ROW, {"reel_url": "u"}))
        self.assertEqual(self.seen[0].kind, AppEventKind.ROW_PROCESSED)

    def test_job_start_and_done_ignored(self):
        self.bus.emit(ScraperEvent(EventKind.JOB_START, {}))
        self.bus.emit(ScraperEvent(EventKind.JOB_DONE, {}))
        self.assertEqual(self.seen, [])

    def test_log_severity_mapping(self):
        self.bus.emit(ScraperEvent(EventKind.LOG, {"message": "[x] boom"}))
        self.assertEqual(self.seen[-1].kind, AppEventKind.ERROR)
        self.seen.clear()
        self.bus.emit(ScraperEvent(EventKind.LOG, {"message": "WARN: slow"}))
        self.assertEqual(self.seen[-1].kind, AppEventKind.WARNING)
        self.seen.clear()
        self.bus.emit(ScraperEvent(EventKind.LOG, {"message": "plain info"}))
        self.assertEqual(self.seen[-1].kind, AppEventKind.LOG)

    def test_emit_app_lifecycle(self):
        self.bus.emit_app(AppEventKind.JOB_CREATED, "job-9", {"urls": ["u"]})
        ev = self.seen[-1]
        self.assertEqual(ev.kind, AppEventKind.JOB_CREATED)
        self.assertEqual(ev.job_id, "job-9")

    def test_subscriber_exception_does_not_break_pipeline(self):
        bad = []
        self.bus.subscribe(lambda e: 1 / 0)
        self.bus.subscribe(lambda e: bad.append(e))
        self.bus.emit_app(AppEventKind.JOB_STARTED, "job-x", {})
        self.assertEqual(len(bad), 1)


if __name__ == "__main__":
    unittest.main()
