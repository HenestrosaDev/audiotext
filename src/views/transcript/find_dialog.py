"""
The window to find a text in a transcription or in its translation, go through
its matches and replace them. It isn't modal, so the text can be read and played
while it's open.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import customtkinter as ctk

from utils.i18n import L_, _
from views.localization import Text, localize
from views.style import icons, theme
from views.widgets.button import icon_button, set_button_state, show_toggled
from views.widgets.tooltip import Tooltip


class SearchableText(Protocol):
    """A text that highlights the matches of a search and goes through them."""

    @property
    def match_status(self) -> tuple[int | None, int]: ...
    def search(
        self, query: str, match_case: bool = False, current: int | None = None
    ) -> None: ...
    def go_to_match(self, step: int) -> None: ...
    def selected_text(self) -> str: ...


@dataclass(frozen=True)
class FindTarget:
    """What is searched: the transcription or its translation."""

    # The title of the window, which says what it searches
    title: Text
    text: SearchableText
    # Called with the replacement of the current match. None if the text can't
    # be replaced, so only found
    replace_current: Callable[[str], None] | None = None
    # Called with the text to find, its replacement and whether to match the case
    replace_all: Callable[[str, str, bool], None] | None = None


class FindDialog(ctk.CTkToplevel):  # type: ignore[misc]
    def __init__(
        self,
        master: Any,
        target: FindTarget,
        is_pinned: bool,
        on_pin_change: Callable[[bool], None],
        on_close: Callable[[], None],
    ) -> None:
        """
        :param is_pinned: Whether it stays above the main window.
        :param on_pin_change: Called when the user pins or unpins it.
        :param on_close: Called when it's closed.
        """
        super().__init__(master)
        self._target = target
        self._is_pinned = is_pinned
        self._on_pin_change = on_pin_change
        self._on_close = on_close

        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.grid_columnconfigure(0, weight=1)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=0, column=0, padx=20, pady=(14, 18), sticky=ctk.EW)
        body.grid_columnconfigure(1, weight=1)

        self._find = ctk.StringVar(self)
        self._replacement = ctk.StringVar(self)
        self._match_case = ctk.BooleanVar(self, False)
        _label, self.ent_find = self._field(body, 1, L_("Find:"), self._find)
        self._init_navigation(body)
        self.lbl_replacement, self.ent_replacement = self._field(
            body, 2, L_("Replace with:"), self._replacement
        )

        localize(
            ctk.CTkCheckBox(
                body,
                variable=self._match_case,
                font=theme.font(13),
                command=self._search,
            ),
            text=L_("Match case"),
        ).grid(row=3, column=1, pady=(8, 0), sticky=ctk.W)

        footer = ctk.CTkFrame(body, fg_color="transparent")
        footer.grid(row=4, column=0, columnspan=3, pady=(16, 0), sticky=ctk.EW)
        footer.grid_columnconfigure(0, weight=1)
        self.btn_pin = localize(
            ctk.CTkButton(
                footer,
                image=icons.icon("pin", 14),
                compound=ctk.LEFT,
                width=0,
                command=self._toggle_pin,
                **theme.SECONDARY_BUTTON,
            ),
            text=L_("Stay on top"),
        )
        self.btn_pin._tooltip = Tooltip(
            self.btn_pin,
            lambda: (
                _("Unpin from the main window")
                if self._is_pinned
                else _("Keep above the main window")
            ),
        )
        self.btn_pin.grid(row=0, column=0, sticky=ctk.W)

        self.frm_replace = buttons = ctk.CTkFrame(footer, fg_color="transparent")
        buttons.grid(row=0, column=1, padx=(16, 0), sticky=ctk.E)
        self.btn_replace = localize(
            ctk.CTkButton(
                buttons, width=100, command=self._replace, **theme.SECONDARY_BUTTON
            ),
            text=L_("Replace"),
        )
        self.btn_replace.grid(row=0, column=0, padx=(0, 8))
        self.btn_replace_all = localize(
            ctk.CTkButton(buttons, width=110, command=self._replace_all),
            text=L_("Replace all"),
        )
        self.btn_replace_all.grid(row=0, column=1)

        self._find.trace_add("write", lambda *_args: self._search())
        for entry in (self.ent_find, self.ent_replacement):
            entry.bind("<Return>", lambda _event: self.go_to_match(1))
            entry.bind("<Shift-Return>", lambda _event: self.go_to_match(-1))
        self.bind("<Escape>", lambda _event: self.close())

        self._apply_pin()
        self.set_target(target)
        self.after(50, self.focus_find)

    # PUBLIC METHODS

    @property
    def target(self) -> FindTarget:
        return self._target

    def set_target(self, target: FindTarget, find: str = "") -> None:
        """
        Searches another text, e.g. the translation instead of the transcription.

        :param find: The text to find, if not the one already being searched.
        """
        if target.text is not self._target.text:
            self._target.text.search("")
        self._target = target
        localize(self, title=target.title)
        # Only found where it can't be replaced
        for widget in (self.lbl_replacement, self.ent_replacement, self.frm_replace):
            if self._can_replace:
                widget.grid()
            else:
                widget.grid_remove()
        if find and find != self._find.get():
            # Searched by the trace of the variable
            self._find.set(find)
        else:
            self._search()

    def focus_find(self) -> None:
        if self.winfo_exists():
            self.deiconify()
            self.lift()
            self.ent_find.focus_set()
            self.ent_find.select_range(0, ctk.END)

    def refresh(self) -> None:
        """Shows the matches again, e.g. after the text changes."""
        current, total = self._target.text.match_status
        if not self._find.get():
            text = ""
        elif not total:
            text = _("No results")
        else:
            text = _("{current} of {total}").format(
                current=(current or 0) + 1, total=total
            )
        self.lbl_matches.configure(text=text)
        # Without flickering on each key (see `set_button_state`)
        for button in (self.btn_previous, self.btn_next):
            set_button_state(button, ctk.NORMAL if total > 1 else ctk.DISABLED)
        for button in (self.btn_replace, self.btn_replace_all):
            set_button_state(
                button, ctk.NORMAL if total and self._can_replace else ctk.DISABLED
            )

    def go_to_match(self, step: int) -> None:
        self._target.text.go_to_match(step)
        self.refresh()

    def close(self) -> None:
        """Removes the highlights of the matches, and closes it."""
        self._target.text.search("")
        self._on_close()
        self.destroy()

    # WIDGETS

    def _field(
        self, master: Any, row: int, label: Text, variable: ctk.StringVar
    ) -> tuple[ctk.CTkLabel, ctk.CTkEntry]:
        lbl = localize(
            ctk.CTkLabel(master, font=theme.font(13), anchor=ctk.W), text=label
        )
        lbl.grid(row=row, column=0, padx=(0, 10), pady=4, sticky=ctk.W)
        entry = ctk.CTkEntry(master, width=280, textvariable=variable)
        entry.grid(row=row, column=1, pady=4, sticky=ctk.EW)
        return lbl, entry

    def _init_navigation(self, master: Any) -> None:
        """The number of matches and the buttons to go to them, next to the text."""
        frame = ctk.CTkFrame(master, fg_color="transparent")
        frame.grid(row=1, column=2, padx=(8, 0))
        font = theme.font(12)
        # As wide as its longest text, so the window doesn't change its width
        # when the number of matches changes
        width = max(
            font.measure(text)
            for text in (
                _("No results"),
                _("{current} of {total}").format(current=999, total=999),
            )
        )
        self.lbl_matches = ctk.CTkLabel(
            frame,
            text="",
            width=max(width + 8, 70),
            font=font,
            text_color=theme.HINT_TEXT,
        )
        self.lbl_matches.grid(row=0, column=0)
        self.btn_previous = icon_button(
            frame,
            "chevron_left",
            lambda: self.go_to_match(-1),
            L_("Previous match"),
        )
        self.btn_previous.grid(row=0, column=1)
        self.btn_next = icon_button(
            frame,
            "chevron_right",
            lambda: self.go_to_match(1),
            L_("Next match"),
        )
        self.btn_next.grid(row=0, column=2)

    # ACTIONS

    def _search(self) -> None:
        self._target.text.search(self._find.get(), self._match_case.get())
        self.refresh()

    @property
    def _can_replace(self) -> bool:
        return self._target.replace_current is not None

    def _replace(self) -> None:
        replace_current = self._target.replace_current
        if replace_current is None or self._target.text.match_status[0] is None:
            return
        replace_current(self._replacement.get())
        self.refresh()

    def _replace_all(self) -> None:
        find = self._find.get()
        replace_all = self._target.replace_all
        if not find or replace_all is None or not self._target.text.match_status[1]:
            return
        replace_all(find, self._replacement.get(), self._match_case.get())
        self.refresh()

    def _toggle_pin(self) -> None:
        self._is_pinned = not self._is_pinned
        self._apply_pin()
        self._on_pin_change(self._is_pinned)

    def _apply_pin(self) -> None:
        # A transient window stays above the one it belongs to
        self.wm_transient(self.master.winfo_toplevel() if self._is_pinned else "")
        show_toggled(self.btn_pin, "pin", self._is_pinned)
