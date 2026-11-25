"""Render PNG icons (192, 512) matching icons/icon.svg with Pillow."""
import math
import pathlib

from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parent.parent


def wave(draw, s, y0, color, width):
    pts = []
    for k in range(121):
        x = 136 + 240 * k / 120
        y = y0 - 28 * math.sin(math.pi * (x - 136) / 120)
        pts.append((x * s, y * s))
    draw.line(pts, fill=color, width=int(width * s), joint="curve")
    for p in (pts[0], pts[-1]):
        r = width * s / 2
        draw.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=color)


def render(size):
    big = size * 4
    s = big / 512
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, big, big], radius=int(112 * s), fill="#eef4f2")
    d.ellipse([80 * s, 80 * s, 432 * s, 432 * s], fill="#9fd8c8")
    wave(d, s, 228, (21, 48, 43, 255), 26)
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    wave(ImageDraw.Draw(over), s, 300, (21, 48, 43, 115), 26)
    img = Image.alpha_composite(img, over)
    return img.resize((size, size), Image.LANCZOS)


for n in (192, 512):
    render(n).save(ROOT / "icons" / f"icon-{n}.png")
    print("icon", n)
