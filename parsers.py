"""Pure parsing helpers for the Instagram reel scraper.

Everything here is a function of the HTML string (or a URL string) alone —
no browser, no network. This keeps the extraction logic unit-testable.
"""

from __future__ import annotations

import html as htmlmod
import json
import re
from datetime import datetime, timezone

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


def looks_like_handle(s: str) -> bool:
    """True when s looks like an IG handle: 1-30 chars of [\\w.] only."""
    return bool(re.fullmatch(r"[\w.]{1,30}", s or ""))


def parse_username_from_html(page_html: str) -> str:
    og_title = meta_content(page_html, "property", "og:title")
    # 1. display name with @handle in parens: "Name (@handle) on Instagram"
    m = re.search(r"\(@([\w.]+)\)", og_title)
    if m:
        return m.group(1).strip()
    # 2. plain handle in og:title (skip styled display names -> fall through)
    m = re.match(r"^\s*([^|]+?)\s+on Instagram", og_title)
    if m and looks_like_handle(m.group(1).strip()):
        return m.group(1).strip()
    # caption-style fallbacks, checked against both meta kinds that carry it
    for desc in (
        meta_content(page_html, "name", "description"),
        meta_content(page_html, "property", "og:description"),
    ):
        # 3. "@handle" reference
        m = re.search(r"\(@([\w.]+)\)", desc)
        if m:
            return m.group(1).strip()
        # 4. "35 likes, 0 comments - handle on <Month D, YYYY>: ..."
        m = re.match(
            r"^\s*[\d,.]+\s*(?:like|view)s?[^:]*-\s*([\w.]+)\s+on\s+"
            r"[A-Z][a-z]+\s+\d{1,2},\s+\d{4}",
            desc,
        )
        if m:
            return m.group(1).strip()
        # 5. "<handle> on <Month D, YYYY>" (profile-less reels)
        m = re.match(r"^\s*([\w.]+)\s+on\s+[A-Z][a-z]+\s+\d{1,2},\s+\d{4}", desc)
        if m:
            return m.group(1).strip()
        # 6. "<handle> on Instagram"
        m = re.match(r"^\s*([\w.]+)\s+on Instagram", desc)
        if m:
            return m.group(1).strip()
    # 7. JSON-LD / embedded JSON: owner.username
    m = re.search(r'"owner"\s*:\s*\{\s*"username"\s*:\s*"([\w.]+)"', page_html)
    if m:
        return m.group(1).strip()
    # 8. generic embedded JSON username
    m = re.search(r'"username"\s*:\s*"([\w.]+)"', page_html)
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
    if m:
        return m.group(1)
    # caption-style fallback: '... on <Month D, YYYY>' -> YYYY-MM-DD
    m = re.search(r"on\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})", page_html)
    if m:
        try:
            return datetime.strptime(m.group(1), "%B %d, %Y").strftime("%Y-%m-%d")
        except ValueError:
            return ""
    # JSON-LD / embedded JSON: taken_at_timestamp (epoch secs) -> UTC ISO
    m = re.search(r'"taken_at_timestamp"\s*:\s*(\d{10})', page_html)
    if m:
        return datetime.fromtimestamp(
            int(m.group(1)), tz=timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
    return ""


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


def parse_followers_from_html(page_html: str) -> str:
    """Followers count from a profile page: og:description, JSON, else ''."""
    # og:description: "12.3K Followers, 10 Following, 200 Posts"
    desc = meta_content(page_html, "property", "og:description")
    m = re.search(r"([\d,.]+\s*[KMB]?)\s+Followers", desc)
    if m:
        return m.group(1).strip().replace(" ", "")
    # JSON-LD / embedded JSON
    m = re.search(r'"edge_followed_by"\s*:\s*\{\s*"count"\s*:\s*(\d+)', page_html)
    if m:
        return m.group(1)
    m = re.search(r'"followers"\s*:\s*(\d+)', page_html)
    if m:
        return m.group(1)
    return ""


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


# ---------------------------------------------------------------------------
# Additive profile / media parsers (Reelminner discovery Phase 1).
# All pure & dependency-free. They never raise; on a miss they return "" (or
# False / an empty dict) so engine behavior is unchanged when data is missing.
# ---------------------------------------------------------------------------

REEL_ID_RE = re.compile(r"/(?:reel|reels|p|tv)/([A-Za-z0-9_-]+)")


def parse_reel_id_from_url(url: Optional[str]) -> str:
    """Extract the Instagram shortcode (reel id) from a reel URL."""
    if not url:
        return ""
    m = REEL_ID_RE.search(url)
    return m.group(1) if m else ""


def parse_thumbnail_from_html(page_html: str) -> str:
    """Best-effort thumbnail URL from ``og:image``."""
    try:
        m = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            page_html,
            re.IGNORECASE,
        )
        if m:
            return m.group(1)
    except Exception:
        pass
    return ""


def parse_music_id_from_html(page_html: str) -> str:
    """Extract the audio asset id from ``music_asset_info`` JSON."""
    try:
        m = re.search(r'"audio_asset_id"\s*:\s*"([^"]+)"', page_html)
        if m:
            return m.group(1)
    except Exception:
        pass
    return ""


def parse_profile_card_from_html(page_html: str) -> dict:
    """Extract profile-level fields from a profile page HTML.

    Returns keys: ``full_name``, ``bio``, ``is_verified`` (bool),
    ``reels_count`` (str). Best-effort: any field not found is left empty / False.
    """
    out: dict = {
        "full_name": "",
        "bio": "",
        "is_verified": False,
        "reels_count": "",
    }
    if not page_html:
        return out
    try:
        desc = meta_content(page_html, "name", "description")
        if desc:
            # counts: "X Followers, Y Following, Z Posts - bio"
            cm = re.search(r"([\d.,KkMm]+)\s*(?:Posts|reels)", desc, re.IGNORECASE)
            if cm:
                out["reels_count"] = cm.group(1)
            bm = re.search(r"\s-\s+(.+)$", desc)
            if bm:
                out["bio"] = bm.group(1).strip()
        # display name from og:title ("Name • Instagram photos and videos")
        t = meta_content(page_html, "property", "og:title")
        if t:
            name = t.replace(" • Instagram photos and videos", "").strip()
            name = re.sub(r"\s*\(@[^)]*\)\s*$", "", name)
            out["full_name"] = name
        # verified flag (best effort)
        vm = re.search(r'"is_verified"\s*:\s*(true|false)', page_html)
        if vm:
            out["is_verified"] = vm.group(1).lower() == "true"
    except Exception:
        pass
    return out
