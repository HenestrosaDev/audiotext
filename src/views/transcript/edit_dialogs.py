"""Dialogs to correct a transcription."""

from dataclasses import dataclass
from typing import Any

import customtkinter as ctk

from utils.i18n import _
from utils.time_format import format_subtitle_time, parse_segment_time
from views.style import theme
from views.widgets.window import place_dialog


@dataclass(frozen=True)
class Timing:
    start: float
    end: float
    # The speaker chosen, if the dialog asks for it
    speaker: str | None = None


class _Dialog(ctk.CTkToplevel):  # type: ignore[misc]
    """A modal dialog with Cancel and OK buttons at its bottom."""

    def __init__(self, master: Any, title: str, ok_text: str) -> None:
        super().__init__(master)
        # Shown by `place_dialog` once it's built, already in its place
        self.withdraw()
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
        place_dialog(self, self.master)
        self.master.wait_window(self)


def _speaker_field(
    master: Any, row: int, speakers: list[str], variable: ctk.StringVar
) -> ctk.CTkComboBox:
    """
    A field to choose one of the speakers of the transcription, or to type
    another one (e.g. one that the diarization missed).
    """
    ctk.CTkLabel(master, text=_("Speaker:"), font=theme.font(13)).grid(
        row=row, column=0, padx=(0, 10), pady=4, sticky=ctk.W
    )
    field = ctk.CTkComboBox(master, width=240, values=speakers, variable=variable)
    field.grid(row=row, column=1, pady=4, sticky=ctk.W)
    return field


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


class TimingDialog(_Dialog):
    """
    Sets when a subtitle starts and ends, precise to the millisecond, and who says
    it if the speakers are identified.
    """

    def __init__(
        self,
        master: Any,
        title: str,
        ok_text: str,
        message: str,
        timing: Timing,
        speakers: list[str] | None = None,
        note: str = "",
    ) -> None:
        """
        :param message: Explains what the subtitle is, e.g. its text.
        :param timing: The current timing of the subtitle, or the suggested one,
                       with its speaker if it's asked for.
        :param speakers: The speakers to choose from, or None to not ask for one.
        :param note: Warns of what changes besides the timing.
        """
        super().__init__(master, title, ok_text)
        self._result: Timing | None = None

        ctk.CTkLabel(
            self.frm_body,
            text=message,
            font=theme.font(13),
            wraplength=380,
            justify=ctk.LEFT,
        ).grid(row=0, column=0, columnspan=2, pady=(0, 8), sticky=ctk.W)

        self._variables: list[ctk.StringVar] = []
        self._entries: list[ctk.CTkEntry] = []
        for row, (label, seconds) in enumerate(
            [(_("Start:"), timing.start), (_("End:"), timing.end)], start=1
        ):
            ctk.CTkLabel(self.frm_body, text=label, font=theme.font(13)).grid(
                row=row, column=0, padx=(0, 10), pady=4, sticky=ctk.W
            )
            variable = ctk.StringVar(self, format_subtitle_time(seconds, ","))
            variable.trace_add("write", lambda *_args: self._refresh())
            entry = ctk.CTkEntry(
                self.frm_body,
                width=160,
                textvariable=variable,
                font=theme.font(13, family=theme.MONOSPACE_FAMILY),
            )
            entry.grid(row=row, column=1, pady=4, sticky=ctk.W)
            self._variables.append(variable)
            self._entries.append(entry)

        # Asked for if the speakers are identified
        self._speaker: ctk.StringVar | None = None
        if speakers is not None:
            self._speaker = ctk.StringVar(self, timing.speaker or "")
            self._speaker.trace_add("write", lambda *_args: self._refresh())
            _speaker_field(self.frm_body, 3, speakers, self._speaker)

        if note:
            ctk.CTkLabel(
                self.frm_body,
                text=note,
                font=theme.font(12),
                text_color=theme.HINT_TEXT,
                anchor=ctk.W,
                justify=ctk.LEFT,
                wraplength=380,
            ).grid(row=4, column=0, columnspan=2, pady=(6, 0), sticky=ctk.W)

        self.lbl_error = ctk.CTkLabel(
            self.frm_body,
            text="",
            font=theme.font(12),
            text_color=theme.ERROR_TEXT,
            anchor=ctk.W,
            justify=ctk.LEFT,
            wraplength=380,
        )
        self.lbl_error.grid(row=5, column=0, columnspan=2, pady=(6, 0), sticky=ctk.W)
        self._refresh()

    def get_result(self) -> Timing | None:
        """Waits until the dialog is closed. :return: None if it was cancelled."""
        self.wait()
        return self._result

    def _parse(self) -> tuple[Timing | None, str]:
        """:return: The timing, or None and why it isn't valid."""
        try:
            start, end = (parse_segment_time(v.get()) for v in self._variables)
        except ValueError:
            return None, _("Type the times as 00:01:05,900, 01:05,9 or 65.9.")
        if end <= start:
            return None, _("The subtitle must end after it starts.")
        if self._speaker is None:
            return Timing(start, end), ""
        if not (speaker := self._speaker.get().strip()):
            return None, _("Choose who says it.")
        return Timing(start, end, speaker), ""

    def _refresh(self) -> None:
        timing, error = self._parse()
        self.lbl_error.configure(text=error)
        self.btn_ok.configure(state=ctk.NORMAL if timing else ctk.DISABLED)

    def _focus_first(self) -> None:
        self._entries[0].focus_set()
        self._entries[0].select_range(0, ctk.END)

    def _ok(self) -> None:
        timing, _error = self._parse()
        if timing is None:
            return
        self._result = timing
        self._close()


class SpeakerDialog(_Dialog):
    """Changes who says a subtitle, unlike `SpeakersDialog`, which renames them."""

    def __init__(
        self, master: Any, message: str, speakers: list[str], speaker: str | None
    ) -> None:
        """
        :param message: Explains what the subtitle is, e.g. its text.
        :param speakers: The speakers of the transcription.
        :param speaker: Who says the subtitle now.
        """
        super().__init__(master, _("Change speaker"), _("Save"))
        self._result: str | None = None

        ctk.CTkLabel(
            self.frm_body,
            text=message,
            font=theme.font(13),
            wraplength=380,
            justify=ctk.LEFT,
        ).grid(row=0, column=0, columnspan=2, pady=(0, 8), sticky=ctk.W)

        self._speaker = ctk.StringVar(self, speaker or "")
        self._speaker.trace_add("write", lambda *_args: self._refresh())
        self.cbx_speaker = _speaker_field(self.frm_body, 1, speakers, self._speaker)
        self._refresh()

    def get_result(self) -> str | None:
        """
        Waits until the dialog is closed.

        :return: The speaker chosen, or None if it was cancelled.
        """
        self.wait()
        return self._result

    def _refresh(self) -> None:
        is_valid = bool(self._speaker.get().strip())
        self.btn_ok.configure(state=ctk.NORMAL if is_valid else ctk.DISABLED)

    def _focus_first(self) -> None:
        self.cbx_speaker.focus_set()

    def _ok(self) -> None:
        if speaker := self._speaker.get().strip():
            self._result = speaker
            self._close()
