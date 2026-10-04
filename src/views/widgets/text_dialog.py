import tkinter as tk
from typing import Any

import customtkinter as ctk

from utils.i18n import _
from views.style import theme
from views.widgets.textbox import CTkTextbox


class TextDialog(ctk.CTkToplevel):  # type: ignore[misc]
    """
    Modal dialog to type a text: a single line (e.g. a tag, with suggestions, or
    an API key, hidden) or several lines (e.g. a note).
    """

    def __init__(
        self,
        master: Any,
        title: str,
        message: str,
        initial_text: str = "",
        is_multiline: bool = False,
        suggestions: list[str] | None = None,
        ok_text: str | None = None,
        allow_empty: bool = True,
        is_secret: bool = False,
    ) -> None:
        super().__init__(master)
        self._result: str | None = None
        self._is_multiline = is_multiline
        self._allow_empty = allow_empty

        self.title(title)
        self.resizable(is_multiline, is_multiline)
        self.transient(master.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            self, text=message, font=theme.font(13), wraplength=380, justify=ctk.LEFT
        ).grid(row=0, column=0, padx=20, pady=(18, 8), sticky=ctk.W)

        if is_multiline:
            self._input: Any = CTkTextbox(self, width=400, height=160, wrap=ctk.WORD)
            self._input.insert("1.0", initial_text)
        elif suggestions:
            self._input = ctk.CTkComboBox(self, width=400, values=suggestions)
            self._input.set(initial_text)
        else:
            self._input = ctk.CTkEntry(self, width=400, show="•" if is_secret else "")
            self._input.insert(0, initial_text)
        self._input.grid(row=1, column=0, padx=20, sticky=ctk.NSEW)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=2, column=0, padx=20, pady=18, sticky=ctk.E)
        ctk.CTkButton(
            buttons,
            text=_("Cancel"),
            width=90,
            command=self._cancel,
            **theme.SECONDARY_BUTTON,
        ).grid(row=0, column=0, padx=(0, 8))
        self._ok_button = ctk.CTkButton(
            buttons, text=ok_text or _("Save"), width=90, command=self._ok
        )
        self._ok_button.grid(row=0, column=1)

        self.bind("<Escape>", lambda _event: self._cancel())
        if is_multiline:
            self.bind(f"<{theme.SHORTCUT_MODIFIER}-Return>", lambda _event: self._ok())
        else:
            self.bind("<Return>", lambda _event: self._ok())

        self.after(50, self._focus)

    def _focus(self) -> None:
        if not self.winfo_exists():
            return
        self.lift()
        self.grab_set()
        widget = self._input._entry if hasattr(self._input, "_entry") else self._input
        widget.focus_set()
        if not self._is_multiline and hasattr(self._input, "_entry"):
            self._input._entry.select_range(0, tk.END)

    def _get_text(self) -> str:
        if self._is_multiline:
            return str(self._input.get("1.0", tk.END)).strip()
        return str(self._input.get()).strip()

    def _ok(self) -> None:
        text = self._get_text()
        if not text and not self._allow_empty:
            return
        self._result = text
        self.grab_release()
        self.destroy()

    def _cancel(self) -> None:
        self.grab_release()
        self.destroy()

    def get_input(self) -> str | None:
        """Waits until the dialog is closed. :return: The text, or None if cancelled."""
        self.master.wait_window(self)
        return self._result
