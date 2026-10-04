"""
Colors, fonts and sizes shared by the views. Colors are (light, dark) pairs, as
CustomTkinter expects them.
"""

import sys
import tkinter
import zlib

import customtkinter as ctk

from utils.enums import Color

ColorPair = tuple[str, str]

TEXT: ColorPair = ("gray10", "gray92")
HINT_TEXT: ColorPair = (Color.LIGHT_HINT_TEXT.value, Color.DARK_HINT_TEXT.value)
ERROR_TEXT: ColorPair = (Color.LIGHT_ERROR_TEXT.value, Color.DARK_ERROR_TEXT.value)
SUCCESS_TEXT: ColorPair = ("#1E7B34", "#4CD964")

WINDOW_BG: ColorPair = ("#F5F5F7", "#1E1E20")
SIDEBAR_BG: ColorPair = ("#EBEBEF", "#252528")
TOPBAR_BG: ColorPair = ("#FBFBFD", "#2B2B2F")
CARD_BG: ColorPair = ("#FFFFFF", "#2A2A2D")
CARD_BORDER: ColorPair = ("#DEDEE3", "#3A3A3F")
SUBTLE_BG: ColorPair = ("#F0F0F4", "#323236")
DIVIDER: ColorPair = ("#D8D8DE", "#3A3A3F")

ROW_HOVER: ColorPair = ("#DEDEE5", "#313136")
ROW_SELECTED: ColorPair = ("#CFE0FA", "#284A75")

ACCENT: ColorPair = (Color.LIGHT_BLUE.value, Color.DARK_BLUE.value)
ACCENT_HOVER: ColorPair = (Color.HOVER_LIGHT_BLUE.value, Color.HOVER_DARK_BLUE.value)
ACCENT_TEXT: ColorPair = ("#1F6AA5", "#6CB4F0")

NOTE_BG: ColorPair = ("#FFF6D6", "#3F3720")
NOTE_BORDER: ColorPair = ("#F0DC8C", "#6B5B24")

DANGER: ColorPair = (Color.LIGHT_RED.value, Color.DARK_RED.value)
DANGER_HOVER: ColorPair = (Color.HOVER_LIGHT_RED.value, Color.HOVER_DARK_RED.value)
PRIMARY: ColorPair = (Color.LIGHT_GREEN.value, Color.DARK_GREEN.value)
PRIMARY_HOVER: ColorPair = (Color.HOVER_LIGHT_GREEN.value, Color.HOVER_DARK_GREEN.value)

ICON: ColorPair = ("#3C3C43", "#D1D1D6")
ICON_MUTED: ColorPair = ("#8E8E93", "#8E8E93")
ICON_ON_ACCENT: ColorPair = ("#FFFFFF", "#FFFFFF")

STATUS_DONE: ColorPair = ("#28A745", "#30D158")
STATUS_PROCESSING: ColorPair = ("#0A84FF", "#409CFF")
STATUS_QUEUED: ColorPair = ("#8E8E93", "#98989D")
STATUS_FAILED: ColorPair = ("#E5383B", "#FF6961")
STATUS_CANCELLED: ColorPair = ("#D97C00", "#FFB340")
STATUS_WATCHING: ColorPair = ("#9B51E0", "#BF7AF0")

# Background and text colors of the tags, chosen from the name of the tag
TAG_COLORS: list[tuple[ColorPair, ColorPair]] = [
    (("#DCEBFF", "#1D3A5C"), ("#0B4F9C", "#9CCBFF")),
    (("#DDF5E3", "#1C4228"), ("#1A6B32", "#8FE0A5")),
    (("#FDE7D9", "#4D2E1A"), ("#9A4A12", "#FFC08F")),
    (("#F3E1FA", "#3D2449"), ("#7A2E99", "#E2A8F7")),
    (("#FFF1C7", "#4A3D12"), ("#7D5E00", "#FFD966")),
    (("#DDF3F5", "#163F44"), ("#0E6670", "#8EDDE6")),
    (("#FBDDE6", "#4A1E2C"), ("#A0244F", "#FFA3C0")),
]
DEFAULT_TAG_COLORS: tuple[ColorPair, ColorPair] = (SUBTLE_BG, HINT_TEXT)

PRIMARY_BUTTON = {"fg_color": PRIMARY, "hover_color": PRIMARY_HOVER}
DANGER_BUTTON = {"fg_color": DANGER, "hover_color": DANGER_HOVER}
SECONDARY_BUTTON = {
    "fg_color": "transparent",
    "border_width": 1,
    "border_color": CARD_BORDER,
    "text_color": TEXT,
    "hover_color": ROW_HOVER,
}
GHOST_BUTTON = {
    "fg_color": "transparent",
    "text_color": TEXT,
    "hover_color": ROW_HOVER,
}

IS_MACOS = sys.platform == "darwin"
SHORTCUT_MODIFIER = "Command" if IS_MACOS else "Control"
SHORTCUT_MODIFIER_LABEL = "⌘" if IS_MACOS else "Ctrl+"
# Right click (and the two-finger tap of a trackpad) is <Button-3>, except on macOS
# with Tk 8.6 and older, where it's <Button-2>
_RIGHT_CLICK_EVENT = (
    "<Button-2>" if IS_MACOS and tkinter.TkVersion < 8.7 else "<Button-3>"
)
CONTEXT_MENU_EVENTS = (
    (_RIGHT_CLICK_EVENT, "<Control-Button-1>") if IS_MACOS else (_RIGHT_CLICK_EVENT,)
)

SIDEBAR_WIDTH = 290
SIDEBAR_MIN_WIDTH = 220
SIDEBAR_MAX_WIDTH = 560
MONOSPACE_FAMILY = (
    "Menlo" if IS_MACOS else "Consolas" if sys.platform == "win32" else "monospace"
)


def tag_colors(tag: str) -> tuple[ColorPair, ColorPair]:
    """
    :return: The background and text colors of a tag. The same tag always has
             the same colors.
    """
    if not tag:
        return DEFAULT_TAG_COLORS

    return TAG_COLORS[zlib.crc32(tag.casefold().encode()) % len(TAG_COLORS)]


def font(
    size: int = 13, weight: str = "normal", family: str | None = None
) -> ctk.CTkFont:
    if family:
        return ctk.CTkFont(family=family, size=size, weight=weight)

    return ctk.CTkFont(size=size, weight=weight)


def fit_text(text: str, text_font: ctk.CTkFont, max_width: int) -> str:
    """
    Shortens a text with an ellipsis so that it fits in the given width, since
    Tk labels can't do it.
    """
    if max_width <= 0 or text_font.measure(text) <= max_width:
        return text

    ellipsis = "…"
    low, high = 0, len(text)

    # Binary search of the longest prefix that fits
    while low < high:
        middle = (low + high + 1) // 2
        if text_font.measure(text[:middle] + ellipsis) <= max_width:
            low = middle
        else:
            high = middle - 1

    return text[:low].rstrip() + ellipsis
