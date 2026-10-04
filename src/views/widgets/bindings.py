"""Helpers to bind events to the widgets of the interface."""

from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from views.style import theme


def bind_context_menu(widget: Any, callback: Callable[[Any], Any]) -> None:
    """Binds the right click (and Control+click on macOS) of a widget."""
    for sequence in theme.CONTEXT_MENU_EVENTS:
        widget.bind(sequence, callback, add="+")


def bind_recursive(widget: Any, sequence: str, callback: Callable[[Any], Any]) -> None:
    """Binds an event to a widget and all its descendants."""
    widget.bind(sequence, callback, add="+")
    for child in widget.winfo_children():
        bind_recursive(child, sequence, callback)


def bind_wraplength(label: ctk.CTkLabel, margin: int = 4, minimum: int = 100) -> None:
    """
    Wraps the text of a label to the width it's given by its layout, which must
    stretch it (e.g. `sticky=ctk.EW`).

    `CTkLabel.bind` would also receive the events of its inner Tk label, whose
    width is the one it requests, which shrinks with each wrap until it reaches
    the minimum. So only the canvas of the label, sized by the layout, is followed.
    """

    def on_configure(event: Any) -> None:
        width = max(int(label._reverse_widget_scaling(event.width)) - margin, minimum)
        if label.cget("wraplength") != width:
            label.configure(wraplength=width)

    label._canvas.bind("<Configure>", on_configure, add="+")
