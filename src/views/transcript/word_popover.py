import tkinter as tk
from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from utils.i18n import L_, _
from views.localization import localize
from views.style import icons, theme
from views.widgets.button import icon_button
from views.widgets.tooltip import Tooltip

# Between the word and the popover below it, and between the popover and the
# sides of the text
POPOVER_GAP = 4
POPOVER_MARGIN = 8
# The width of the field for a word, and the widest for a whole segment, which
# the space of the text may narrow
WORD_FIELD_WIDTH = 200
SEGMENT_FIELD_WIDTH = 480
# The space taken by the buttons and the margins next to the field
BUTTONS_WIDTH = 276
REPLAY_SHORTCUT = f"<{theme.SHORTCUT_MODIFIER}-r>"


class WordPopover(ctk.CTkFrame):  # type: ignore[misc]
    """
    Corrects a low confidence word where it is, below it (or above it, near the
    bottom of the text): its text can be changed (Return saves it), played again
    (Command/Control + R), or accepted as it is. Escape, its close button, or
    clicking elsewhere, closes it without changes: what was typed is discarded.
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
        self._anchor: Any = None

        self.ent_text = ctk.CTkEntry(self, width=WORD_FIELD_WIDTH, height=32)
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
        self.btn_replay._tooltip = Tooltip(
            self.btn_replay,
            lambda: _("Replay ({shortcut})").format(
                shortcut=f"{theme.SHORTCUT_MODIFIER_LABEL}R"
            ),
        )
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
        self.btn_accept.grid(row=0, column=2, padx=(0, 4), pady=10)
        self.btn_close = icon_button(
            self,
            "x",
            self.close,
            lambda: _("Close ({shortcut})").format(shortcut="Esc"),
        )
        self.btn_close.grid(row=0, column=3, padx=(0, 6), pady=10)

        for sequence in ("<Return>", "<KP_Enter>"):
            self.ent_text.bind(sequence, self._on_return)
        self.ent_text.bind("<Escape>", self._on_escape)
        self._on_replay = on_replay
        self.ent_text.bind(REPLAY_SHORTCUT, self._on_replay_key)

    @property
    def is_open(self) -> bool:
        return self._is_open

    def open(
        self,
        text: str,
        anchor: Any,
        box: tuple[int, int, int],
        is_segment: bool = False,
    ) -> None:
        """
        Shows the popover below a word, with its text selected to replace it. Any
        text typed in it before is discarded.

        :param anchor: The widget the word is in.
        :param box: The left, the top and the bottom of the word in `anchor`.
        :param is_segment: Whether the text is a whole segment, which takes a
            wider field.
        """
        width = WORD_FIELD_WIDTH
        if is_segment:
            room = anchor.winfo_width() - BUTTONS_WIDTH - 2 * POPOVER_MARGIN
            width = max(WORD_FIELD_WIDTH, min(SEGMENT_FIELD_WIDTH, room))
        self.ent_text.configure(width=width)
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
        x, top, bottom = box
        self._anchor = anchor
        self.update_idletasks()
        # Kept inside the text (and so the window), even for a word at its right
        # end, or at its bottom, where it's shown above the word
        max_x = anchor.winfo_width() - self.winfo_reqwidth() - POPOVER_MARGIN
        y = bottom + POPOVER_GAP
        if y + self.winfo_reqheight() > anchor.winfo_height() - POPOVER_MARGIN:
            y = max(POPOVER_MARGIN, top - POPOVER_GAP - self.winfo_reqheight())
        self.place(in_=anchor, x=max(POPOVER_MARGIN, min(x, max_x)), y=y)

    def _on_return(self, _event: Any) -> str:
        self._on_commit(self.ent_text.get())
        return "break"

    def _on_replay_key(self, _event: Any) -> str:
        self._on_replay()
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
        was_placed = bool(self.winfo_manager())
        self.place_forget()
        if was_placed:
            self._redraw_anchor()

    def _redraw_anchor(self) -> None:
        """
        Redraws the text it was over: on macOS, Tk may not repaint the area a
        placed widget leaves, which would keep showing it (without working)
        until the text changes.
        """
        anchor = self._anchor
        if anchor is None or not anchor.winfo_exists():
            return
        try:
            # Configuring a Text widget, even with the same value, redraws it all
            anchor.configure(padx=anchor.cget("padx"))
        except tk.TclError:
            anchor.update_idletasks()
