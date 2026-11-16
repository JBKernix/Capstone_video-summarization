"""Generate launcher icons (assets/icons/*.ico) for the root .bat files.

Usage: python scripts/make_icons.py
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "assets" / "icons"

S = 1024  # draw at 4x and downsample for smooth edges
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
WHITE = (255, 255, 255, 255)


def base(top, bottom):
    """Rounded square with a vertical gradient."""
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / (S - 1)
        color = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,)
        gd.line([(0, y), (S, y)], fill=color)
    mask = Image.new("L", (S, S), 0)
    pad = S * 0.04
    ImageDraw.Draw(mask).rounded_rectangle([pad, pad, S - pad, S - pad], radius=S * 0.22, fill=255)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    return img


def glyph_play(d):
    c = S / 2
    r = S * 0.27
    pts = [(c - r * 0.75, c - r), (c - r * 0.75, c + r), (c + r * 1.05, c)]
    d.polygon(pts, fill=WHITE)


def glyph_stop(d):
    c = S / 2
    r = S * 0.22
    d.rounded_rectangle([c - r, c - r, c + r, c + r], radius=S * 0.05, fill=WHITE)


def glyph_restart(d):
    c = S / 2
    r = S * 0.25
    w = int(S * 0.085)
    # open circular arrow: PIL arcs run clockwise from 3 o'clock, leaving a gap at the upper right
    d.arc([c - r, c - r, c + r, c + r], start=-20, end=270, fill=WHITE, width=w)
    # arrow head at the 12 o'clock end, pointing clockwise into the gap
    a = math.radians(270)
    px, py = c + r * math.cos(a), c + r * math.sin(a)
    tx, ty = -math.sin(a), math.cos(a)  # clockwise tangent on screen
    nx, ny = math.cos(a), math.sin(a)
    h = S * 0.14
    tip = (px + tx * h, py + ty * h)
    left = (px + nx * h * 0.85, py + ny * h * 0.85)
    right = (px - nx * h * 0.85, py - ny * h * 0.85)
    d.polygon([tip, left, right], fill=WHITE)


def glyph_cloud(d, color):
    c = S / 2
    # cloud body
    d.ellipse([c - S * 0.30, c - S * 0.02, c - S * 0.06, c + S * 0.22], fill=WHITE)
    d.ellipse([c - S * 0.17, c - S * 0.20, c + S * 0.13, c + S * 0.10], fill=WHITE)
    d.ellipse([c + S * 0.04, c - S * 0.04, c + S * 0.30, c + S * 0.22], fill=WHITE)
    d.rectangle([c - S * 0.18, c + S * 0.04, c + S * 0.18, c + S * 0.22], fill=WHITE)
    # up arrow cut into the cloud (tunnel → outside)
    aw = S * 0.035
    d.rectangle([c - aw, c - S * 0.02, c + aw, c + S * 0.16], fill=color)
    d.polygon([(c - S * 0.10, c - S * 0.01), (c + S * 0.10, c - S * 0.01), (c, c - S * 0.12)], fill=color)


def glyph_app(d, color):
    c = S / 2
    # browser window
    l, t, r, b = c - S * 0.28, c - S * 0.22, c + S * 0.28, c + S * 0.22
    d.rounded_rectangle([l, t, r, b], radius=S * 0.05, fill=WHITE)
    d.rectangle([l + S * 0.04, t + S * 0.10, r - S * 0.04, b - S * 0.04], fill=color)
    for i in range(3):
        x = l + S * 0.06 + i * S * 0.055
        d.ellipse([x - S * 0.018, t + S * 0.032, x + S * 0.018, t + S * 0.068], fill=color)
    # small play mark inside the window
    pc_x, pc_y, pr = c, c + S * 0.06, S * 0.07
    d.polygon([(pc_x - pr * 0.7, pc_y - pr), (pc_x - pr * 0.7, pc_y + pr), (pc_x + pr, pc_y)], fill=WHITE)


ICONS = {
    "start_all": ((52, 199, 89), (22, 140, 60), lambda d, col: glyph_play(d)),
    "stop_all": ((240, 82, 72), (180, 32, 38), lambda d, col: glyph_stop(d)),
    "restart_servers": ((255, 176, 46), (230, 116, 18), lambda d, col: glyph_restart(d)),
    "start_tunnel": ((150, 110, 245), (96, 60, 200), glyph_cloud),
    "run_app": ((64, 156, 255), (24, 96, 210), glyph_app),
}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, (top, bottom, draw) in ICONS.items():
        img = base(top, bottom)
        mid = tuple((top[i] + bottom[i]) // 2 for i in range(3)) + (255,)
        draw(ImageDraw.Draw(img), mid)
        img = img.resize((256, 256), Image.LANCZOS)
        img.save(OUT_DIR / f"{name}.ico", sizes=SIZES)
        print(f"wrote {OUT_DIR / (name + '.ico')}")


if __name__ == "__main__":
    main()
