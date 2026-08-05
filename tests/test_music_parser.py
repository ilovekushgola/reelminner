from pathlib import Path

from parsers import parse_music_from_html

FIX = Path(__file__).resolve().parent / "fixtures"


def test_licensed_music_full():
    html = (FIX / "reel_full.html").read_text(encoding="utf-8")
    m = parse_music_from_html(html)
    assert m["title"] == 'Dilbar (From "Satyameva Jayate")'
    assert m["artist"] == "Neha Kakkar"
    assert m["original"] is False
    assert m["audio_page_url"] == "https://www.instagram.com/reels/audio/2949486874309131/"


def test_braces_inside_title_do_not_break_parser():
    html = (FIX / "reel_stress_music.html").read_text(encoding="utf-8")
    m = parse_music_from_html(html)
    assert m["title"] == "Party Mix {Official} 2026"
    assert m["artist"] == "DJ Remix"


def test_original_audio_detected():
    html = (FIX / "reel_original_audio.html").read_text(encoding="utf-8")
    m = parse_music_from_html(html)
    assert m["original"] is True
    assert m["title"] == "Original audio"
    assert m["artist"] == ""


def test_no_music_info_returns_empty():
    html = (FIX / "reel_login_wall.html").read_text(encoding="utf-8")
    m = parse_music_from_html(html)
    assert m == {"title": "", "artist": "", "original": False, "audio_page_url": ""}
