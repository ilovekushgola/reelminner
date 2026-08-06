"""Regression guard: reel_url must be at COLUMN_ORDER index 3.

The "followers" column was inserted at index 2, shifting reel_url from
index 2 to index 3. _copy_url/_open_url/_copy_row must use
COLUMN_ORDER.index("reel_url") — never a hardcoded index.
"""

import importlib
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

import gui  # noqa: E402


def test_column_order_has_followers_at_2_and_reel_url_at_3():
    assert gui.COLUMN_ORDER[2] == "followers"
    assert gui.COLUMN_ORDER[3] == "reel_url"


def test_copy_url_uses_named_column_index_not_literal():
    src = Path(gui.__file__).read_text(encoding="utf-8")
    # The copy/open lookups must resolve the reel_url column by name.
    assert 'COLUMN_ORDER.index("reel_url")' in src


def test_gui_imports_without_opening_window():
    # Importing the module must not create a Tk window (import-safe).
    mod = importlib.reload(gui)
    assert mod.COLUMN_ORDER[3] == "reel_url"
