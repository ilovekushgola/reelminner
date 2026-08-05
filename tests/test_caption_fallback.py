from parsers import parse_uploaded_at_from_html, parse_username_from_html

# Profile-less reel: no og:title, no article:published_time; caption is
# 'rohit_sharma_fan on August 5, 2026 ...' (real pattern from Task 8).
NO_TITLE_HTML = """<html><head>
<meta property="og:description" content="rohit_sharma_fan on August 5, 2026
Clutch finish in the chase! #IPL #cricket" />
</head><body></body></html>"""

# Same pattern but caption is the only meta at all.
ONLY_CAPTION_HTML = """<html><head>
<meta name="description" content="priya_vlogs on June 12, 2026
Morning routine, new city. #vlog" />
</head><body></body></html>"""


def test_username_from_caption_date_pattern():
    assert parse_username_from_html(NO_TITLE_HTML) == "rohit_sharma_fan"


def test_username_from_plain_description_meta():
    assert parse_username_from_html(ONLY_CAPTION_HTML) == "priya_vlogs"


def test_uploaded_at_from_caption_date():
    assert parse_uploaded_at_from_html(NO_TITLE_HTML) == "2026-08-05"
    assert parse_uploaded_at_from_html(ONLY_CAPTION_HTML) == "2026-06-12"


def test_existing_paths_untouched():
    # og:title path still wins
    assert parse_username_from_html(
        '<meta property="og:title" content="shubham_travels on Instagram" />'
    ) == "shubham_travels"
    # article:published_time still wins
    assert parse_uploaded_at_from_html(
        '<meta property="article:published_time" content="2026-07-30T14:22:11.000Z" />'
    ) == "2026-07-30T14:22:11.000Z"
