from pathlib import Path

from parsers import (
    parse_caption_from_html,
    parse_uploaded_at_from_html,
    parse_username_from_html,
    parse_video_url_from_html,
)

FIX = Path(__file__).resolve().parent / "fixtures"


def test_username_from_og_title():
    html = (FIX / "reel_full.html").read_text(encoding="utf-8")
    assert parse_username_from_html(html) == "shubham_travels"


def test_username_with_reversed_meta_attr_order():
    html = (FIX / "reel_stress_music.html").read_text(encoding="utf-8")
    assert parse_username_from_html(html) == "DJ_remix"


def test_caption_strips_username_prefix():
    html = (FIX / "reel_full.html").read_text(encoding="utf-8")
    assert parse_caption_from_html(html) == "Sunset vibes at the beach"


def test_uploaded_at():
    html = (FIX / "reel_full.html").read_text(encoding="utf-8")
    assert parse_uploaded_at_from_html(html) == "2026-07-30T14:22:11.000Z"


def test_video_url_from_og_video():
    html = (FIX / "reel_full.html").read_text(encoding="utf-8")
    assert parse_video_url_from_html(html) == \
        "https://scontent.cdninstagram.com/v/t50.2886-16/100000000_12345.mp4"


def test_empty_when_missing():
    html = (FIX / "reel_login_wall.html").read_text(encoding="utf-8")
    assert parse_username_from_html(html) == ""
    assert parse_caption_from_html(html) == ""
    assert parse_uploaded_at_from_html(html) == ""
    assert parse_video_url_from_html(html) == ""
