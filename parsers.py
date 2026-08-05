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
