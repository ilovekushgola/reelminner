"""Build the Windows .exe via PyInstaller.

Run: python build_exe.py
Requires: pyinstaller (pip install pyinstaller)
Output: dist\\InstagramReelScraper.exe
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIST = HERE / "dist"
EXE = DIST / "InstagramReelScraper.exe"


def main() -> int:
    # 1. Generate the icon (idempotent).
    subprocess.run(
        [sys.executable, str(HERE / "assets" / "make_icon.py")],
        check=True,
        cwd=HERE,
    )
    # 2. Build.
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "InstagramReelScraper.spec", "--noconfirm", "--clean"],
        check=True,
        cwd=HERE,
    )
    # 3. Verify artifact.
    if not EXE.exists():
        print("ERROR: dist\\InstagramReelScraper.exe missing", file=sys.stderr)
        return 1
    size_mb = EXE.stat().st_size / (1024 * 1024)
    print(f"OK: {EXE} ({size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
