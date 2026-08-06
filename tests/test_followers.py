from parsers import parse_followers_from_html
from scraper import ReelData

DESC = '<meta property="og:description" content="12.3K Followers, 10 Following, 200 Posts" />'
EDGE_JSON = '<script>{"edge_followed_by":{"count":123456}}</script>'
GENERIC_JSON = '<script>{"followers":999}</script>'
EMPTY = "<html></html>"


def test_followers_from_og_description():
    assert parse_followers_from_html(DESC) == "12.3K"


def test_followers_from_edge_followed_by():
    assert parse_followers_from_html(EDGE_JSON) == "123456"


def test_followers_from_generic_key():
    assert parse_followers_from_html(GENERIC_JSON) == "999"


def test_followers_empty():
    assert parse_followers_from_html(EMPTY) == ""


def test_reel_data_has_followers_column():
    cols = ReelData.csv_columns()
    assert cols[cols.index("username") + 1] == "followers"
    assert ReelData().followers == ""
    assert ReelData().to_dict()["followers"] == ""
