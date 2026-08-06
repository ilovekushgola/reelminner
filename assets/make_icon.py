"""Generate assets/icon.ico: indigo rounded square + white play triangle.

Run: python assets/make_icon.py
Requires: Pillow (pip install pillow)
"""

from pathlib import Path

from PIL import Image, ImageDraw

ACCENT = (99, 102, 241, 255)  # #6366F1
WHITE = (255, 255, 255, 255)
SIZE = 128
OUT = Path(__file__).resolve().parent / "icon.ico"


def draw(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = size * 0.08
    radius = size * 0.22
    d.rounded_rectangle(
        [pad, pad, size - pad, size - pad], radius=radius, fill=ACCENT
    )
    cx, cy = size / 2, size / 2
    r = size * 0.26
    d.polygon(
        [(cx - r * 0.55, cy - r), (cx - r * 0.55, cy + r), (cx + r * 0.9, cy)],
        fill=WHITE,
    )
    return img


def main() -> None:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [draw(s) for s in sizes]
    imgs[-1].save(OUT, sizes=[(s, s) for s in sizes])
    print(f"wrote {OUT} ({len(sizes)} sizes)")


if __name__ == "__main__":
    main()
