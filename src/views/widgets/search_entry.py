from typing import Any

import customtkinter as ctk

from views.style import icons, theme
from views.widgets.placeholder import add_placeholder


class SearchEntry(ctk.CTkFrame):  # type: ignore[misc]
    """
    A text field for searching: a magnifying glass before the text and, while
    there is a search, a button to clear it.
    """

    def __init__(
        self,
        master: Any,
        textvariable: ctk.StringVar,
        placeholder_text: str,
        height: int = 30,
        width: int = 200,
        corner_radius: int = 8,
    ) -> None:
        entry_theme = ctk.ThemeManager.theme["CTkEntry"]
        super().__init__(
            master,
            width=width,
            height=height,
            corner_radius=corner_radius,
            border_width=1,
            fg_color=entry_theme["fg_color"],
            border_color=entry_theme["border_color"],
        )
        self._variable = textvariable
        self.grid_columnconfigure(1, weight=1)
        self.grid_propagate(False)
        self.grid_rowconfigure(0, weight=1)

        lbl_icon = ctk.CTkLabel(
            self, text="", width=14, image=icons.icon("search", 13, theme.ICON_MUTED)
        )
        lbl_icon.grid(row=0, column=0, padx=(9, 0))

        self.entry = ctk.CTkEntry(
            self,
            textvariable=textvariable,
            height=height - 4,
            border_width=0,
            corner_radius=0,
            fg_color=entry_theme["fg_color"],
        )
        self.entry.grid(row=0, column=1, padx=(0, 2), sticky=ctk.EW)
        add_placeholder(self.entry, textvariable, placeholder_text)
        lbl_icon.bind("<Button-1>", lambda _event: self.entry.focus_set())

        self.btn_clear = ctk.CTkButton(
            self,
            text="",
            width=20,
            height=20,
            image=icons.icon("x_circle", 13, theme.ICON_MUTED),
            command=self.clear,
            **theme.GHOST_BUTTON,
        )
        self.btn_clear.grid(row=0, column=2, padx=(0, 5))
        textvariable.trace_add("write", lambda *_args: self._refresh_clear_button())
        self._refresh_clear_button()

    def clear(self) -> None:
        self._variable.set("")
        self.entry.focus_set()

    def _refresh_clear_button(self) -> None:
        if self._variable.get():
            self.btn_clear.grid()
        else:
            self.btn_clear.grid_remove()
