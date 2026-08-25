import logging
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from events import (  # noqa: E402
    EventKind,
    EventSink,
    ScraperEvent,
    StructuredLogger,
    configure_logging,
)


class TestEvents(unittest.TestCase):
    def test_event_kind_values(self):
        self.assertEqual(EventKind.ROW.value, "row")
        self.assertEqual(EventKind.JOB_START.value, "job_start")
        self.assertEqual(EventKind.JOB_DONE.value, "job_done")

    def test_event_to_dict(self):
        e = ScraperEvent(EventKind.PROGRESS, {"done": 1, "total": 2})
        d = e.to_dict()
        self.assertEqual(d["kind"], "progress")
        self.assertEqual(d["payload"], {"done": 1, "total": 2})

    def test_event_sink_protocol(self):
        captured = []

        class Sink:
            def emit(self, event):
                captured.append(event)

        sink = Sink()
        sink.emit(ScraperEvent(EventKind.LOG, {"msg": "hi"}))
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0].kind, EventKind.LOG)

    def test_configure_logging_idempotent(self):
        configure_logging(level=logging.INFO, console=True)
        before = len(logging.getLogger("reelminner").handlers)
        # calling again must NOT attach duplicate handlers
        configure_logging(level=logging.DEBUG, console=True)
        after = len(logging.getLogger("reelminner").handlers)
        self.assertEqual(before, after)

    def test_structured_logger(self):
        logger = StructuredLogger("reelminner.test")
        logger.info("hello", job="x")  # must not raise


if __name__ == "__main__":
    unittest.main()
