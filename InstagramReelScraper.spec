# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: one-file, windowed GUI exe for Instagram Reel Scraper."""

from pathlib import Path

HERE = Path(SPECPATH).resolve() if "SPECPATH" in dir() else Path.cwd()
STATE_FILE = HERE / "storage_state.json"

datas = []
# Bundle the saved session (if present at build time) so a built exe
# ships with the user's logged-in storage state.
if STATE_FILE.exists():
    datas.append((str(STATE_FILE), "."))

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
    a.binaries,
    a.datas,
    [],
    name="InstagramReelScraper",
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
