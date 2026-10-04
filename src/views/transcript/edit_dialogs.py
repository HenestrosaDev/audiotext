"""Dialogs to correct a transcription."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import customtkinter as ctk

from utils.i18n import _
from views.style import theme


@dataclass(frozen=True)
class Replacement:
    find: str
    replacement: str
    match_case: bool


class _Dialog(ctk.CTkToplevel):  # type: ignore[misc]
    """A modal dialog with Cancel and OK buttons at its bottom."""

    def __init__(self, master: Any, title: str, ok_text: str) -> None:
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.grid_columnconfigure(0, weight=1)

        self.frm_body = ctk.CTkFrame(self, fg_color="transparent")
        self.frm_body.grid(row=0, column=0, padx=20, pady=(18, 0), sticky=ctk.EW)
        self.frm_body.grid_columnconfigure(1, weight=1)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=1, column=0, padx=20, pady=18, sticky=ctk.E)
        ctk.CTkButton(
            buttons,
            text=_("Cancel"),
            width=90,
            command=self._close,
            **theme.SECONDARY_BUTTON,
        ).grid(row=0, column=0, padx=(0, 8))
        self.btn_ok = ctk.CTkButton(buttons, text=ok_text, width=110, command=self._ok)
        self.btn_ok.grid(row=0, column=1)

        self.bind("<Escape>", lambda _event: self._close())
        self.bind("<Return>", lambda _event: self._ok())
        self.after(50, self._focus)

    def _focus(self) -> None:
        if self.winfo_exists():
            self.lift()
            self.grab_set()
            self._focus_first()

    def _focus_first(self) -> None:
        """Focuses the first field of the dialog."""

    def _ok(self) -> None:
        raise NotImplementedError

    def _close(self) -> None:
        self.grab_release()
        self.destroy()

    def wait(self) -> None:
        self.master.wait_window(self)


class ReplaceDialog(_Dialog):
    """Replaces a text in the whole transcription, showing how many times it's in."""

    def __init__(
        self,
        master: Any,
        count_matches: Callable[[str, bool], int],
        initial_text: str = "",
    ) -> None:
        """
        :param count_matches: Returns how many times a text is in the
                              transcription, and whether it matches the case.
        :param initial_text: The text to find, e.g. the one being searched.
        """
        super().__init__(master, _("Find and replace"), _("Replace all"))
        self._count_matches = count_matches
        self._result: Replacement | None = None

        self._find = ctk.StringVar(self, initial_text)
        self._replacement = ctk.StringVar(self)
        self._match_case = ctk.BooleanVar(self, False)

        for row, (label, variable) in enumerate(
            [(_("Find:"), self._find), (_("Replace with:"), self._replacement)]
        ):
            ctk.CTkLabel(self.frm_body, text=label, font=theme.font(13)).grid(
                row=row, column=0, padx=(0, 10), pady=4, sticky=ctk.W
            )
            entry = ctk.CTkEntry(self.frm_body, width=320, textvariable=variable)
            entry.grid(row=row, column=1, pady=4, sticky=ctk.EW)
            if row == 0:
                self.ent_find = entry

        ctk.CTkCheckBox(
            self.frm_body,
            text=_("Match case"),
            variable=self._match_case,
            font=theme.font(13),
            command=self._refresh,
        ).grid(row=2, column=1, pady=(8, 0), sticky=ctk.W)
        self.lbl_count = ctk.CTkLabel(
            self.frm_body, text="", font=theme.font(12), text_color=theme.HINT_TEXT
        )
        self.lbl_count.grid(row=3, column=1, pady=(8, 0), sticky=ctk.W)

        self._find.trace_add("write", lambda *_args: self._refresh())
        self._refresh()

    def get_result(self) -> Replacement | None:
        """Waits until the dialog is closed. :return: None if it was cancelled."""
        self.wait()
        return self._result

    def _focus_first(self) -> None:
        self.ent_find.focus_set()
        self.ent_find.select_range(0, ctk.END)

    def _refresh(self) -> None:
        find = self._find.get()
        count = self._count_matches(find, self._match_case.get()) if find else 0

        if not find:
            text = ""
        elif count == 1:
            text = _("1 match")
        else:
            text = _("{count} matches").format(count=count)
        self.lbl_count.configure(text=text)
        self.btn_ok.configure(state=ctk.NORMAL if count else ctk.DISABLED)

    def _ok(self) -> None:
        find = self._find.get()
        if not find or not self._count_matches(find, self._match_case.get()):
            return
        self._result = Replacement(
            find, self._replacement.get(), self._match_case.get()
        )
        self._close()


class SpeakersDialog(_Dialog):
    """Gives names to the speakers identified in the transcription."""

    def __init__(self, master: Any, speakers: list[str]) -> None:
        super().__init__(master, _("Rename speakers"), _("Save"))
        self._result: dict[str, str] | None = None
        self._variables: dict[str, ctk.StringVar] = {}

        ctk.CTkLabel(
            self.frm_body,
            text=_(
                "Give a name to each speaker. Giving two speakers the same name "
                "merges them."
            ),
            font=theme.font(13),
            wraplength=380,
            justify=ctk.LEFT,
        ).grid(row=0, column=0, columnspan=2, pady=(0, 8), sticky=ctk.W)

        self._entries: list[ctk.CTkEntry] = []
        for row, speaker in enumerate(speakers, start=1):
            ctk.CTkLabel(
                self.frm_body,
                text=speaker,
                font=theme.font(13, "bold"),
                anchor=ctk.W,
            ).grid(row=row, column=0, padx=(0, 12), pady=4, sticky=ctk.W)
            variable = ctk.StringVar(self, speaker)
            entry = ctk.CTkEntry(self.frm_body, width=240, textvariable=variable)
            entry.grid(row=row, column=1, pady=4, sticky=ctk.EW)
            self._variables[speaker] = variable
            self._entries.append(entry)

    def get_result(self) -> dict[str, str] | None:
        """
        Waits until the dialog is closed.

        :return: The new name of each renamed speaker, or None if it was
                 cancelled.
        """
        self.wait()
        return self._result

    def _focus_first(self) -> None:
        if self._entries:
            self._entries[0].focus_set()
            self._entries[0].select_range(0, ctk.END)

    def _ok(self) -> None:
        self._result = {
            speaker: variable.get().strip()
            for speaker, variable in self._variables.items()
            if variable.get().strip() and variable.get().strip() != speaker
        }
        self._close()
