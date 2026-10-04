import sys
import tkinter as tk
from typing import Any

import customtkinter as ctk

# Tk 9 reports the trackpad as `<TouchpadScroll>` events with the distance in
# pixels, and the mouse wheel in multiples of 120 per notch, like on Windows.
# CustomTkinter only handles the events of Tk 8.6, so the trackpad didn't scroll
# and a notch of the mouse wheel scrolled almost a thousand pixels on macOS
_PRECISE_SCROLLING = tk.TkVersion >= 9 and not sys.platform.startswith("win")

# Pixels scrolled by each notch of the mouse wheel, like Tk's text widgets
_PIXELS_PER_NOTCH = 30
_WHEEL_DELTA_PER_NOTCH = 120


class CTkScrollableFrame(ctk.CTkScrollableFrame):  # type: ignore[misc]
    """Scrollable frame that scrolls with the trackpad and the mouse on Tk 9."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        if _PRECISE_SCROLLING:
            self.bind_all("<TouchpadScroll>", self._touchpad_scroll_all, add=True)
            if sys.platform.startswith("linux"):
                # X11 sends `<MouseWheel>` instead of buttons 4 and 5 since Tk 9
                self.bind_all("<MouseWheel>", self._mouse_wheel_all, add=True)

    def _set_scroll_increments(self) -> None:
        if _PRECISE_SCROLLING:
            # A unit is a pixel, so the trackpad scrolls as much as the fingers
            self._parent_canvas.configure(xscrollincrement=1, yscrollincrement=1)
        else:
            super()._set_scroll_increments()

    def _mouse_wheel_all(self, event: tk.Event) -> None:
        if not _PRECISE_SCROLLING:
            super()._mouse_wheel_all(event)
            return

        pixels = round(-event.delta * _PIXELS_PER_NOTCH / _WHEEL_DELTA_PER_NOTCH)
        if self._shift_pressed:
            self._scroll_by_pixels(event.widget, pixels, 0)
        else:
            self._scroll_by_pixels(event.widget, 0, pixels)

    def _touchpad_scroll_all(self, event: tk.Event) -> None:
        # The horizontal distance is in the high 16 bits and the vertical one in
        # the low 16 bits, both signed
        delta_x = event.delta >> 16
        delta_y = event.delta & 0xFFFF
        if delta_y >= 0x8000:
            delta_y -= 0x10000
        self._scroll_by_pixels(event.widget, -delta_x, -delta_y)

    def _scroll_by_pixels(self, widget: Any, pixels_x: int, pixels_y: int) -> None:
        if not self._check_if_valid_scroll(widget):
            return
        if pixels_x and self._parent_canvas.xview() != (0.0, 1.0):
            self._parent_canvas.xview("scroll", pixels_x, "units")
        if pixels_y and self._parent_canvas.yview() != (0.0, 1.0):
            self._parent_canvas.yview("scroll", pixels_y, "units")
