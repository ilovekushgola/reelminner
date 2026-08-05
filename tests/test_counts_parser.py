from pathlib import Path

from parsers import parse_counts_from_html

FIX = Path(__file__).resolve().parent / "fixtures"


def test_counts_full():
    html = (FIX / "reel_full.html").read_text(encoding="utf-8")
    c = parse_counts_from_html(html)
    assert c == {"likes": "1234", "comments": "56", "plays": "78901"}


def test_counts_without_play_count():
    html = (FIX / "reel_original_audio.html").read_text(encoding="utf-8")
    c = parse_counts_from_html(html)
    assert c["likes"] == "99"
    assert c["comments"] == "3"
    assert c["plays"] == "1200"


def test_counts_empty_when_absent():
    html = (FIX / "reel_login_wall.html").read_text(encoding="utf-8")
    assert parse_counts_from_html(html) == {"likes": "", "comments": "", "plays": ""}
