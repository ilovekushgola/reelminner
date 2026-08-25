# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: onedir, windowed GUI app for Instagram Reel Scraper.

Onedir (not onefile) so the app starts instantly (no per-launch temp
extraction of ~140 MB) and can ship its own Playwright browsers in a
predictable folder layout.
"""

import os

from pathlib import Path

HERE = Path(SPECPATH).resolve() if "SPECPATH" in dir() else Path.cwd()
STATE_FILE = HERE / "storage_state.json"

datas = []
# Bundle the saved session (if present at build time) so a built app
# ships with the user's logged-in storage state.
if STATE_FILE.exists():
    datas.append((str(STATE_FILE), "."))

# ---------------------------------------------------------------------------
# Bundle the Playwright browsers the app needs (chromium + headless shell +
# ffmpeg for video) from the local ms-playwright cache. The app sets
# PLAYWRIGHT_BROWSERS_PATH to its own ms-playwright folder at runtime, so the
# installed app is fully self-contained and works on machines without the
# cache. Datas land under _internal/ms-playwright/ in the onedir layout.
# ---------------------------------------------------------------------------
BROWSER_CACHE = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
BUNDLE_REVISIONS = [
    "chromium-1228",
    "chromium_headless_shell-1228",
    "ffmpeg-1011",
    "ffmpeg-1009",
]
for _rev in BUNDLE_REVISIONS:
    _src = BROWSER_CACHE / _rev
    if _src.is_dir():
        datas.append((str(_src), f"ms-playwright/{_rev}"))
        print(f"  [spec] bundling browser: {_rev}")

hiddenimports = [
    "playwright.sync_api",
    "playwright._impl._driver",
    "pandas",
    "openpyxl",
    "openpyxl.cell._writer",
    "email",
    "email.mime",
    "selftest",
    "theme",
    "config",
]

a = Analysis(
    ["gui.py"],
    pathex=[str(HERE)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Reelminner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(HERE / "assets" / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Reelminner",
)
