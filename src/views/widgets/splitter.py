import tkinter as tk
from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from views.style import theme


def _bind_parts(widget: Any, sequence: str, callback: Callable[[Any], Any]) -> None:
    """
    Binds an event to the Tk widgets that make up a widget, including the inner
    canvas of the CTk widgets, which `CTkFrame.winfo_children` leaves out.
    """
    tk.Misc.bind(widget, sequence, callback, add="+")
    for child in tk.Misc.winfo_children(widget):
        _bind_parts(child, sequence, callback)


class Splitter(ctk.CTkFrame):  # type: ignore[misc]
    """
    A handle that is dragged to resize the panes at its sides. It reports the
    position of the pointer on the screen, so the owner computes the new sizes.
    Double-clicking it restores the default sizes.
    """

    GRIP_LENGTH = 36

    def __init__(
        self,
        master: Any,
        is_vertical: bool,
        on_drag: Callable[[int], None],
        on_release: Callable[[], None] | None = None,
        on_reset: Callable[[], None] | None = None,
        thickness: int = 10,
        has_line: bool = False,
    ) -> None:
        """
        :param is_vertical: Whether the handle is a vertical bar, dragged
                            horizontally.
        :param has_line: Whether to draw a line along the edge of the handle (like
                         a divider) instead of a small grip in its center.
        """
        super().__init__(
            master,
            width=thickness if is_vertical else 0,
            height=0 if is_vertical else thickness,
            fg_color="transparent",
            corner_radius=0,
            cursor="sb_h_double_arrow" if is_vertical else "sb_v_double_arrow",
        )
        self._is_vertical = is_vertical
        self._on_drag = on_drag
        self._on_release = on_release
        self._on_reset = on_reset
        self._is_dragging = False
        self._idle_color = theme.DIVIDER

        if has_line:
            self._mark = ctk.CTkFrame(
                self,
                width=1,
                height=1,
                corner_radius=0,
                fg_color=self._idle_color,
            )
            if is_vertical:
                self._mark.place(x=0, rely=0, relheight=1)
            else:
                self._mark.place(relx=0, y=0, relwidth=1)
        else:
            self._mark = ctk.CTkFrame(
                self,
                width=4 if is_vertical else self.GRIP_LENGTH,
                height=self.GRIP_LENGTH if is_vertical else 4,
                corner_radius=2,
                fg_color=self._idle_color,
            )
            self._mark.place(relx=0.5, rely=0.5, anchor=ctk.CENTER)

        _bind_parts(self, "<Enter>", lambda _event: self._set_highlighted(True))
        _bind_parts(self, "<Leave>", self._on_leave)
        _bind_parts(self, "<ButtonPress-1>", self._on_press)
        _bind_parts(self, "<B1-Motion>", self._on_motion)
        _bind_parts(self, "<ButtonRelease-1>", self._on_button_release)
        _bind_parts(self, "<Double-Button-1>", self._on_double_click)

    def _set_highlighted(self, is_highlighted: bool) -> None:
        self._mark.configure(
            fg_color=theme.ACCENT if is_highlighted else self._idle_color
        )

    def _on_leave(self, _event: Any) -> None:
        if self._is_dragging:
            return
        # Moving between the parts of the handle also triggers <Leave>
        x, y = self.winfo_pointerxy()
        widget = self.winfo_containing(x, y)
        while widget is not None:
            if widget is self:
                return
            widget = getattr(widget, "master", None)
        self._set_highlighted(False)

    def _on_press(self, _event: Any) -> None:
        self._is_dragging = True

    def _on_motion(self, event: Any) -> None:
        if self._is_dragging:
            self._on_drag(event.x_root if self._is_vertical else event.y_root)

    def _on_button_release(self, event: Any) -> None:
        if not self._is_dragging:
            return
        self._is_dragging = False
        self._on_leave(event)
        if self._on_release:
            self._on_release()

    def _on_double_click(self, _event: Any) -> None:
        if self._on_reset:
            self._on_reset()
