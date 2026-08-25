"""Build the Windows .exe via PyInstaller.

Run: python build_exe.py
Requires: pyinstaller (pip install pyinstaller)
Output: dist\\Reelminner\\Reelminner.exe  (onedir app folder)
"""

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIST = HERE / "dist"
APP_DIR_OUT = DIST / "Reelminner"
EXE = APP_DIR_OUT / "Reelminner.exe"


def main() -> int:
    # 1. Generate the icon (idempotent).
    subprocess.run(
        [sys.executable, str(HERE / "assets" / "make_icon.py")],
        check=True,
        cwd=HERE,
    )
    # 2. Clean stale output (onedir keeps old files otherwise).
    if APP_DIR_OUT.exists():
        shutil.rmtree(APP_DIR_OUT)
    # 3. Build.
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "Reelminner.spec", "--noconfirm", "--clean"],
        check=True,
        cwd=HERE,
    )
    # 4. Verify artifact.
    if not EXE.exists():
        print("ERROR: dist\\Reelminner\\Reelminner.exe missing", file=sys.stderr)
        return 1
    size_mb = EXE.stat().st_size / (1024 * 1024)
    total_mb = sum(p.stat().st_size for p in APP_DIR_OUT.rglob("*") if p.is_file()) / (1024 * 1024)
    print(f"OK: {EXE} ({size_mb:.1f} MB exe, {total_mb:.0f} MB app folder)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
