"""
Icons drawn with Pillow, so they're sharp at any size and follow the light and
dark themes without image files. Each icon is drawn in white on a 64×64 mask and
tinted with the requested colors.
"""

from collections.abc import Callable
from functools import cache

import customtkinter as ctk
from PIL import Image, ImageColor, ImageDraw

import utils.path_helper as ph
from views.style import theme

CANVAS = 64
STROKE = 5
ON = 255
OFF = 0

Draw = ImageDraw.ImageDraw


def _line(d: Draw, points: list[tuple[float, float]], width: int = STROKE) -> None:
    d.line(points, fill=ON, width=width, joint="curve")
    # Round the ends of the line
    radius = width / 2
    for x, y in (points[0], points[-1]):
        d.ellipse((x - radius, y - radius, x + radius, y + radius), fill=ON)


def _file(d: Draw) -> None:
    _line(d, [(38, 7), (15, 7), (15, 57), (49, 57), (49, 18), (38, 7)])
    _line(d, [(38, 7), (38, 18), (49, 18)])
    for y, end in ((31, 41), (40, 41), (49, 34)):
        _line(d, [(22, y), (end, y)], width=4)


def _link_layer() -> Image.Image:
    layer = Image.new("L", (CANVAS, CANVAS), OFF)
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((3, 21, 37, 43), radius=11, outline=ON, width=STROKE)
    d.rounded_rectangle((27, 21, 61, 43), radius=11, outline=ON, width=STROKE)
    return layer.rotate(45, resample=Image.Resampling.BICUBIC)


def _mic(d: Draw) -> None:
    d.rounded_rectangle((22, 4, 42, 38), radius=10, outline=ON, width=STROKE)
    d.arc((11, 16, 53, 50), start=0, end=180, fill=ON, width=STROKE)
    _line(d, [(32, 50), (32, 58)])
    _line(d, [(21, 58), (43, 58)])


def _folder(d: Draw) -> None:
    _line(d, [(7, 52), (7, 13), (25, 13), (31, 20), (57, 20), (57, 52), (7, 52)])
    _line(d, [(7, 27), (57, 27)], width=4)


def _sidebar(d: Draw) -> None:
    d.rounded_rectangle((6, 11, 58, 53), radius=8, outline=ON, width=STROKE)
    _line(d, [(25, 12), (25, 52)])
    for y in (21, 29):
        _line(d, [(12, y), (18, y)], width=4)


def _gear(d: Draw) -> None:
    import math

    for idx in range(8):
        angle = idx * math.pi / 4
        x1, y1 = 32 + 17 * math.cos(angle), 32 + 17 * math.sin(angle)
        x2, y2 = 32 + 27 * math.cos(angle), 32 + 27 * math.sin(angle)
        d.line([(x1, y1), (x2, y2)], fill=ON, width=10)
    d.ellipse((12, 12, 52, 52), fill=ON)
    d.ellipse((23, 23, 41, 41), fill=OFF)


def _plus(d: Draw) -> None:
    _line(d, [(32, 12), (32, 52)])
    _line(d, [(12, 32), (52, 32)])


def _search(d: Draw) -> None:
    d.ellipse((8, 8, 42, 42), outline=ON, width=STROKE)
    _line(d, [(40, 40), (55, 55)], width=6)


def _pin_layer() -> Image.Image:
    layer = Image.new("L", (CANVAS, CANVAS), OFF)
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((22, 5, 42, 13), radius=3, fill=ON)
    d.polygon([(25, 12), (39, 12), (41, 30), (23, 30)], fill=ON)
    d.rounded_rectangle((14, 29, 50, 36), radius=3, fill=ON)
    _line(d, [(32, 36), (32, 59)], width=4)
    return layer.rotate(-35, resample=Image.Resampling.BICUBIC)


def _note(d: Draw) -> None:
    _line(d, [(42, 55), (10, 55), (10, 9), (54, 9), (54, 43), (42, 55)])
    _line(d, [(42, 55), (42, 43), (54, 43)])
    _line(d, [(18, 22), (46, 22)], width=4)
    _line(d, [(18, 32), (38, 32)], width=4)


def _chevron_right(d: Draw) -> None:
    _line(d, [(24, 14), (42, 32), (24, 50)], width=6)


def _chevron_down(d: Draw) -> None:
    _line(d, [(14, 24), (32, 42), (50, 24)], width=6)


def _chevron_left(d: Draw) -> None:
    _line(d, [(40, 14), (22, 32), (40, 50)], width=6)


def _play(d: Draw) -> None:
    d.polygon([(19, 10), (54, 32), (19, 54)], fill=ON)


def _pause(d: Draw) -> None:
    d.rounded_rectangle((15, 10, 27, 54), radius=3, fill=ON)
    d.rounded_rectangle((37, 10, 49, 54), radius=3, fill=ON)


def _check(d: Draw) -> None:
    _line(d, [(13, 34), (27, 47), (51, 19)], width=6)


def _check_circle(d: Draw) -> None:
    d.ellipse((4, 4, 60, 60), fill=ON)
    d.line([(19, 33), (28, 42), (45, 23)], fill=OFF, width=7, joint="curve")


def _x_circle(d: Draw) -> None:
    d.ellipse((4, 4, 60, 60), fill=ON)
    d.line([(22, 22), (42, 42)], fill=OFF, width=7)
    d.line([(42, 22), (22, 42)], fill=OFF, width=7)


def _alert_circle(d: Draw) -> None:
    d.ellipse((4, 4, 60, 60), fill=ON)
    d.rounded_rectangle((28, 15, 36, 38), radius=4, fill=OFF)
    d.ellipse((27, 42, 37, 52), fill=OFF)


def _clock(d: Draw) -> None:
    d.ellipse((6, 6, 58, 58), outline=ON, width=STROKE)
    _line(d, [(32, 17), (32, 33), (43, 40)])


def _calendar(d: Draw) -> None:
    d.rounded_rectangle((7, 11, 57, 57), radius=7, outline=ON, width=STROKE)
    _line(d, [(8, 25), (56, 25)], width=4)
    for x in (21, 43):
        _line(d, [(x, 5), (x, 15)])
    for x, y in ((21, 36), (32, 36), (43, 36), (21, 46), (32, 46)):
        d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=ON)


def _globe(d: Draw) -> None:
    d.ellipse((6, 6, 58, 58), outline=ON, width=STROKE)
    d.ellipse((21, 6, 43, 58), outline=ON, width=4)
    _line(d, [(8, 32), (56, 32)], width=4)


def _chip(d: Draw) -> None:
    d.rounded_rectangle((15, 15, 49, 49), radius=6, outline=ON, width=STROKE)
    d.rounded_rectangle((25, 25, 39, 39), radius=2, fill=ON)
    for offset in (24, 32, 40):
        _line(d, [(offset, 6), (offset, 13)], width=4)
        _line(d, [(offset, 51), (offset, 58)], width=4)
        _line(d, [(6, offset), (13, offset)], width=4)
        _line(d, [(51, offset), (58, offset)], width=4)


def _eye(d: Draw) -> None:
    d.chord((2, 12, 62, 72), start=200, end=340, fill=ON)
    d.chord((2, -8, 62, 52), start=20, end=160, fill=ON)
    d.ellipse((10, 19, 54, 45), fill=OFF)
    d.ellipse((22, 20, 42, 44), fill=ON)
    d.ellipse((28, 26, 36, 38), fill=OFF)


def _copy(d: Draw) -> None:
    d.rounded_rectangle((20, 18, 56, 58), radius=6, outline=ON, width=STROKE)
    _line(d, [(12, 44), (8, 44), (8, 8), (40, 8), (40, 12)])


def _export(d: Draw) -> None:
    _line(d, [(32, 8), (32, 38)])
    _line(d, [(20, 20), (32, 8), (44, 20)])
    _line(d, [(10, 34), (10, 56), (54, 56), (54, 34)])


def _import(d: Draw) -> None:
    _line(d, [(32, 6), (32, 38)])
    _line(d, [(20, 26), (32, 38), (44, 26)])
    _line(d, [(10, 34), (10, 56), (54, 56), (54, 34)])


def _trash(d: Draw) -> None:
    _line(d, [(9, 15), (55, 15)])
    _line(d, [(24, 15), (26, 7), (38, 7), (40, 15)], width=4)
    _line(d, [(15, 15), (19, 57), (45, 57), (49, 15)])
    for x in (27, 37):
        _line(d, [(x, 26), (x, 47)], width=4)


def _record(d: Draw) -> None:
    d.ellipse((10, 10, 54, 54), fill=ON)


def _stop(d: Draw) -> None:
    d.rounded_rectangle((14, 14, 50, 50), radius=7, fill=ON)


def _waveform(d: Draw) -> None:
    for x, height in ((10, 10), (20, 24), (30, 40), (40, 20), (50, 30)):
        d.rounded_rectangle(
            (x - 3, 32 - height / 2 - 3, x + 3, 32 + height / 2 + 3), radius=3, fill=ON
        )


def _tag(d: Draw) -> None:
    _line(d, [(8, 8), (30, 8), (57, 35), (35, 57), (8, 30), (8, 8)])
    d.ellipse((17, 17, 25, 25), fill=ON)


def _more(d: Draw) -> None:
    for x in (14, 32, 50):
        d.ellipse((x - 5, 27, x + 5, 37), fill=ON)


def _pencil(d: Draw) -> None:
    d.polygon(
        [(42, 8), (56, 22), (24, 54), (10, 54), (10, 40)], outline=ON, width=STROKE
    )
    _line(d, [(36, 14), (50, 28)])


def _refresh(d: Draw) -> None:
    d.arc((10, 10, 54, 54), start=40, end=330, fill=ON, width=STROKE)
    d.polygon([(55, 6), (57, 28), (36, 22)], fill=ON)


def _subtitles(d: Draw) -> None:
    d.rounded_rectangle((5, 12, 59, 52), radius=8, outline=ON, width=STROKE)
    _line(d, [(14, 34), (26, 34)], width=4)
    _line(d, [(32, 34), (50, 34)], width=4)
    _line(d, [(14, 43), (38, 43)], width=4)


def _text_lines(d: Draw) -> None:
    for y, end in ((14, 54), (26, 54), (38, 54), (50, 38)):
        _line(d, [(10, y), (end, y)])


def _book(d: Draw) -> None:
    _line(d, [(32, 16), (22, 11), (7, 11), (7, 50), (22, 50), (32, 55)])
    _line(d, [(32, 16), (42, 11), (57, 11), (57, 50), (42, 50), (32, 55)])
    _line(d, [(32, 16), (32, 55)])


def _github(d: Draw) -> None:
    # The GitHub mark: a cat silhouette cut out of a circle
    d.ellipse((2, 2, 62, 62), fill=ON)
    d.ellipse((13, 17, 51, 45), fill=OFF)
    d.polygon([(15, 28), (16, 10), (28, 18)], fill=OFF)
    d.polygon([(49, 28), (48, 10), (36, 18)], fill=OFF)
    d.polygon([(26, 42), (38, 42), (39, 62), (25, 62)], fill=OFF)
    d.arc((10, 36, 28, 54), start=90, end=210, fill=OFF, width=4)
    d.line([(19, 52), (27, 52)], fill=OFF, width=4)


def _heart(d: Draw) -> None:
    d.ellipse((5, 9, 35, 39), fill=ON)
    d.ellipse((29, 9, 59, 39), fill=ON)
    d.polygon([(9.4, 34.6), (32, 57), (54.6, 34.6), (32, 22)], fill=ON)


ICONS: dict[str, Callable[[Draw], None]] = {
    "file": _file,
    "mic": _mic,
    "folder": _folder,
    "sidebar": _sidebar,
    "gear": _gear,
    "plus": _plus,
    "search": _search,
    "note": _note,
    "chevron_right": _chevron_right,
    "chevron_down": _chevron_down,
    "chevron_left": _chevron_left,
    "play": _play,
    "pause": _pause,
    "check": _check,
    "check_circle": _check_circle,
    "x_circle": _x_circle,
    "alert_circle": _alert_circle,
    "clock": _clock,
    "calendar": _calendar,
    "globe": _globe,
    "chip": _chip,
    "eye": _eye,
    "copy": _copy,
    "export": _export,
    "import": _import,
    "trash": _trash,
    "record": _record,
    "stop": _stop,
    "waveform": _waveform,
    "tag": _tag,
    "more": _more,
    "pencil": _pencil,
    "refresh": _refresh,
    "subtitles": _subtitles,
    "text": _text_lines,
    "book": _book,
    "github": _github,
    "heart": _heart,
}
LAYER_ICONS: dict[str, Callable[[], Image.Image]] = {
    "link": _link_layer,
    "pin": _pin_layer,
}
SPINNER_FRAMES = 12


@cache
def _mask(name: str) -> Image.Image:
    if name in LAYER_ICONS:
        return LAYER_ICONS[name]()

    if name.startswith("spinner_"):
        angle = int(name.removeprefix("spinner_")) * 360 // SPINNER_FRAMES
        mask = Image.new("L", (CANVAS, CANVAS), OFF)
        ImageDraw.Draw(mask).arc(
            (7, 7, 57, 57), start=angle, end=angle + 270, fill=ON, width=8
        )
        return mask

    mask = Image.new("L", (CANVAS, CANVAS), OFF)
    ICONS[name](ImageDraw.Draw(mask))
    return mask


def _tint(mask: Image.Image, color: str) -> Image.Image:
    image = Image.new("RGBA", mask.size, color)
    image.putalpha(mask)
    return image


def _resolve(color: str) -> str:
    """Converts Tk color names (e.g. "gray92") to a color Pillow understands."""
    try:
        ImageColor.getrgb(color)
        return color
    except ValueError:
        import tkinter

        red, green, blue = tkinter._default_root.winfo_rgb(color)  # type: ignore[attr-defined]
        return f"#{red >> 8:02x}{green >> 8:02x}{blue >> 8:02x}"


@cache
def icon(
    name: str, size: int = 18, color: theme.ColorPair = theme.ICON
) -> ctk.CTkImage:
    """
    :param name: A key of `ICONS` or `LAYER_ICONS`, or `spinner_<frame>`.
    :param size: The size in points. The image is downscaled from a larger one,
                 so it's sharp on HiDPI screens.
    :param color: The (light, dark) colors of the icon.
    """
    mask = _mask(name)
    light, dark = color
    return ctk.CTkImage(
        light_image=_tint(mask, _resolve(light)),
        dark_image=_tint(mask, _resolve(dark)),
        size=(size, size),
    )


@cache
def app_logo(size: int, color: theme.ColorPair = theme.ICON) -> ctk.CTkImage:
    """
    The app logo as a single-color silhouette, tinted like the other icons.

    :param size: The size in points.
    :param color: The (light, dark) colors of the logo.
    """
    mask = Image.open(ph.ROOT_PATH / "res/img/icon-light.png").getchannel("A")
    light, dark = color
    return ctk.CTkImage(
        light_image=_tint(mask, _resolve(light)),
        dark_image=_tint(mask, _resolve(dark)),
        size=(size, size),
    )


def spinner(
    frame: int, size: int = 14, color: theme.ColorPair = theme.STATUS_PROCESSING
) -> ctk.CTkImage:
    return icon(f"spinner_{frame % SPINNER_FRAMES}", size, color)
