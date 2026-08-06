# E2E Test-Fix-Improve Loop for Instagram Reel Scraper — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a repeatable end-to-end test → fix → improve loop that runs the scraper against a fixed corpus of 12 real reel URLs using the user's injected session, measures data-quality gates (username/music/likes fill rates, failure reasons), drives fixes for discovered gaps, and re-measures until the gates pass.

**Architecture:** Two layers. (1) A `pytest` unit layer that never touches the network: pure HTML/URL parsing helpers are extracted from `scraper.py` into a new `parsers.py` module and tested against fixture HTML that mirrors what Instagram actually serves. (2) An integration harness `run_qa.py` that executes the REAL engine (Playwright, visible browsers, user session) over the 12-URL corpus with throttling-safe settings, writes `qa_report.json` + CSV, prints a metrics table, and enforces PASS/FAIL gates via exit code. The "fix" tasks target the failure modes the first run surfaces (session walls, timeouts, missing music); the "improve" tasks add backoff, retry, and honest music metrics (`is_original_audio`). The loop closes with a re-run and a before/after summary.

**Tech Stack:** Python 3.11, Playwright sync API (Chromium 1228), pytest 9, tkinter (existing GUI), openpyxl (existing export).

## Global Constraints

- Project root (all paths relative to it): `E:\Download\Code\AionUi\Work Directory\conversations\2026\08\06\aionrs-temp-500e1eff\instagram-reel-scraper`
- Corpus: the 12 reel URLs from the spec, verbatim, one per line in `tests/corpus.txt`.
- Session: `storage_state.json` with the user's cookies (already injected and verified as @ilovekushgola). `InstagramReelScraper.has_session()` must return True before any QA run.
- Browsers: full QA runs MUST be visible (`headless=False`). Headless is allowed only in `--quick` mode (1 URL). Rationale (learned 2026-08-06): rapid headless requests get throttled by Instagram (60s nav timeouts, blank pages).
- QA run settings: workers = 2, delay = 2.0s per worker (plus existing 0–1.5s jitter). Never exceed workers=4 / delay < 1.0s in QA runs.
- Gates (all must pass): engine crash-free; ok_rate ≥ 0.75; username fill ≥ 0.80; music fill ≥ 0.60 (licensed reels only, see Task 5 `is_original_audio`); zero `session_expired`; runtime ≤ 1800s.
- Every full QA run writes `results/qa/qa_report.json` and `results/qa/qa_results.csv`. `results/` and all `*.json`/`*.csv` are git-ignored (scraped metadata stays local — privacy).
- Unit tests never hit the network; live runs happen only via `run_qa.py` / the scraper CLI.
- Commit after every task. First commit initializes the repo (project is not yet a git repo).

---

### Task 0: Repo init, test scaffolding, corpus

**Files:**
- Create: `pytest.ini`
- Create: `requirements-dev.txt`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/corpus.txt`
- Create: `tests/fixtures/reel_full.html`
- Create: `tests/fixtures/reel_original_audio.html`
- Create: `tests/fixtures/reel_stress_music.html`
- Create: `tests/fixtures/reel_login_wall.html`

**Interfaces:**
- Consumes: nothing.
- Produces: `tests/corpus.txt` (12 URLs — used by run_qa.py in Task 7); `tests/conftest.py` (adds project root to `sys.path` so `import scraper` / `import parsers` work from any cwd); fixture HTML files (used by parser tests in Tasks 2–4).

- [ ] **Step 1: git init + baseline commit**

```powershell
cd "E:\Download\Code\AionUi\Work Directory\conversations\2026\08\06\aionrs-temp-500e1eff\instagram-reel-scraper"
git init
git add .gitignore gui.py scraper.py README.md requirements.txt
git commit -m "chore: baseline reel scraper (engine + GUI)"
```

Expected: repo created; commit succeeds. `storage_state.json` and `cookies_export.json` are NOT committed (ignored by `.gitignore`).

- [ ] **Step 2: Write `pytest.ini`**

```ini
[pytest]
testpaths = tests
addopts = -q
```

- [ ] **Step 3: Write `requirements-dev.txt`**

```
pytest>=9
```

- [ ] **Step 4: Write `tests/__init__.py`** (empty file)

- [ ] **Step 5: Write `tests/conftest.py`**

```python
"""Make project modules importable from any cwd."""
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
```

- [ ] **Step 6: Write `tests/corpus.txt`** (exactly these 12 lines)

```
https://www.instagram.com/reel/Dbnod4jJ-W9/
https://www.instagram.com/reel/DbprVwagDXC/
https://www.instagram.com/reel/DbmlR2BxRgk/
https://www.instagram.com/reel/Dbnn7iTu6hn/
https://www.instagram.com/reel/DblYoy8PKOV/
https://www.instagram.com/reel/DbpHZ1RzbJu/
https://www.instagram.com/reel/DboHwadBl5k/
https://www.instagram.com/reel/DbpvQ1fR_HA/
https://www.instagram.com/reel/Dbps6koultg/
https://www.instagram.com/reel/DbnSVmwTjeV/
https://www.instagram.com/reel/Dbpt7UhzHIv/
https://www.instagram.com/reel/DbniOTOTi42/
```

- [ ] **Step 7: Write the four fixture files**

`tests/fixtures/reel_full.html` — every field present:

```html
<!DOCTYPE html>
<html>
<head>
<title>shubham_travels on Instagram</title>
<meta property="og:title" content="shubham_travels on Instagram: &quot;Sunset vibes at the beach&quot;" />
<meta name="description" content="shubham_travels (@shubham_travels) on Instagram: Sunset vibes at the beach" />
<meta property="og:description" content="shubham_travels on Instagram: Sunset vibes at the beach" />
<meta property="og:video" content="https://scontent.cdninstagram.com/v/t50.2886-16/100000000_12345.mp4" />
<meta property="article:published_time" content="2026-07-30T14:22:11.000Z" />
</head>
<body>
<article>
  <header><a href="/shubham_travels/"><span>shubham_travels</span></a></header>
  <a href="/reels/audio/2949486874309131/">Use this sound</a>
</article>
<script type="application/json">{"config":{"clip":{"music_asset_info":{"audio_asset_id":"2949486874309131","title":"Dilbar (From \"Satyameva Jayate\")","display_artist":"Neha Kakkar","music_canonical_url":"/reels/audio/2949486874309131/"},"like_count":1234,"comment_count":56,"play_count":78901}}}</script>
</body>
</html>
```

`tests/fixtures/reel_original_audio.html` — no licensed music (the "Original audio" case):

```html
<!DOCTYPE html>
<html>
<head>
<meta property="og:title" content="priya_vlogs on Instagram: &quot;Morning run&quot;" />
<meta name="description" content="priya_vlogs (@priya_vlogs) on Instagram: Morning run" />
<meta property="og:description" content="priya_vlogs on Instagram: Morning run" />
</head>
<body>
<article>
  <header><a href="/priya_vlogs/"><span>priya_vlogs</span></a></header>
  <a href="/reels/audio/123456789/">Use this sound</a>
  <span>Original audio</span>
</article>
<script type="application/json">{"config":{"clip":{"like_count":99,"comment_count":3,"play_count":1200}}}</script>
</body>
</html>
```

`tests/fixtures/reel_stress_music.html` — title contains braces AND the attribute order of og:title is reversed (content before property) to prove parser robustness:

```html
<!DOCTYPE html>
<html>
<head>
<meta content="DJ_remix on Instagram: &quot;Night drive&quot;" property="og:title" />
</head>
<body>
<script type="application/json">{"x":{"music_asset_info":{"title":"Party Mix {Official} 2026","display_artist":"DJ Remix"},"play_count":42}}</script>
</body>
</html>
```

`tests/fixtures/reel_login_wall.html` — the login-wall markup the engine must detect:

```html
<!DOCTYPE html>
<html>
<body>
<form method="post" action="/accounts/login/">
  <input name="username" type="text" />
  <input name="password" type="password" />
</form>
</body>
</html>
```

- [ ] **Step 8: Write the corpus validity test**

`tests/test_corpus.py`:

```python
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
```

- [ ] **Step 9: Run the test to verify it fails (parsers.py does not exist yet)**

Run: `python -m pytest tests/test_corpus.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'parsers'` — this is the red state for Task 1.

- [ ] **Step 10: Commit**

```powershell
git add pytest.ini requirements-dev.txt tests/
git commit -m "test: corpus + fixtures + pytest scaffolding"
```

---

### Task 1: Extract `parsers.py` — URL normalization

**Files:**
- Create: `parsers.py`
- Modify: `scraper.py` (CLI `main()` URL loop; keep `REEL_URL_RE` name exported for gui.py)
- Modify: `gui.py` (`_collect_urls` method + import line)
- Test: `tests/test_normalize_url.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `parsers.REEL_URL_RE` (regex), `parsers.normalize_reel_url(raw: str) -> str | None`. `scraper` re-exports `REEL_URL_RE` so `from scraper import REEL_URL_RE` in gui.py keeps working during the transition.

- [ ] **Step 1: Write the failing test**

`tests/test_normalize_url.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_normalize_url.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'parsers'`.

- [ ] **Step 3: Create `parsers.py`**

```python
"""Pure parsing helpers for the Instagram reel scraper.

Everything here is a function of the HTML string (or a URL string) alone —
no browser, no network. This keeps the extraction logic unit-testable.
"""

from __future__ import annotations

import html as htmlmod
import json
import re

REEL_URL_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/(reel|reels|p)/([\w-]+)", re.IGNORECASE
)


def normalize_reel_url(raw: str) -> str | None:
    """Normalize a user-supplied URL into a canonical reel URL, or None."""
    if not raw:
        return None
    u = raw.strip()
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    m = REEL_URL_RE.search(u)
    if not m:
        return None
    kind = m.group(1).lower()
    return f"https://www.instagram.com/{kind}/{m.group(2)}/"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_normalize_url.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Re-export from `scraper.py` and refactor the CLI**

Add to `scraper.py` imports (top of file, replacing the inline `REEL_URL_RE` definition):

```python
from parsers import REEL_URL_RE, normalize_reel_url  # noqa: F401  (re-exported for gui.py)
```

Then delete the old `REEL_URL_RE = re.compile(...)` line from `scraper.py` (it is now imported).

Refactor the URL-collection block in `scraper.py` `main()` (currently the `# normalize / validate` block) to:

```python
    normalized = []
    for u in urls:
        norm = normalize_reel_url(u)
        if norm:
            normalized.append(norm)
        else:
            print(f"[!] Skipped (not a reel URL): {u}")
    urls = normalized
```

- [ ] **Step 6: Refactor `gui.py` `_collect_urls`**

Change the import in `gui.py` from:

```python
from scraper import (
    DEFAULT_STATE_FILE,
    REEL_URL_RE,
    InstagramReelScraper,
    export_excel,
    export_json,
    write_csv,
)
```

to:

```python
from scraper import (
    DEFAULT_STATE_FILE,
    InstagramReelScraper,
    export_excel,
    export_json,
    normalize_reel_url,
    write_csv,
)
```

Replace the `_collect_urls` method body in `gui.py` with:

```python
    def _collect_urls(self) -> list:
        raw = self.urls_text.get("1.0", tk.END)
        seen, out = set(), []
        for line in raw.splitlines():
            norm = normalize_reel_url(line)
            if norm:
                if norm not in seen:
                    seen.add(norm)
                    out.append(norm)
            else:
                self._append_log(f"  * skipped (not a reel URL): {line.strip()}")
        return out
```

- [ ] **Step 7: Run full unit suite + compile checks**

Run: `python -m pytest tests/ -v`
Expected: PASS (7 tests: 1 corpus + 6 normalize).

Run: `python -m py_compile scraper.py gui.py parsers.py`
Expected: no output, exit code 0.

- [ ] **Step 8: Commit**

```powershell
git add parsers.py scraper.py gui.py tests/test_normalize_url.py
git commit -m "refactor: extract URL normalization into parsers.py (unit-tested)"
```

---

### Task 2: Meta parsers — username, caption, upload date, video URL

**Files:**
- Create: `tests/test_meta_parsers.py`
- Modify: `parsers.py`

**Interfaces:**
- Consumes: `tests/fixtures/reel_full.html`, `reel_stress_music.html`, `reel_original_audio.html`.
- Produces: `parsers.meta_content(page_html: str, attr: str, value: str) -> str` (returns html-unescaped content of the matching meta tag, `""` if absent); `parsers.parse_username_from_html(page_html: str) -> str`; `parsers.parse_caption_from_html(page_html: str) -> str`; `parsers.parse_uploaded_at_from_html(page_html: str) -> str`; `parsers.parse_video_url_from_html(page_html: str) -> str`. Task 5 wires these into `_extract`.

- [ ] **Step 1: Write the failing tests**

`tests/test_meta_parsers.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_meta_parsers.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_username_from_html'`.

- [ ] **Step 3: Implement the parsers in `parsers.py`**

Append to `parsers.py`:

```python
_META_TAG_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(r'([\w:-]+)\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)


def _tag_attrs(tag_html: str) -> dict:
    return {k.lower(): htmlmod.unescape(v) for k, v in _ATTR_RE.findall(tag_html)}


def meta_content(page_html: str, attr: str, value: str) -> str:
    """Content of the first <meta> whose `attr` equals `value` (order-proof)."""
    for tag in _META_TAG_RE.findall(page_html):
        attrs = _tag_attrs(tag)
        if attrs.get(attr.lower(), "").lower() == value.lower():
            return attrs.get("content", "")
    return ""


def parse_username_from_html(page_html: str) -> str:
    og_title = meta_content(page_html, "property", "og:title")
    m = re.match(r"^\s*([^|]+?)\s+on Instagram", og_title)
    if m:
        return m.group(1).strip()
    desc = meta_content(page_html, "name", "description")
    m = re.match(r"^\s*([\w.]+)\s*\(@", desc)
    if m:
        return m.group(1).strip()
    return ""


def parse_caption_from_html(page_html: str) -> str:
    desc = meta_content(page_html, "property", "og:description")
    desc = re.sub(r"^.*?on Instagram:\s*", "", desc, count=1)
    return desc.strip()[:500]


def parse_uploaded_at_from_html(page_html: str) -> str:
    v = meta_content(page_html, "property", "article:published_time")
    if v:
        return v
    m = re.search(r'"uploadDate"\s*:\s*"([^"]+)"', page_html)
    return m.group(1) if m else ""


def parse_video_url_from_html(page_html: str) -> str:
    for prop in ("og:video", "og:video:url"):
        v = meta_content(page_html, "property", prop)
        if v:
            return v
    m = re.search(r'"contentUrl"\s*:\s*"([^"]+)"', page_html)
    return m.group(1) if m else ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_meta_parsers.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```powershell
git add parsers.py tests/test_meta_parsers.py
git commit -m "feat: meta tag + username/caption/date/video parsers with tests"
```

---

### Task 3: Music parser — brace-matching JSON scan + original-audio flag

**Files:**
- Create: `tests/test_music_parser.py`
- Modify: `parsers.py`

**Interfaces:**
- Consumes: fixtures `reel_full.html`, `reel_original_audio.html`, `reel_stress_music.html`.
- Produces: `parsers._extract_json_object(page_html: str, key: str) -> dict | None` (brace-matching scanner, string/escape aware — unlike regex it survives `}` inside titles); `parsers.parse_music_from_html(page_html: str) -> dict` returning `{"title": str, "artist": str, "original": bool, "audio_page_url": str}`. `original=True` means no licensed track (`music_asset_info` absent + "Original audio" text present); then `title` is set to `"Original audio"` and `artist` to `""`.

- [ ] **Step 1: Write the failing tests**

`tests/test_music_parser.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_music_parser.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_music_from_html'`.

- [ ] **Step 3: Implement in `parsers.py`**

Append:

```python
def _extract_json_object(page_html: str, key: str) -> dict | None:
    """Find `"key": { ... }` and parse the object with brace matching.

    Handles escaped quotes and literal braces inside string values, which a
    naive regex cannot. Returns None when the key or a well-formed object is
    not found.
    """
    idx = 0
    while True:
        idx = page_html.find(f'"{key}"', idx)
        if idx == -1:
            return None
        j = page_html.find(":", idx + len(key) + 2)
        if j == -1:
            return None
        k = j + 1
        while k < len(page_html) and page_html[k] in " \t\r\n":
            k += 1
        if k < len(page_html) and page_html[k] == "{":
            depth, in_str, esc = 0, False, False
            for p in range(k, len(page_html)):
                ch = page_html[p]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                else:
                    if ch == '"':
                        in_str = True
                    elif ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            try:
                                return json.loads(page_html[k : p + 1])
                            except Exception:
                                return None
            return None
        idx += len(key)
    return None


_AUDIO_HREF_RE = re.compile(r'href=["\']/reels/audio/([\w-]+)/["\']')


def parse_music_from_html(page_html: str) -> dict:
    """Return {title, artist, original, audio_page_url} for the reel's music."""
    result = {"title": "", "artist": "", "original": False, "audio_page_url": ""}

    obj = _extract_json_object(page_html, "music_asset_info")
    if obj:
        result["title"] = (obj.get("title") or "").strip()
        result["artist"] = (obj.get("display_artist") or "").strip()

    m = _AUDIO_HREF_RE.search(page_html)
    if m:
        result["audio_page_url"] = "https://www.instagram.com/reels/audio/" + m.group(1) + "/"

    if not result["title"] and re.search(r"Original audio", page_html):
        result["original"] = True
        result["title"] = "Original audio"
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_music_parser.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```powershell
git add parsers.py tests/test_music_parser.py
git commit -m "feat: robust music parser (brace-matching JSON scan) + original-audio flag"
```

---

### Task 4: Counts parser — likes / comments / plays

**Files:**
- Create: `tests/test_counts_parser.py`
- Modify: `parsers.py`

**Interfaces:**
- Consumes: fixtures `reel_full.html`, `reel_original_audio.html`, `reel_login_wall.html`.
- Produces: `parsers.parse_counts_from_html(page_html: str) -> dict` with keys `likes`, `comments`, `plays` (strings, `""` when absent). Task 5 wires it into `_extract`.

- [ ] **Step 1: Write the failing tests**

`tests/test_counts_parser.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_counts_parser.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_counts_from_html'`.

- [ ] **Step 3: Implement in `parsers.py`**

Append:

```python
def parse_counts_from_html(page_html: str) -> dict:
    def num(pat: str) -> str:
        m = re.search(pat, page_html)
        return m.group(1) if m else ""

    return {
        "likes": num(r'"like_count"\s*:\s*(\d+)'),
        "comments": num(r'"comment_count"\s*:\s*(\d+)'),
        "plays": num(r'"play_count"\s*:\s*(\d+)')
        or num(r'"video_play_count"\s*:\s*(\d+)'),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_counts_parser.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```powershell
git add parsers.py tests/test_counts_parser.py
git commit -m "feat: likes/comments/plays parser with tests"
```

---

### Task 5: Wire parsers into the engine + `is_original_audio` field + smoke run

**Files:**
- Modify: `scraper.py` (`ReelData` dataclass; `_extract` method; `_is_login_wall` to reuse fixture-verified logic; `export_excel` widths)
- Create: `tests/test_extract_wiring.py`
- Test run (manual): 1-URL live smoke via CLI

**Interfaces:**
- Consumes: all parsers from Tasks 1–4.
- Produces: `ReelData` gains `is_original_audio: bool = False` (new CSV column, appended last in `csv_columns()`); `InstagramReelScraper._extract(page) -> ReelData` now calls the parsers on `page.content()` first and keeps only DOM evaluations as secondary fallbacks (article-header anchor for username, `liked_by`/`comments` spans for counts).

- [ ] **Step 1: Write the failing tests (stub-page wiring test)**

`tests/test_extract_wiring.py` — a fake `Page` proves `_extract` feeds real HTML into the parsers without a browser:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_extract_wiring.py -v`
Expected: FAIL — `AttributeError: 'ReelData' object has no attribute 'is_original_audio'` (and extraction returns empty fields because `_extract` is still inline).

- [ ] **Step 3: Add `is_original_audio` to `ReelData` in `scraper.py`**

Add the field after `status`:

```python
    status: str = "ok"
    is_original_audio: bool = False
```

Add `"is_original_audio"` as the last entry of `csv_columns()`:

```python
            "video_url",
            "status",
            "is_original_audio",
        ]
```

Update `export_excel` widths dict in `scraper.py` — add: `"is_original_audio": 12,`

- [ ] **Step 4: Rewrite `_extract` in `scraper.py` to use the parsers**

Replace the entire `_extract` method body with:

```python
    def _extract(self, page: Page) -> ReelData:
        d = ReelData()
        try:
            html = page.content()
        except Exception:
            html = ""

        # canonical reel URL
        try:
            d.reel_url = page.eval_on_selector(
                'link[rel="canonical"]', "el => el.href"
            ) or d.reel_url
        except Exception:
            pass

        # --- username: parsers first, article-header anchor as fallback ---
        d.username = parse_username_from_html(html)
        if not d.username:
            try:
                d.username = page.evaluate(
                    """
                    () => {
                        const anchors = document.querySelectorAll(
                            'article header a[href^="/"], article a[href^="/"]'
                        );
                        const re = /^\\/([\\w.]+)\\/?$/;
                        for (const a of anchors) {
                            const m = (a.getAttribute('href') || '').match(re);
                            if (m) return m[1];
                        }
                        return '';
                    }
                    """
                ) or ""
            except Exception:
                pass

        # --- music info ---
        music = parse_music_from_html(html)
        d.music_title = music["title"]
        d.music_artist = music["artist"]
        d.audio_page_url = music["audio_page_url"]
        d.is_original_audio = music["original"]

        # --- likes / comments / plays: parsers first, DOM spans as fallback ---
        counts = parse_counts_from_html(html)
        d.likes, d.comments, d.plays = counts["likes"], counts["comments"], counts["plays"]
        if not d.likes or not d.comments:
            try:
                dom_counts = page.evaluate(
                    r"""
                    () => {
                        const pick = (sel) => {
                            const el = document.querySelector(sel);
                            return el ? (el.textContent || '')
                                .replace(/\s+/g, ' ').trim() : '';
                        };
                        return {
                            likes: pick('a[href*="/liked_by/"] span'),
                            comments: pick('a[href*="/comments/"] span'),
                        };
                    }
                    """
                ) or {}
                d.likes = d.likes or (dom_counts.get("likes") or "")
                d.comments = d.comments or (dom_counts.get("comments") or "")
            except Exception:
                pass

        # --- caption / upload date / video URL ---
        d.caption = parse_caption_from_html(html)
        d.uploaded_at = parse_uploaded_at_from_html(html)
        d.video_url = parse_video_url_from_html(html)
        return d
```

Also update the imports at the top of `scraper.py`:

```python
from parsers import (
    REEL_URL_RE,
    normalize_reel_url,
    parse_caption_from_html,
    parse_counts_from_html,
    parse_music_from_html,
    parse_uploaded_at_from_html,
    parse_username_from_html,
    parse_video_url_from_html,
)
```

`_is_login_wall` in `scraper.py` already uses the DOM check `input[name="username"], input[name="password"]`; leave it unchanged (the fixture `reel_login_wall.html` documents that markup for humans).

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: PASS — all 20 tests (1 corpus + 6 normalize + 6 meta + 4 music + 3 counts + 3 wiring; counts may differ if a test was added, report actual number).

- [ ] **Step 6: Compile + live smoke run (1 URL, visible browser, real session)**

Run: `python -m py_compile scraper.py gui.py parsers.py`

Run: `python scraper.py "https://www.instagram.com/reel/Dbnod4jJ-W9/" -w 1 --delay 0 -o results/qa/smoke.csv`
Expected: process completes without exception; `results/qa/smoke.csv` contains one row with a `status` of `ok`, `session_expired`, `timeout`, or `unavailable` (live results vary — the point is no crash and the row is written). If `session_expired`, stop and re-import cookies: `python scraper.py --import-cookies cookies_export.json`.

- [ ] **Step 7: Commit**

```powershell
git add scraper.py tests/test_extract_wiring.py
git commit -m "refactor: wire unit-tested parsers into engine; add is_original_audio field"
```

---

### Task 6: Session + export regression suite (pure, no network)

**Files:**
- Create: `tests/test_session_and_export.py`

**Interfaces:**
- Consumes: `InstagramReelScraper.save_cookies_from_file`, `has_session`, `clear_session`; `write_csv`, `export_json`, `export_excel`; `ReelData`.
- Produces: nothing new — locks existing behavior against regressions, including the new `is_original_audio` CSV column from Task 5.

- [ ] **Step 1: Write the tests**

`tests/test_session_and_export.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python -m pytest tests/test_session_and_export.py -v`
Expected: PASS (9 tests). If `test_csv_roundtrip_includes_new_column` fails, `csv_columns()` in `scraper.py` is missing the trailing `"is_original_audio"` entry — add it (see Task 5 Step 3).

- [ ] **Step 3: Commit**

```powershell
git add tests/test_session_and_export.py
git commit -m "test: session import/expiry + CSV/JSON/Excel export regression suite"
```

---

### Task 7: `run_qa.py` — integration harness with gates

**Files:**
- Create: `run_qa.py`
- Create: `tests/test_qa_metrics.py`

**Interfaces:**
- Consumes: `InstagramReelScraper` (headless/workers/delay/has_session/scrape/stop), `ReelData` (incl. `is_original_audio`), `write_csv`; `tests/corpus.txt`.
- Produces: `run_qa.py` CLI with flags `--corpus`, `--url` (repeatable), `--workers`, `--delay`, `--quick`, `--headless`, `--report-only`; artifacts `results/qa/qa_report.json`, `results/qa/qa_results.csv`; exit code 0 iff all gates pass, else 1. Module-level `compute_metrics(results, runtime_s) -> dict`, `evaluate_gates(metrics) -> list[(name, passed)]`, `GATES` list — unit-tested here and reused in Task 8.

- [ ] **Step 1: Write the failing metric/gate tests**

`tests/test_qa_metrics.py`:

```python
import run_qa
from scraper import ReelData


def make_rows():
    ok = ReelData(username="u", reel_url="https://www.instagram.com/reel/A/",
                  music_title="t", music_artist="a", likes="10",
                  comments="1", caption="c", uploaded_at="2026-01-01")
    orig = ReelData(username="v", reel_url="https://www.instagram.com/reel/B/",
                    music_title="Original audio", is_original_audio=True)
    fail = ReelData(username="", reel_url="https://www.instagram.com/reel/C/",
                    status="session_expired")
    return [ok, ok, orig, fail]


def test_compute_metrics_basics():
    m = run_qa.compute_metrics(make_rows(), runtime_s=42.0)
    assert m["total"] == 4
    assert m["ok_count"] == 3
    assert m["original_audio_count"] == 1
    assert m["status_counts"] == {"ok": 3, "session_expired": 1}
    assert m["runtime_s"] == 42.0


def test_music_fill_excludes_original_audio():
    m = run_qa.compute_metrics(make_rows(), runtime_s=1.0)
    # 2 licensed ok rows, both with music -> 1.0
    assert m["fill"]["music_title"] == 1.0


def test_username_fill_only_counts_ok_rows():
    m = run_qa.compute_metrics(make_rows(), runtime_s=1.0)
    # 3 ok rows, all have username -> 1.0 (the session_expired row is excluded)
    assert m["fill"]["username"] == 1.0


def test_gates_pass_for_good_data():
    m = run_qa.compute_metrics(make_rows(), runtime_s=100.0)
    passed = {name for name, ok in run_qa.evaluate_gates(m) if ok}
    assert passed == {name for name, _ in run_qa.GATES}


def test_gates_fail_on_poor_data():
    rows = [
        ReelData(status="session_expired"),
        ReelData(status="timeout"),
        ReelData(status="unavailable"),
    ]
    m = run_qa.compute_metrics(rows, runtime_s=5.0)
    assert run_qa.evaluate_gates(m) != [g for g in run_qa.GATES]
    # explicitly: ok_rate, username fill, music fill, session gates fail
    failed = {name for name, ok in run_qa.evaluate_gates(m) if not ok}
    assert "ok_rate >= 0.75" in failed
    assert "no session_expired" in failed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_qa_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'run_qa'`.

- [ ] **Step 3: Write `run_qa.py`**

```python
"""End-to-end QA harness for the Instagram reel scraper.

Runs the real engine over a URL corpus with the user's saved session,
measures data-quality gates, writes qa_report.json + qa_results.csv, and
exits 0 iff every gate passes.

Usage:
  python run_qa.py                    # full run over tests/corpus.txt
  python run_qa.py --quick            # 1 URL, headless, no delay (iteration)
  python run_qa.py --url <reel-url>   # single custom URL (repeatable)
  python run_qa.py --report-only      # show the last report without running
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from scraper import InstagramReelScraper, write_csv

PROJECT = Path(__file__).resolve().parent
CORPUS = PROJECT / "tests" / "corpus.txt"
QA_DIR = PROJECT / "results" / "qa"
REPORT_JSON = QA_DIR / "qa_report.json"
REPORT_CSV = QA_DIR / "qa_results.csv"

GATES = [
    {"name": "engine completed (crash-free)", "fn": lambda m: True},
    {"name": "ok_rate >= 0.75", "fn": lambda m: (m["ok_count"] / max(m["total"], 1)) >= 0.75},
    {"name": "username fill >= 0.80", "fn": lambda m: m["fill"]["username"] >= 0.80},
    {"name": "music fill >= 0.60 (licensed only)", "fn": lambda m: m["fill"]["music_title"] >= 0.60},
    {"name": "no session_expired", "fn": lambda m: m["status_counts"].get("session_expired", 0) == 0},
    {"name": "runtime <= 1800s", "fn": lambda m: m["runtime_s"] <= 1800},
]

FILL_FIELDS = ("username", "music_title", "music_artist", "likes", "comments", "caption", "uploaded_at")


def compute_metrics(results, runtime_s: float) -> dict:
    total = len(results)
    status_counts: dict = {}
    for r in results:
        status_counts[r.status] = status_counts.get(r.status, 0) + 1
    ok_rows = [r for r in results if r.status == "ok"]
    licensed = [r for r in ok_rows if not r.is_original_audio]

    def fill(rows, attr: str) -> float:
        if not rows:
            return 0.0
        return round(
            sum(1 for r in rows if (getattr(r, attr) or "").strip()) / len(rows), 3
        )

    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "runtime_s": round(runtime_s, 1),
        "total": total,
        "ok_count": len(ok_rows),
        "original_audio_count": sum(1 for r in ok_rows if r.is_original_audio),
        "status_counts": status_counts,
        "fill": {f: fill(licensed if f.startswith("music") else ok_rows, f) for f in FILL_FIELDS},
        "failures": [
            {"url": r.reel_url, "status": r.status, "music": r.music_title}
            for r in results
            if r.status != "ok"
        ],
    }


def evaluate_gates(metrics: dict) -> list:
    return [(g["name"], g["fn"](metrics)) for g in GATES]


def print_report(metrics: dict, gates: list | None = None) -> None:
    gates = gates or evaluate_gates(metrics)
    print("\n================ QA REPORT ================")
    print(f"timestamp     : {metrics['timestamp']}")
    print(f"runtime       : {metrics['runtime_s']}s")
    print(f"total         : {metrics['total']}")
    print(f"ok            : {metrics['ok_count']}")
    print(f"original audio: {metrics['original_audio_count']}")
    print(f"status counts : {metrics['status_counts']}")
    print("\n-- field fill rates (ok rows; music = licensed only) --")
    for f, v in metrics["fill"].items():
        print(f"  {f:<14}: {v}")
    print("\n-- failures --")
    for fr in metrics["failures"]:
        print(f"  [{fr['status']}] {fr['url']}  music={fr['music']!r}")
    print("\n-- gates --")
    all_ok = True
    for name, passed in gates:
        all_ok = all_ok and passed
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    print(f"\nRESULT: {'ALL GATES PASS' if all_ok else 'GATES FAILED'}")
    print(f"report: {REPORT_JSON}")
    print(f"csv   : {REPORT_CSV}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", default=str(CORPUS))
    ap.add_argument("--url", action="append", default=[], help="extra reel URL (repeatable)")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--quick", action="store_true", help="1 URL, headless, no delay")
    ap.add_argument("--headless", action="store_true", help="run browsers invisible")
    ap.add_argument("--report-only", action="store_true", help="print last report, no run")
    args = ap.parse_args()

    if args.report_only:
        if REPORT_JSON.exists():
            print_report(json.loads(REPORT_JSON.read_text(encoding="utf-8")))
        else:
            print("[!] no report yet - run the harness first")
        return 0

    urls: list = []
    if Path(args.corpus).exists():
        urls += [
            l.strip()
            for l in Path(args.corpus).read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
    urls += args.url
    if not urls:
        print("[x] no URLs found (corpus missing?)")
        return 1

    headless = args.headless or args.quick
    workers = 1 if args.quick else args.workers
    delay = 0.0 if args.quick else args.delay
    if args.quick:
        urls = urls[:1]

    scraper = InstagramReelScraper(headless=headless, workers=workers, delay=delay)
    if not scraper.has_session():
        print("[x] FAIL: no valid session. Re-import cookies (storage_state.json).")
        return 1

    QA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[>] QA run: {len(urls)} URL(s), workers={workers}, "
          f"headless={headless}, delay={delay}s")
    t0 = time.time()
    results = scraper.scrape(urls)
    runtime_s = time.time() - t0

    metrics = compute_metrics(results, runtime_s)
    REPORT_JSON.write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_csv(results, REPORT_CSV)

    gates = evaluate_gates(metrics)
    print_report(metrics, gates)
    return 0 if all(p for _, p in gates) else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run metric tests to verify they pass**

Run: `python -m pytest tests/test_qa_metrics.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Sanity-run the harness in report-only mode**

Run: `python run_qa.py --report-only`
Expected: `[!] no report yet - run the harness first` (exit 0).

- [ ] **Step 6: Commit**

```powershell
git add run_qa.py tests/test_qa_metrics.py
git commit -m "feat: QA harness run_qa.py with data-quality gates + tests"
```

---

### Task 8: First full QA run — collect baseline data

**Files:**
- Create: `results/qa/run-1-notes.md` (local, git-ignored — data collection, not code)

**Interfaces:**
- Consumes: `run_qa.py` (Task 7), corpus (Task 0), session (existing `storage_state.json`).
- Produces: baseline `results/qa/qa_report.json` + `qa_results.csv`; a decision record in `run-1-notes.md` mapping every FAILED gate to a fix task (Tasks 9–10 or session re-import).

- [ ] **Step 1: Ensure session is valid**

Run: `python -c "from scraper import InstagramReelScraper; print('session ok' if InstagramReelScraper().has_session() else 'NO SESSION')"`
Expected: `session ok`. If `NO SESSION`, run `python scraper.py --import-cookies cookies_export.json` first.

- [ ] **Step 2: Run the full QA**

Run: `python run_qa.py --workers 2 --delay 2.0`
Expected: report table printed with per-field fill rates and PASS/FAIL gates; `qa_report.json` and `qa_results.csv` written; visible browser windows open during the run (expected — do not cancel them). Live results are data, not an assertion: gates may pass or fail. Exit code will be 0 or 1 accordingly.

- [ ] **Step 3: Record the outcome and branch**

Create `results/qa/run-1-notes.md` containing: the report metrics, the gate results, and — for each failed gate — the diagnosed cause from `qa_report.json` ("failures" list + fill rates). Decision rules:

| Observation | Action |
|---|---|
| any `session_expired` | re-import cookies (`--import-cookies cookies_export.json`), re-run |
| `timeout` / `error:*` rows present | Task 9 (backoff) + Task 10 (retry) |
| `music fill < 0.60` with `music_title` empty on licensed reels | Task 10 review; if the fixture-based parsers pass but live HTML differs, add a new fixture + parser tweak |
| `unavailable` rows | expected for deleted/private reels — record them, no code change |
| `username fill < 0.80` | Task 10 review (DOM fallback already exists) |

- [ ] **Step 4: Commit the loop state**

```powershell
git add -A
git commit -m "docs: baseline QA run 1 - gates and decisions recorded (results stay local)"
```

(Only `run-1-notes.md` is committed if it is outside ignored dirs — place it in the project root instead of `results/` if it must be versioned; `results/` is git-ignored by design, so keep a copy of the notes at `docs/qa/run-1-notes.md`.)

---

### Task 9: Fix — exponential backoff after consecutive failures

**Files:**
- Modify: `scraper.py` (add module-level `backoff_delay`; use it in `worker_fn` inside `scrape`)
- Create: `tests/test_backoff.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `scraper.backoff_delay(consecutive_failures: int, base: float = 2.0, cap: float = 30.0) -> float` — 0 for ≤0 failures, `min(cap, base * 2 ** (failures - 1))` otherwise. `worker_fn` tracks a per-worker consecutive-failure streak and adds the backoff to the normal delay between URLs.

- [ ] **Step 1: Write the failing tests**

`tests/test_backoff.py`:

```python
from scraper import backoff_delay


def test_zero_failures_no_delay():
    assert backoff_delay(0) == 0.0
    assert backoff_delay(-3) == 0.0


def test_exponential_growth():
    assert backoff_delay(1) == 2.0
    assert backoff_delay(2) == 4.0
    assert backoff_delay(3) == 8.0


def test_capped():
    assert backoff_delay(10) == 30.0
    assert backoff_delay(50) == 30.0


def test_custom_base_and_cap():
    assert backoff_delay(2, base=1.0, cap=5.0) == 2.0
    assert backoff_delay(10, base=1.0, cap=5.0) == 5.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_backoff.py -v`
Expected: FAIL — `ImportError: cannot import name 'backoff_delay'`.

- [ ] **Step 3: Implement `backoff_delay` in `scraper.py`**

Add near the top of `scraper.py` (after the constants):

```python
def backoff_delay(consecutive_failures: int, base: float = 2.0, cap: float = 30.0) -> float:
    """Exponential cool-down (s) after N consecutive failed reels."""
    if consecutive_failures <= 0:
        return 0.0
    return min(cap, base * (2 ** (consecutive_failures - 1)))
```

- [ ] **Step 4: Wire the streak into `worker_fn`**

In `scraper.py` `scrape()`, inside `worker_fn`, replace the loop's tail (the current `time.sleep(self.delay + random.uniform(0, 1.5))` block) with streak tracking:

```python
                    fail_streak = 0
                    while True:
                        try:
                            url = q.get_nowait()
                        except queue.Empty:
                            break
                        if self._stop.is_set():
                            break
                        self.log(f"    worker {wid} -> {url}")
                        page = context.new_page()
                        try:
                            data = self._scrape_one(page, url)
                        finally:
                            page.close()
                        with lock:
                            results.append(data)
                        if progress_cb:
                            progress_cb(len(results), total)
                        fail_streak = fail_streak + 1 if data.status != "ok" else 0
                        wait = (
                            self.delay
                            + random.uniform(0, 1.5)
                            + backoff_delay(fail_streak)
                        )
                        if fail_streak >= 2:
                            self.log(
                                f"    worker {wid}: {fail_streak} failures in a row, "
                                f"cooling down {wait:.1f}s"
                            )
                        time.sleep(wait)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_backoff.py -v`
Expected: PASS (4 tests). Then `python -m pytest tests/ -v` — all previous tests still PASS.

- [ ] **Step 6: Commit**

```powershell
git add scraper.py tests/test_backoff.py
git commit -m "fix: exponential backoff between reels after consecutive failures"
```

---

### Task 10: Improve — one automatic retry for transient failures

**Files:**
- Modify: `scraper.py` (`should_retry` helper; `_scrape_one` becomes a two-attempt loop)
- Create: `tests/test_retry.py`

**Interfaces:**
- Consumes: existing `_scrape_one` body.
- Produces: `scraper.should_retry(status: str) -> bool` — True for `"timeout"` and any `status.startswith("error:")`, False otherwise (never retries `ok`, `session_expired`, `unavailable`). `_scrape_one(page, url)` keeps the same signature and behavior but retries ONCE when `should_retry` matches and the engine is not stopped.

- [ ] **Step 1: Write the failing tests**

`tests/test_retry.py`:

```python
from scraper import should_retry


def test_retryable_statuses():
    assert should_retry("timeout") is True
    assert should_retry("error: TimeoutError") is True
    assert should_retry("error: SomeError") is True


def test_non_retryable_statuses():
    assert should_retry("ok") is False
    assert should_retry("session_expired") is False
    assert should_retry("unavailable") is False
    assert should_retry("") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_retry.py -v`
Expected: FAIL — `ImportError: cannot import name 'should_retry'`.

- [ ] **Step 3: Implement `should_retry` in `scraper.py`**

Add after `backoff_delay`:

```python
def should_retry(status: str) -> bool:
    """Transient failures worth one automatic retry."""
    return status == "timeout" or status.startswith("error:")
```

- [ ] **Step 4: Convert `_scrape_one` to a two-attempt loop**

Replace the current `_scrape_one` method with:

```python
    def _scrape_one(self, page: Page, url: str) -> ReelData:
        data = ReelData(reel_url=url)
        for attempt in (1, 2):
            data = self._attempt_one(page, url)
            if data.status == "ok" or not should_retry(data.status):
                break
            if self._stop.is_set():
                break
            self.log(f"    retry {url} (attempt {attempt + 1})")
            page.wait_for_timeout(1500)
        return data

    def _attempt_one(self, page: Page, url: str) -> ReelData:
        """Single navigation + extraction pass for one reel URL."""
        data = ReelData(reel_url=url)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            self._dismiss_overlays(page)

            if self._is_login_wall(page):
                data.status = "session_expired"
                self.log(
                    f"    [x] {url} - session expired / login wall. "
                    "Re-login via the Login button."
                )
                return data

            try:
                page.wait_for_selector(
                    'a[href*="/reels/audio/"], meta[property="og:title"], '
                    "article, video",
                    timeout=30000,
                )
            except PWTimeoutError:
                pass

            page.wait_for_timeout(2500)  # let lazy content settle
            data = self._extract(page)
            if not data.reel_url:
                data.reel_url = url  # keep the input URL if canonical missing

            if self._is_unavailable(page):
                data.status = "unavailable"
                return data

            # One reload retry if the page rendered without core data.
            if not data.username and not data.music_title:
                try:
                    page.reload(wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(2500)
                    data = self._extract(page)
                except Exception:
                    pass

            data.status = "ok"
        except PWTimeoutError:
            data.status = "timeout"
            self.log(f"    [x] {url} - timed out.")
        except Exception as e:  # pragma: no cover - defensive
            data.status = f"error: {type(e).__name__}"
            self.log(f"    [x] {url} -> {e}")
        return data
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_retry.py -v`
Expected: PASS (2 tests). Then `python -m pytest tests/ -v` — the full suite still PASSes (the wiring tests use `_extract`, unchanged; `_scrape_one` signature unchanged).

- [ ] **Step 6: Commit**

```powershell
git add scraper.py tests/test_retry.py
git commit -m "improve: single auto-retry for transient timeout/error reels"
```

---

### Task 11: Close the loop — full re-run + before/after summary + docs

**Files:**
- Create: `docs/qa/run-1-notes.md` (baseline record — moved/created here so it is versioned)
- Create: `docs/qa/run-2-notes.md` (post-fix record)
- Modify: `README.md` (add "QA loop" section)

**Interfaces:**
- Consumes: Tasks 8–10 outputs; `run_qa.py`.
- Produces: a versioned before/after comparison proving the loop works, and the documented operating procedure for future runs.

- [ ] **Step 1: Move the baseline notes into the repo**

```powershell
cd "E:\Download\Code\AionUi\Work Directory\conversations\2026\08\06\aionrs-temp-500e1eff\instagram-reel-scraper"
New-Item -ItemType Directory -Force docs\qa | Out-Null
Copy-Item results\qa\run-1-notes.md docs\qa\run-1-notes.md -ErrorAction SilentlyContinue
```

(If the file does not exist yet because Task 8 was skipped in execution, create `docs/qa/run-1-notes.md` from the baseline `qa_report.json` metrics.)

- [ ] **Step 2: Re-import cookies (fresh session, in case of expiry)**

Run: `python scraper.py --import-cookies cookies_export.json`
Expected: `[OK] Cookies imported -> ...storage_state.json`.

- [ ] **Step 3: Full QA re-run**

Run: `python run_qa.py --workers 2 --delay 2.0`
Expected: report table printed; exit code 0 if all gates pass. If any gate still fails, diagnose from `qa_report.json` and repeat the relevant fix task before re-running — that is the loop.

- [ ] **Step 4: Write `docs/qa/run-2-notes.md`**

Content: the new metrics, gate results, and a before/after table (run-1 vs run-2 columns: ok_rate, username fill, music fill, failures by status). State explicitly which fix (backoff / retry / session re-import) moved each metric.

- [ ] **Step 5: Add the QA section to `README.md`**

Append:

```markdown
## QA loop

```powershell
python -m pytest tests/ -v        # unit layer (no network)
python run_qa.py --workers 2 --delay 2.0   # full corpus run, visible browsers
python run_qa.py --quick          # fast 1-URL iteration (headless)
python run_qa.py --report-only    # show last report
```

Full runs write `results/qa/qa_report.json` + `qa_results.csv` and exit 0
only when every gate passes (ok_rate >= 0.75, username fill >= 0.80,
music fill >= 0.60 on licensed reels, no session_expired, runtime <= 1800s).
Decision rules: `session_expired` -> re-import cookies; `timeout`/`error` ->
backoff + retry (already built in); `unavailable` -> deleted/private reel,
expected; low music fill -> add a fixture + extend `parsers.parse_music_from_html`.
```

- [ ] **Step 6: Run the full unit suite one last time**

Run: `python -m pytest tests/ -v`
Expected: PASS — every test across all tasks.

- [ ] **Step 7: Commit**

```powershell
git add docs/qa/ README.md
git commit -m "docs: QA loop closed - before/after notes + operating procedure"
```

---

## Self-Review

**Spec coverage:** The spec asks for an end-to-end "test → fix → improve" loop against the 12 URLs. Coverage: corpus + unit layer (Tasks 0–6), integration harness with gates (Task 7), baseline run + decision rules (Task 8), concrete fixes (Task 9 backoff, Task 10 retry), loop closure + docs (Task 11). All 12 URLs are the corpus in Task 0; the harness and fixes run against them in Tasks 8 and 11.

**Placeholder scan:** No TBD/TODO; every code step carries complete code, and every run step carries an expected outcome. Live runs (Tasks 8/11) state that results are data, not assertions, and specify the branch conditions — intentional, since real Instagram output is nondeterministic.

**Type consistency:** `normalize_reel_url` (Task 1) is used by gui.py (Task 1 Step 6) and scraper CLI (Task 1 Step 5) with the same `str | None` signature. `parse_music_from_html` returns `{"title","artist","original","audio_page_url"}` in Task 3 and is consumed with those exact keys in Task 5. `ReelData.is_original_audio` is added in Task 5 and consumed by `compute_metrics` in Task 7 and the export tests in Task 6 (Task 6 runs after Task 5 in dependency order). `backoff_delay` / `should_retry` are module-level in `scraper.py` and imported as `from scraper import ...` in their tests. `run_qa.compute_metrics` / `evaluate_gates` / `GATES` names match between Task 7 tests and `run_qa.py`.

One deliberate simplification: Task 5 removes the old audio-link DOM evaluation (the parser's `_AUDIO_HREF_RE` reads the same anchors from `page.content()`), so the `a[href*="/reels/audio/"]` wait selector in `_attempt_one` is retained purely as a render signal — no behavior regression.
