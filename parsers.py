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
