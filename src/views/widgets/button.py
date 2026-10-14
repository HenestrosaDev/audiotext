import sys
from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from views.localization import Text
from views.style import icons, theme
from views.widgets.tooltip import Tooltip


def set_button_state(button: ctk.CTkButton, state: str) -> None:
    """
    Enables or disables a button without making it flicker.

    CustomTkinter changes the cursor of the frame of the button with its state.
    On macOS, configuring that frame hides its text and image for a moment. The
    cursor is changed in its canvas and labels instead, which cover the frame.
    """
    if button.cget("state") == state:
        return

    button._cursor_manipulation_enabled = False
    button.configure(state=state)

    # The same cursors as CustomTkinter
    hand_cursor = {"darwin": "pointinghand", "win32": "hand2"}.get(sys.platform)
    if hand_cursor and button.cget("command") is not None:
        cursor = "arrow" if state == ctk.DISABLED else hand_cursor
        for widget in (button._canvas, button._text_label, button._image_label):
            if widget is not None:
                widget.configure(cursor=cursor)


class _RoundButton(ctk.CTkButton):  # type: ignore[misc]
    """
    A button as wide as it's tall, with its corners rounded into a circle.

    CTkButton keeps a margin as wide as its corner radius on each side of its
    content, which would make it wider than tall, so its corners would cover
    what's around it.
    """

    def _create_grid(self) -> None:
        super()._create_grid()
        minsize = self._apply_widget_scaling(self._border_width + 1)
        self.grid_columnconfigure(0, minsize=minsize)
        self.grid_columnconfigure(4, minsize=minsize)


def icon_button(
    master: Any,
    icon_name: str,
    command: Callable[[], Any],
    tooltip: Text,
    is_round: bool = False,
) -> ctk.CTkButton:
    """
    A small button with an icon, which shows what it does on hover.

    :param is_round: Whether it's a circle with a border, e.g. to float between
                     two panels.
    """
    size = 28
    style = (
        theme.SECONDARY_BUTTON | {"corner_radius": size // 2}
        if is_round
        else theme.GHOST_BUTTON
    )
    button = (_RoundButton if is_round else ctk.CTkButton)(
        master,
        text="",
        width=size,
        height=size,
        image=icons.icon(icon_name, 14),
        command=command,
        **style,
    )
    button._tooltip = Tooltip(button, tooltip)
    return button


def show_toggled(
    button: ctk.CTkButton, icon_name: str, is_on: bool, size: int = 14
) -> None:
    """Shows a button that turns an option on and off pressed while it's on."""
    button.configure(
        image=icons.icon(icon_name, size, theme.ACCENT_TEXT if is_on else theme.ICON),
        fg_color=theme.ROW_SELECTED if is_on else "transparent",
        text_color=theme.ACCENT_TEXT if is_on else theme.TEXT,
    )
    if button.cget("border_width"):
        button.configure(border_color=theme.ACCENT_TEXT if is_on else theme.CARD_BORDER)
