from datetime import datetime, timezone

from parsers import (
    looks_like_handle,
    parse_uploaded_at_from_html,
    parse_username_from_html,
)

TITLE_WITH_AT = '<meta property="og:title" content="PULSAR 220 OFFICIAL™️ (@pulsar_220_official) on Instagram" />'
LIKES_PREFIX_CAPTION = (
    '<meta property="og:description" content="35 likes, 0 comments - '
    'pulsar_220_official on August 4, 2026: caption text here" />'
)
DISPLAY_TITLE = (
    '<meta property="og:title" content="PULSAR 220 OFFICIAL™️ on Instagram" />'
    '<meta property="og:description" content="35 likes, 0 comments - '
    'pulsar_220_official on August 4, 2026: caption text here" />'
)
OWNER_JSON = (
    '<script type="application/ld+json">{"owner": {"username": "bmw_x7_club"}, '
    '"taken_at_timestamp": 1775200000}</script>'
)


def test_at_handle_in_og_title_wins():
    assert parse_username_from_html(TITLE_WITH_AT) == "pulsar_220_official"


def test_handle_from_likes_prefix_caption():
    assert parse_username_from_html(LIKES_PREFIX_CAPTION) == "pulsar_220_official"


def test_display_name_title_falls_through_to_caption_handle():
    assert parse_username_from_html(DISPLAY_TITLE) == "pulsar_220_official"


def test_handle_from_owner_json():
    assert parse_username_from_html(OWNER_JSON) == "bmw_x7_club"


def test_taken_at_timestamp_fallback():
    assert parse_uploaded_at_from_html(OWNER_JSON) == datetime.fromtimestamp(
        1775200000, tz=timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_looks_like_handle():
    assert looks_like_handle("pulsar_220_official") is True
    assert looks_like_handle("shubham_travels") is True
    assert looks_like_handle("PULSAR 220 OFFICIAL™️") is False
    assert looks_like_handle("𝗨 𝗦 𝗧 𝗔 𝗗") is False
    assert looks_like_handle("a" * 40) is False
    assert looks_like_handle("") is False
