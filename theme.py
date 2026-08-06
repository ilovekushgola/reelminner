"""Design tokens — single source of truth for all UI colors and fonts.

Dark professional developer-tool palette (verified against the
ui-ux-pro-max dark-tool design database). Widgets must read colors
from this module — never hardcode hex values elsewhere.
"""

# --- colors ---
ACCENT = "#6366F1"      # indigo-500 (primary CTA, progress, selected)
ACCENT_HI = "#4F46E5"   # indigo-600 (hover/pressed)
ACCENT_SOFT = "#EEF2FF" # indigo-50 (subtle highlight / active bg, light accents)

BG = "#0F172A"          # slate-900 (window background)
BG_PANEL = "#1E293B"    # slate-800 (cards, panels, headers)
BG_INPUT = "#334155"    # slate-700 (entry / text areas, troughs)

FG = "#F8FAFC"          # slate-50 (primary text)
FG_MUTED = "#A3B3C8"    # muted text — passes 4.5:1 on BG, BG_PANEL and BG_INPUT

BORDER = "#334155"      # slate-700 (visible borders)

SUCCESS = "#22C55E"     # green-500 (ok status)
ERROR = "#EF4444"       # red-500 (error status)
WARN = "#F59E0B"        # amber-500 (warning status)

ZEBRA_EVEN = "#16213A"  # striped row background (even rows)

# --- fonts ---
MONO = ("Consolas", 10)
UI = ("Segoe UI", 10)
UI_BOLD = ("Segoe UI", 10, "bold")
TITLE = ("Segoe UI", 16, "bold")

# --- semantic role map (for layout/theming code that needs lookups) ---
COLOR_ROLES = {
    "bg": BG,
    "panel": BG_PANEL,
    "input": BG_INPUT,
    "fg": FG,
    "muted": FG_MUTED,
    "border": BORDER,
    "accent": ACCENT,
    "success": SUCCESS,
    "error": ERROR,
    "warn": WARN,
}


def contrast_ratio(c1: str, c2: str) -> float:
    """WCAG contrast ratio between two #RRGGBB colors (0.0-21.0)."""

    def lum(hex_color: str) -> float:
        hex_color = hex_color.lstrip("#")
        r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4))
        comp = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * comp(r) + 0.7152 * comp(g) + 0.0722 * comp(b)

    l1, l2 = lum(c1), lum(c2)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def contrast_ok(c1: str, c2: str, min_ratio: float = 4.5) -> bool:
    return contrast_ratio(c1, c2) >= min_ratio


if __name__ == "__main__":
    print("ACCENT:", ACCENT)
    print(f"BG vs FG contrast: {contrast_ratio(BG, FG):.2f}:1")
    print(f"BG_INPUT vs FG_MUTED contrast: {contrast_ratio(BG_INPUT, FG_MUTED):.2f}:1")
