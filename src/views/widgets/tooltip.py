"""
A short text shown below a widget while the pointer is over it, e.g. what an
icon button does.
"""

import contextlib
import tkinter as tk
from typing import Any

import customtkinter as ctk

from views.localization import Text
from views.style import theme

TOOLTIP_DELAY_MS = 500
# (light, dark) colors, inverted from the ones of the window so it stands out
TOOLTIP_BG = ("#3A3A3F", "#E5E5EA")
TOOLTIP_TEXT = ("#FFFFFF", "#1C1C1E")


class Tooltip:
    def __init__(self, widget: Any, text: Text) -> None:
        """
        :param text: Called each time it's shown, so it's in the current interface
                     language.
        """
        self._widget = widget
        self._text = text
        self._after_id: str | None = None
        self._window: tk.Toplevel | None = None

        widget.bind("<Enter>", lambda _event: self._schedule(), add="+")
        widget.bind("<Leave>", lambda _event: self.hide(), add="+")
        # Clicking it (e.g. a button) does what it says, so it's no longer needed
        widget.bind("<ButtonPress>", lambda _event: self.hide(), add="+")
        widget.bind("<Destroy>", lambda _event: self.hide(), add="+")

    def hide(self) -> None:
        if self._after_id:
            self._widget.after_cancel(self._after_id)
            self._after_id = None
        if self._window:
            self._window.destroy()
            self._window = None

    def _schedule(self) -> None:
        self.hide()
        self._after_id = self._widget.after(TOOLTIP_DELAY_MS, self._show)

    def _show(self) -> None:
        self._after_id = None
        widget = self._widget
        if not widget.winfo_exists() or not widget.winfo_viewable():
            return

        is_dark = ctk.get_appearance_mode() == "Dark"
        background = TOOLTIP_BG[is_dark]
        window = tk.Toplevel(widget)
        window.wm_overrideredirect(True)
        if theme.IS_MACOS:
            # Without a frame or a shadow, and without taking the focus
            with contextlib.suppress(tk.TclError):
                window.tk.call(
                    "::tk::unsupported::MacWindowStyle",
                    "style",
                    window._w,  # type: ignore[attr-defined]
                    "help",
                    "noActivates",
                )
        window.configure(background=background)
        tk.Label(
            window,
            text=self._text(),
            background=background,
            foreground=TOOLTIP_TEXT[is_dark],
            font=theme.font(12),
            padx=8,
            pady=4,
        ).pack()
        window.update_idletasks()

        # Centered below the widget, within the screen
        width = window.winfo_reqwidth()
        x = widget.winfo_rootx() + (widget.winfo_width() - width) // 2
        x = max(0, min(x, widget.winfo_screenwidth() - width))
        y = widget.winfo_rooty() + widget.winfo_height() + 4
        window.wm_geometry(f"+{x}+{y}")
        self._window = window
