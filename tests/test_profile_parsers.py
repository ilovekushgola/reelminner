import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers import (
    parse_music_id_from_html,
    parse_profile_card_from_html,
    parse_reel_id_from_url,
    parse_thumbnail_from_html,
)

REEL_HTML = """
<html><head>
<meta property="og:image" content="https://scontent.cdninstagram.com/thumb.jpg" />
<script>window.__additionalData={"music_asset_info":{"audio_asset_id":"2949486874309131","audio_cluster_id":"2949486874309131"}}</script>
</head><body></body></html>
"""

PROFILE_HTML = """
<html><head>
<meta property="og:title" content="National Geographic • Instagram photos and videos" />
<meta name="description" content="285M Followers, 53 Following, 124K Posts - Stories about our world, nature, and science." />
<script>{"is_verified":true}</script>
</head><body></body></html>
"""


class TestReelId(unittest.TestCase):
    def test_from_reel(self):
        self.assertEqual(
            parse_reel_id_from_url("https://www.instagram.com/reel/Dbnod4jJ-W9/"),
            "Dbnod4jJ-W9",
        )

    def test_from_reels(self):
        self.assertEqual(
            parse_reel_id_from_url("https://instagram.com/reels/ABC123/"), "ABC123"
        )

    def test_from_short(self):
        self.assertEqual(parse_reel_id_from_url("https://instagram.com/p/XyZ/"), "XyZ")

    def test_missing(self):
        self.assertEqual(parse_reel_id_from_url("https://example.com/"), "")
        self.assertEqual(parse_reel_id_from_url(""), "")


class TestThumbnail(unittest.TestCase):
    def test_extracted(self):
        self.assertEqual(
            parse_thumbnail_from_html(REEL_HTML),
            "https://scontent.cdninstagram.com/thumb.jpg",
        )

    def test_missing(self):
        self.assertEqual(parse_thumbnail_from_html("<html></html>"), "")


class TestMusicId(unittest.TestCase):
    def test_extracted(self):
        self.assertEqual(parse_music_id_from_html(REEL_HTML), "2949486874309131")

    def test_missing(self):
        self.assertEqual(parse_music_id_from_html("<html></html>"), "")


class TestProfileCard(unittest.TestCase):
    def test_extracted(self):
        card = parse_profile_card_from_html(PROFILE_HTML)
        self.assertEqual(card["full_name"], "National Geographic")
        self.assertEqual(card["reels_count"], "124K")
        self.assertTrue(card["is_verified"])
        self.assertIn("Stories about our world", card["bio"])

    def test_empty(self):
        card = parse_profile_card_from_html("")
        self.assertEqual(card["full_name"], "")
        self.assertFalse(card["is_verified"])
        self.assertEqual(card["reels_count"], "")


if __name__ == "__main__":
    unittest.main()
