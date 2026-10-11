#!/usr/bin/env python3
"""Generates the background of the Audiotext disk image.

Run it only when the design changes and commit the output:

    uv run --only-group dmg python packaging/macos/make_dmg_background.py

Produces dmg-background.png (660x400) and dmg-background@2x.png (1320x800). The
layout below is also the one of the window (see dmg_settings.py).
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 660, 400  # window size in points
ICON_SIZE = 128
APP_POS = (180, 215)  # center of the app icon
APPS_POS = (480, 215)  # center of the Applications folder
S = 4  # supersampling factor
FONTS = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/SFNS.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render(scale: int) -> Image.Image:
    k = S * scale
    img = Image.new("RGB", (W * k, H * k))

    # Vertical gradient background
    top, bottom = (250, 251, 255), (222, 227, 245)
    px = ImageDraw.Draw(img)
    for y in range(H * k):
        t = y / (H * k - 1)
        px.line(
            [(0, y), (W * k, y)],
            fill=tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3)),
        )

    # Soft glow behind each icon. The transparent pixels have its color, since the blur
    # would otherwise mix in black and turn it gray
    glow_color = (110, 125, 255)
    glow = Image.new("RGBA", img.size, (*glow_color, 0))
    g = ImageDraw.Draw(glow)
    for cx, cy in (APP_POS, APPS_POS):
        r = 95 * k
        g.ellipse(
            [cx * k - r, cy * k - r, cx * k + r, cy * k + r], fill=(*glow_color, 38)
        )
    glow = glow.filter(ImageFilter.GaussianBlur(40 * k))
    img.paste(glow, (0, 0), glow)

    d = ImageDraw.Draw(img, "RGBA")

    # Title and subtitle
    d.text(
        (W * k / 2, 60 * k),
        "Install Audiotext",
        font=font(26 * k),
        fill=(32, 36, 66, 255),
        anchor="mm",
    )
    d.text(
        (W * k / 2, 92 * k),
        "Drag the app into the Applications folder",
        font=font(13 * k),
        fill=(32, 36, 66, 150),
        anchor="mm",
    )

    # Arrow between the two icons
    y = APP_POS[1] * k
    gap = ICON_SIZE / 2 + 20
    x0, x1 = (APP_POS[0] + gap) * k, (APPS_POS[0] - gap) * k
    head = 22 * k
    thick = 7 * k
    color = (96, 108, 230, 255)
    d.rounded_rectangle(
        [x0, y - thick / 2, x1 - head + 2 * k, y + thick / 2],
        radius=thick / 2,
        fill=color,
    )
    d.polygon(
        [(x1 - head, y - head * 0.75), (x1, y), (x1 - head, y + head * 0.75)],
        fill=color,
    )

    return img.resize((W * scale, H * scale), Image.Resampling.LANCZOS)


if __name__ == "__main__":
    out = Path(__file__).parent
    render(1).save(out / "dmg-background.png")
    render(2).save(out / "dmg-background@2x.png")
    print("Generated dmg-background.png and dmg-background@2x.png")
