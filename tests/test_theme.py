"""Theme token + WCAG contrast tests."""

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

import theme  # noqa: E402


def test_accent_token():
    assert theme.ACCENT == "#6366F1"


def test_color_roles_cover_all_tokens():
    for key, val in theme.COLOR_ROLES.items():
        assert val, f"empty color role: {key}"


def test_primary_text_contrast():
    assert theme.contrast_ratio(theme.BG, theme.FG) >= 4.5


def test_muted_text_contrast_on_all_surfaces():
    for bg in (theme.BG, theme.BG_PANEL, theme.BG_INPUT):
        assert theme.contrast_ratio(bg, theme.FG_MUTED) >= 4.5, f"muted vs {bg}"


def test_contrast_ratio_known_pair():
    assert abs(theme.contrast_ratio("#000000", "#FFFFFF") - 21.0) < 0.01
    assert abs(theme.contrast_ratio("#FFFFFF", "#FFFFFF") - 1.0) < 0.01
