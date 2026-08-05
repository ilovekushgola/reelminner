from pathlib import Path

from parsers import REEL_URL_RE

CORPUS = Path(__file__).resolve().parent / "corpus.txt"


def test_corpus_has_12_urls():
    urls = [l.strip() for l in CORPUS.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(urls) == 12


def test_corpus_urls_all_match_reel_pattern():
    urls = [l.strip() for l in CORPUS.read_text(encoding="utf-8").splitlines() if l.strip()]
    for u in urls:
        assert REEL_URL_RE.search(u), f"not a reel URL: {u}"
