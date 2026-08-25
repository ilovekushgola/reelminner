import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app_events import ApplicationEventBus, AppEventKind
from storage import JobStore
from settings import SettingsService


class TestSettingsService(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "s.db")
        self.bus = ApplicationEventBus()
        self.events = []
        self.bus.subscribe(lambda e: self.events.append(e))
        self.store = JobStore(self.db)
        self.svc = SettingsService(self.store, self.bus)

    def tearDown(self):
        self.store.close()
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_defaults(self):
        s = self.svc.get()
        self.assertEqual(s.scraping.workers, 3)
        self.assertEqual(s.scraping.delay, 2.0)
        self.assertFalse(s.scraping.headless)
        self.assertTrue(s.scraping.profile_enrichment)
        self.assertEqual(s.export.default_format, "csv")
        self.assertEqual(s.mcp.transport, "stdio")
        self.assertEqual(s.general.default_page_size, 50)

    def test_persistence_across_reload(self):
        self.svc.update(scraping_workers=8, export_default_format="json")
        # Reload from the SAME store (no extra connection to close).
        svc2 = SettingsService(self.store, ApplicationEventBus())
        reloaded = svc2.get()
        self.assertEqual(reloaded.scraping.workers, 8)
        self.assertEqual(reloaded.export.default_format, "json")

    def test_validation_rejects_bad_workers(self):
        with self.assertRaises(ValueError):
            self.svc.update(scraping_workers=999)
        # unchanged
        self.assertEqual(self.svc.get().scraping.workers, 3)

    def test_validation_rejects_bad_format(self):
        with self.assertRaises(ValueError):
            self.svc.update(export_default_format="pdf")

    def test_validation_rejects_bad_delay(self):
        with self.assertRaises(ValueError):
            self.svc.update(scraping_delay=-1)

    def test_reset(self):
        self.svc.update(scraping_workers=10, scraping_headless=True)
        self.svc.reset()
        s = self.svc.get()
        self.assertEqual(s.scraping.workers, 3)
        self.assertFalse(s.scraping.headless)

    def test_update_emits_event(self):
        self.svc.update(scraping_workers=5)
        self.assertIn(AppEventKind.SETTINGS_UPDATED, [e.kind for e in self.events])

    def test_validate_method(self):
        bad = self.svc.get()
        bad.scraping.workers = 999
        errors = self.svc.validate(bad)
        self.assertTrue(any("workers" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
