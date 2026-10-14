from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from utils.i18n import L_
from views.localization import localize
from views.style import icons, theme

# Between the word and the popover below it, and between the popover and the
# sides of the text
POPOVER_GAP = 4
POPOVER_MARGIN = 8


class WordPopover(ctk.CTkFrame):  # type: ignore[misc]
    """
    Corrects a low confidence word where it is, below it: its text can be
    changed (Return saves it), played again, or accepted as it is. Escape closes
    it without changes.
    """

    def __init__(
        self,
        master: Any,
        on_commit: Callable[[str], None],
        on_accept: Callable[[], None],
        on_replay: Callable[[], None],
        on_close: Callable[[], None],
    ) -> None:
        """
        :param on_commit: Called with the text, if the user saves it.
        :param on_close: Called when it closes without changes.
        """
        super().__init__(
            master,
            fg_color=theme.CARD_BG,
            border_color=theme.CARD_BORDER,
            border_width=1,
            corner_radius=10,
        )
        self._on_commit = on_commit
        self._on_close = on_close
        self._is_open = False

        self.ent_text = ctk.CTkEntry(self, width=200, height=32)
        self.ent_text.grid(row=0, column=0, padx=(10, 6), pady=10)
        self.btn_replay = localize(
            ctk.CTkButton(
                self,
                image=icons.icon("refresh", 14),
                compound=ctk.LEFT,
                width=0,
                height=32,
                command=on_replay,
                **theme.SECONDARY_BUTTON,
            ),
            text=L_("Replay"),
        )
        self.btn_replay.grid(row=0, column=1, padx=(0, 6), pady=10)
        self.btn_accept = localize(
            ctk.CTkButton(
                self,
                image=icons.icon("check", 14, theme.ICON_ON_ACCENT),
                compound=ctk.LEFT,
                width=0,
                height=32,
                command=on_accept,
            ),
            text=L_("Accept"),
        )
        self.btn_accept.grid(row=0, column=2, padx=(0, 10), pady=10)

        for sequence in ("<Return>", "<KP_Enter>"):
            self.ent_text.bind(sequence, self._on_return)
        self.ent_text.bind("<Escape>", self._on_escape)

    @property
    def is_open(self) -> bool:
        return self._is_open

    def open(self, text: str, anchor: Any, box: tuple[int, int, int]) -> None:
        """
        Shows the popover below a word, with its text selected to replace it.

        :param anchor: The widget the word is in.
        :param box: The left, the top and the height of the word in `anchor`.
        """
        self.ent_text.delete(0, ctk.END)
        self.ent_text.insert(0, text)
        self._is_open = True
        self.place_at(anchor, box)
        self.lift()
        self.ent_text.focus_set()
        self.ent_text.select_range(0, ctk.END)
        self.ent_text.icursor(ctk.END)

    def place_at(self, anchor: Any, box: tuple[int, int, int] | None) -> None:
        """Follows the word (e.g. when the text scrolls), hidden while it isn't
        visible."""
        if not self._is_open:
            return
        if box is None:
            self.place_forget()
            return
        x, y, height = box
        self.update_idletasks()
        # Kept inside the text, even for a word at its right end
        max_x = anchor.winfo_width() - self.winfo_reqwidth() - POPOVER_MARGIN
        self.place(
            in_=anchor,
            x=max(POPOVER_MARGIN, min(x, max_x)),
            y=y + height + POPOVER_GAP,
        )

    def _on_return(self, _event: Any) -> str:
        self._on_commit(self.ent_text.get())
        return "break"

    def _on_escape(self, _event: Any) -> str:
        self.close()
        return "break"

    def close(self) -> None:
        """Closes it without changes."""
        if not self._is_open:
            return
        self.hide()
        self._on_close()

    def hide(self) -> None:
        """Closes it after the word was saved or accepted."""
        self._is_open = False
        self.place_forget()
