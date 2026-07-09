#!/usr/bin/env python3
"""Generate brand assets: favicon PNGs + Open Graph social card.

Outputs (in assets/):
  favicon.svg           vector favicon (hand-authored below)
  favicon-192.png       Google-friendly favicon
  favicon-32.png        classic tab icon
  apple-touch-icon.png  180x180
  og-card.png           1200x630 social share card (LinkedIn/Bluesky/etc.)

Run: python3 pipeline/build_assets.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

NAVY = (22, 46, 81)        # #162e51
NAVY_DK = (14, 30, 55)
BLUE = (26, 68, 128)       # #1a4480
GOLD = (255, 190, 46)      # #ffbe2e
WHITE = (255, 255, 255)
MIST = (184, 201, 224)     # #b8c9e0

FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_REG = "/System/Library/Fonts/Supplemental/Arial.ttf"


def font(path, size):
    return ImageFont.truetype(path, size)


def rounded(draw, xy, radius, fill):
    draw.rounded_rectangle(xy, radius=radius, fill=fill)


# ---------------- favicon ----------------
FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="14" fill="#162e51"/>
  <rect x="0" y="0" width="64" height="6" rx="3" fill="#ffbe2e"/>
  <text x="32" y="45" font-family="Arial, Helvetica, sans-serif" font-size="30"
        font-weight="bold" text-anchor="middle" fill="#ffbe2e">RE</text>
</svg>
"""


def make_favicon(size, out):
    s = size * 4  # supersample
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rounded(d, (0, 0, s - 1, s - 1), radius=int(s * 0.22), fill=NAVY)
    # gold top bar
    d.rounded_rectangle((0, 0, s - 1, int(s * 0.11)), radius=int(s * 0.05), fill=GOLD)
    f = font(FONT_BOLD, int(s * 0.47))
    d.text((s / 2, s * 0.58), "RE", font=f, fill=GOLD, anchor="mm")
    img = img.resize((size, size), Image.LANCZOS)
    img.save(out)
    print("wrote", out)


# ---------------- og card ----------------
def make_og_card(out):
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(img)

    # subtle vertical gradient
    for y in range(H):
        t = y / H
        c = tuple(int(NAVY[i] + (NAVY_DK[i] - NAVY[i]) * t) for i in range(3))
        d.line([(0, y), (W, y)], fill=c)

    # gold top bar
    d.rectangle((0, 0, W, 14), fill=GOLD)

    # faint oversized watermark seal, right side
    d.ellipse((W - 380, H - 380, W + 120, H + 120), outline=(38, 66, 108), width=26)
    d.ellipse((W - 320, H - 320, W + 60, H + 60), outline=(32, 58, 98), width=18)

    # seal
    cx, cy, r = 132, 150, 56
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=GOLD)
    d.text((cx, cy + 4), "RE", font=font(FONT_BOLD, 52), fill=NAVY, anchor="mm")

    # unofficial tag
    tag_f = font(FONT_BOLD, 26)
    tw = d.textlength("UNOFFICIAL COMMUNITY GUIDE", font=tag_f)
    d.rounded_rectangle((214, 118, 214 + tw + 44, 182), radius=14, outline=GOLD, width=3)
    d.text((214 + 22, 150), "UNOFFICIAL COMMUNITY GUIDE", font=tag_f, fill=GOLD, anchor="lm")

    # title
    t1 = font(FONT_BOLD, 78)
    d.text((76, 268), "NSF Restricted", font=t1, fill=WHITE, anchor="lm")
    d.text((76, 358), "Entities Guide", font=t1, fill=WHITE, anchor="lm")

    # subtitle
    sub = font(FONT_REG, 34)
    d.text((76, 448), "Search 5,900+ entries across all 13 U.S. restricted party lists", font=sub, fill=MIST, anchor="lm")
    d.text((76, 496), "named in NSF's FY2027 collaboration prohibition", font=sub, fill=MIST, anchor="lm")

    # url footer
    d.rectangle((0, H - 62, W, H), fill=NAVY_DK)
    d.text((76, H - 31), "curtishoffmann.com/nsfreg", font=font(FONT_BOLD, 30), fill=GOLD, anchor="lm")
    d.text((W - 76, H - 31), "Verify everything at the official sources", font=font(FONT_REG, 24), fill=MIST, anchor="rm")

    img.save(out, optimize=True)
    print("wrote", out, f"({Path(out).stat().st_size // 1024} KB)")


if __name__ == "__main__":
    (ASSETS / "favicon.svg").write_text(FAVICON_SVG, encoding="utf-8")
    print("wrote", ASSETS / "favicon.svg")
    make_favicon(192, ASSETS / "favicon-192.png")
    make_favicon(32, ASSETS / "favicon-32.png")
    make_favicon(180, ASSETS / "apple-touch-icon.png")
    make_og_card(ASSETS / "og-card.png")
