from parsers import normalize_reel_url

def test_full_url_passthrough():
    assert normalize_reel_url("https://www.instagram.com/reel/Dbnod4jJ-W9/") == \
        "https://www.instagram.com/reel/Dbnod4jJ-W9/"

def test_missing_scheme_gets_prefixed():
    assert normalize_reel_url("instagram.com/reels/DbprVwagDXC/") == \
        "https://www.instagram.com/reels/DbprVwagDXC/"

def test_query_string_stripped():
    assert normalize_reel_url("https://www.instagram.com/reel/ABC?igsh=xyz") == \
        "https://www.instagram.com/reel/ABC/"

def test_reels_and_p_kinds_allowed():
    assert normalize_reel_url("https://www.instagram.com/reels/DbpHZ1RzbJu/") == \
        "https://www.instagram.com/reels/DbpHZ1RzbJu/"
    assert normalize_reel_url("https://www.instagram.com/p/DboHwadBl5k/") == \
        "https://www.instagram.com/p/DboHwadBl5k/"

def test_non_reel_url_returns_none():
    assert normalize_reel_url("https://twitter.com/foo") is None
    assert normalize_reel_url("https://www.instagram.com/explore/") is None

def test_blank_returns_none():
    assert normalize_reel_url("") is None
    assert normalize_reel_url("   ") is None
