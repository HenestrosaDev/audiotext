from typing import Any

import customtkinter as ctk


def skip_forced_layout(widget: Any) -> None:
    """
    CustomTkinter's option menus and scrollbars call `update_idletasks()` on their
    canvas each time they're drawn, which lays out the whole window right away. A
    form with several of them took more than a second to appear, with the window
    frozen. Without it, Tk draws them on the next idle cycle, like other widgets.

    :param widget: An option menu or a scrollbar.
    """
    widget._canvas.update_idletasks = lambda: None


class CTkOptionMenu(ctk.CTkOptionMenu):  # type: ignore[misc]
    """Option menu that doesn't lay out the whole window when it's drawn."""

    def _draw(self, no_color_updates: bool = False) -> None:
        # Called from the parent's constructor, so it can't be done before
        skip_forced_layout(self)
        super()._draw(no_color_updates)


class CTkScrollbar(ctk.CTkScrollbar):  # type: ignore[misc]
    """Scrollbar that doesn't lay out the whole window when it's drawn."""

    def _draw(self, no_color_updates: bool = False) -> None:
        # Called from the parent's constructor, so it can't be done before
        skip_forced_layout(self)
        super()._draw(no_color_updates)


def skip_scrollbar_forced_layout(frame: ctk.CTkScrollableFrame) -> None:
    """The scrollbar is redrawn each time the content of the frame changes."""
    skip_forced_layout(frame._scrollbar)
