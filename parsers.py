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
