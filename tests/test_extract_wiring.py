from pathlib import Path

from scraper import InstagramReelScraper

FIX = Path(__file__).resolve().parent / "fixtures"


class StubPage:
    """Minimal fake Page: returns fixture HTML for content(); nothing else."""

    def __init__(self, html: str):
        self._html = html
        self.url = "https://www.instagram.com/reel/Dbnod4jJ-W9/"

    def content(self):
        return self._html

    def evaluate(self, *_a, **_k):
        return None

    def eval_on_selector(self, *_a, **_k):
        return ""


def make_scraper():
    return InstagramReelScraper(headless=True, workers=1, delay=0)


def test_extract_full_fixture():
    s = make_scraper()
    d = s._extract(StubPage((FIX / "reel_full.html").read_text(encoding="utf-8")))
    assert d.username == "shubham_travels"
    assert d.music_title == 'Dilbar (From "Satyameva Jayate")'
    assert d.music_artist == "Neha Kakkar"
    assert d.is_original_audio is False
    assert d.likes == "1234"
    assert d.caption == "Sunset vibes at the beach"


def test_extract_original_audio_fixture():
    s = make_scraper()
    d = s._extract(StubPage((FIX / "reel_original_audio.html").read_text(encoding="utf-8")))
    assert d.username == "priya_vlogs"
    assert d.music_title == "Original audio"
    assert d.is_original_audio is True


def test_reel_data_has_new_csv_column():
    from scraper import ReelData
    cols = ReelData.csv_columns()
    assert cols[-1] == "is_original_audio"
    d = ReelData()
    assert d.is_original_audio is False
    assert d.to_dict()["is_original_audio"] is False
