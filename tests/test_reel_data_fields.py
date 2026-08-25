import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper import ReelData

NEW_FIELDS = [
    "scrape_ts",
    "reel_id",
    "profile_url",
    "music_id",
    "thumbnail",
    "is_verified",
    "full_name",
    "bio",
    "reels_count",
]


class TestReelDataFields(unittest.TestCase):
    def test_new_fields_defaults(self):
        d = ReelData()
        for f in NEW_FIELDS:
            with self.subTest(f):
                self.assertIn(f, d.to_dict())
        self.assertFalse(d.is_verified)
        self.assertEqual(d.full_name, "")
        self.assertEqual(d.scrape_ts, "")

    def test_in_csv_columns(self):
        cols = ReelData.csv_columns()
        for f in NEW_FIELDS:
            with self.subTest(f):
                self.assertIn(f, cols)

    def test_is_original_audio_still_present(self):
        self.assertIn("is_original_audio", ReelData.csv_columns())

    def test_populated(self):
        d = ReelData(username="natgeo", reel_id="ABC", is_verified=True, full_name="Nat Geo")
        self.assertEqual(d.reel_id, "ABC")
        self.assertTrue(d.is_verified)
        self.assertEqual(d.full_name, "Nat Geo")


if __name__ == "__main__":
    unittest.main()
