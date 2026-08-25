import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper import ReelData  # noqa: E402
from service import ScraperService  # noqa: E402


class TestScraperService(unittest.TestCase):
    def test_construction_and_proxies(self):
        svc = ScraperService(headless=True, workers=5, delay=1.0)
        self.assertTrue(svc.headless)
        self.assertEqual(svc.workers, 5)
        self.assertEqual(svc.delay, 1.0)
        # setters propagate to the underlying engine
        svc.workers = 2
        self.assertEqual(svc.workers, 2)
        svc.delay = 3.0
        self.assertEqual(svc.delay, 3.0)
        svc.headless = False
        self.assertFalse(svc.headless)

    def test_export_formats(self):
        rows = [ReelData(username="u", status="ok")]
        with tempfile.TemporaryDirectory() as td:
            svc = ScraperService()
            csv_p = pathlib.Path(td) / "out.csv"
            svc.export(rows, str(csv_p), "csv")
            self.assertTrue(csv_p.exists())
            json_p = pathlib.Path(td) / "out.json"
            svc.export(rows, str(json_p), "json")
            self.assertTrue(json_p.exists())


if __name__ == "__main__":
    unittest.main()
