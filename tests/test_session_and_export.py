import json
from pathlib import Path

import pytest

from scraper import InstagramReelScraper, ReelData, export_excel, export_json, write_csv

TMP = Path(__file__).resolve().parent / "_tmp"
TMP.mkdir(exist_ok=True)

EDITTHISCOOKIE = [
    {"domain": ".instagram.com", "name": "sessionid", "value": "abc123",
     "path": "/", "expirationDate": 1817496972, "httpOnly": True,
     "secure": True, "sameSite": None},
    {"domain": ".instagram.com", "name": "csrftoken", "value": "tok",
     "path": "/", "expirationDate": -1, "httpOnly": False,
     "secure": True, "sameSite": "lax"},
]


@pytest.fixture()
def scraper(tmp_path):
    return InstagramReelScraper(state_file=tmp_path / "state.json")


def test_import_editthiscookie_format(scraper):
    f = TMP / "etc.json"
    f.write_text(json.dumps(EDITTHISCOOKIE), encoding="utf-8")
    assert scraper.save_cookies_from_file(f) is True
    assert scraper.has_session() is True
    state = json.loads(scraper.state_file.read_text(encoding="utf-8"))
    assert len(state["cookies"]) == 2
    assert state["cookies"][0]["domain"] == ".instagram.com"
    # null sameSite must become Lax, not None
    assert state["cookies"][0]["sameSite"] == "Lax"
    assert state["cookies"][1]["sameSite"] == "Lax"


def test_import_playwright_format(scraper):
    f = TMP / "pw.json"
    f.write_text(
        json.dumps({"cookies": [{"name": "sessionid", "value": "x", "domain": ".instagram.com",
                                 "path": "/", "expires": -1, "httpOnly": True,
                                 "secure": True, "sameSite": "Lax"}], "origins": []}),
        encoding="utf-8",
    )
    assert scraper.save_cookies_from_file(f) is True
    assert scraper.has_session() is True


def test_expired_sessionid_detected(scraper):
    f = TMP / "expired.json"
    f.write_text(
        json.dumps({"cookies": [{"name": "sessionid", "value": "x", "domain": ".instagram.com",
                                 "path": "/", "expires": 100, "httpOnly": True,
                                 "secure": True, "sameSite": "Lax"}], "origins": []}),
        encoding="utf-8",
    )
    scraper.save_cookies_from_file(f)
    assert scraper.has_session() is False


def test_bad_format_rejected(scraper):
    f = TMP / "bad.json"
    f.write_text(json.dumps({"foo": 1}), encoding="utf-8")
    assert scraper.save_cookies_from_file(f) is False


def test_clear_session(scraper):
    f = TMP / "ok.json"
    f.write_text(json.dumps({"cookies": [{"name": "sessionid", "value": "x",
                                          "domain": ".instagram.com", "path": "/",
                                          "expires": -1, "httpOnly": True,
                                          "secure": True, "sameSite": "Lax"}],
                             "origins": []}), encoding="utf-8")
    scraper.save_cookies_from_file(f)
    scraper.clear_session()
    assert scraper.has_session() is False


def test_csv_roundtrip_includes_new_column(tmp_path):
    d = ReelData(username="u", reel_url="https://www.instagram.com/reel/A/",
                 music_title="t", is_original_audio=True)
    out = tmp_path / "r.csv"
    write_csv([d], out)
    lines = out.read_text(encoding="utf-8-sig").splitlines()
    assert lines[0].split(",")[-1] == "is_original_audio"
    assert "True" in lines[1]


def test_json_export(tmp_path):
    d = ReelData(username="u")
    out = tmp_path / "r.json"
    export_json([d], out)
    assert json.loads(out.read_text(encoding="utf-8"))[0]["username"] == "u"


def test_excel_export(tmp_path):
    d = ReelData(username="u", music_title="t")
    out = tmp_path / "r.xlsx"
    export_excel([d], out)
    assert out.exists() and out.stat().st_size > 0
