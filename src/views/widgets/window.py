"""Helpers to place the windows of the interface."""

import logging
import re
from typing import Any

import customtkinter as ctk

import utils.config_manager as cm
from models.config.config_system import ConfigSystem

# Pixels of a window that must be on the screen to restore its position
VISIBLE_WINDOW_MARGIN = 100
# Time a dialog must stay still after it's moved before its position is stored
POSITION_SAVE_DELAY_MS = 500

logger = logging.getLogger(__name__)


def is_on_screen(
    window: tuple[int, int, int, int], screen_size: tuple[int, int]
) -> bool:
    """
    Whether a part of the window big enough to drag it would be visible. Tk only
    knows the size of the main screen, so the windows on the other screens are
    accepted if they are close enough: up to two screens to the left or to the
    right, and one screen above or below. The screens to the left of or above the
    main screen have negative coordinates.

    :param window: The width, height, x and y of the window.
    :param screen_size: The width and height of the main screen.
    """
    width, height, x, y = window
    screen_width, screen_height = screen_size
    return bool(
        -screen_width * 2 + VISIBLE_WINDOW_MARGIN < x + width
        and x < screen_width * 3 - VISIBLE_WINDOW_MARGIN
        and -screen_height + VISIBLE_WINDOW_MARGIN < y + height
        and y < screen_height * 2 - VISIBLE_WINDOW_MARGIN
    )


def place_dialog(
    window: ctk.CTkToplevel,
    master: Any,
    width: int | None = None,
    height: int | None = None,
) -> None:
    """
    Shows a new dialog where the user last moved one of its kind, or centered over
    the window of `master` if it was never moved or that place is off the screen,
    instead of near the top left corner of the screen, where Tk places it. Then,
    remembers where the user moves it.

    The window must be hidden with `withdraw` right after it's created, because
    some widgets (e.g. the option menus) update the layout while they're built,
    which would show it in that corner before it's moved.

    :param width: The size of the window when it's fixed with `geometry`, which
                  Tk doesn't report until it's shown. Defaults to the size its
                  widgets need.
    """
    window.update_idletasks()
    scaling = ctk.ScalingTracker.get_window_scaling(window)
    window_width = round(width * scaling) if width else window.winfo_reqwidth()
    window_height = round(height * scaling) if height else window.winfo_reqheight()

    name = type(window).__name__
    screen_size = (window.winfo_screenwidth(), window.winfo_screenheight())
    position = _saved_positions().get(name)
    if not position or not is_on_screen(
        (window_width, window_height, *position), screen_size
    ):
        owner = master.winfo_toplevel()
        x = owner.winfo_rootx() + (owner.winfo_width() - window_width) // 2
        y = owner.winfo_rooty() + (owner.winfo_height() - window_height) // 2
        # Keeps it on the screen if the owner is partly off it
        x = max(0, min(x, screen_size[0] - window_width))
        y = max(0, min(y, screen_size[1] - window_height))
        position = (x, y)

    size = f"{width}x{height}" if width and height else ""
    window.geometry(f"{size}+{position[0]}+{position[1]}")
    window.deiconify()
    _remember_moves(window, name, position)


def _remember_moves(
    window: ctk.CTkToplevel, name: str, position: tuple[int, int]
) -> None:
    """Stores the position of a dialog when the user moves it."""
    saved_position = current_position = position
    save_job: str | None = None

    def save() -> None:
        nonlocal saved_position, save_job
        save_job = None
        if current_position != saved_position:
            _save_position(name, current_position)
            saved_position = current_position

    def on_configure(event: Any) -> None:
        nonlocal current_position, save_job
        # The event is also received for every widget of the window
        if event.widget is not window:
            return
        # `geometry` of CustomTkinter would scale it
        current_position = _parse_position(window.wm_geometry()) or current_position
        # The window sends an event for every step while it's moved
        if save_job:
            window.after_cancel(save_job)
        save_job = window.after(POSITION_SAVE_DELAY_MS, save)

    def on_destroy(event: Any) -> None:
        # Closed right after it's moved
        if event.widget is window and save_job:
            window.after_cancel(save_job)
            save()

    window.bind("<Configure>", on_configure, add="+")
    window.bind("<Destroy>", on_destroy, add="+")


def _parse_position(text: str) -> tuple[int, int] | None:
    """
    Parses the position at the end of a Tk geometry, like "+100+-50" or
    "440x146+100+-50".
    """
    match = re.search(r"([+-]-?\d+)([+-]-?\d+)$", text.strip())
    if not match:
        return None
    # Tk writes "+-10" for a negative position
    return int(match[1].replace("+-", "-")), int(match[2].replace("+-", "-"))


def _saved_positions() -> dict[str, tuple[int, int]]:
    """:return: The position of each dialog the user moved, by its class name."""
    positions = {}
    for item in cm.ConfigManager.get_config_system().dialog_positions:
        name, _sign, position = item.partition("+")
        if parsed := _parse_position(f"+{position}"):
            positions[name] = parsed
    return positions


def _save_position(name: str, position: tuple[int, int]) -> None:
    positions = _saved_positions() | {name: position}
    try:
        cm.ConfigManager.modify_value(
            ConfigSystem.Key.SECTION,
            ConfigSystem.Key.DIALOG_POSITIONS,
            ", ".join(f"{name}+{x}+{y}" for name, (x, y) in positions.items()),
        )
    except OSError:
        logger.exception("Could not save the position of the %s", name)
