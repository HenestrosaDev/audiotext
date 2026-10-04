from typing import Any

import customtkinter as ctk

from models.history import EntryStatus, HistoryEntry
from utils.enums import AudioSource
from utils.i18n import _
from views.entries.delegates import EntryDelegate
from views.history.formatting import status_icon, status_label
from views.style import icons, theme
from views.widgets.bindings import bind_wraplength
from views.widgets.stepper import Stepper


def first_step_label(kind: str) -> str:
    return {
        AudioSource.FILE.value: _("Choose a file"),
        AudioSource.YOUTUBE.value: _("Enter the URL"),
        AudioSource.MIC.value: _("Record"),
        AudioSource.DIRECTORY.value: _("Choose a folder"),
        AudioSource.WATCH.value: _("Choose a folder"),
    }.get(kind, _("Source"))


class ProgressCard(ctk.CTkFrame):  # type: ignore[misc]
    """
    The status of a transcription in progress (or that has failed): the last
    step of the stepper, the progress and the actions.
    """

    def __init__(
        self, master: Any, entry: HistoryEntry, delegate: EntryDelegate
    ) -> None:
        super().__init__(
            master,
            fg_color=theme.CARD_BG,
            border_color=theme.CARD_BORDER,
            border_width=1,
            corner_radius=14,
        )
        self._entry = entry
        self._delegate = delegate
        self._is_progress_indeterminate = False
        self.grid_columnconfigure(0, weight=1)

        self.stepper = Stepper(
            self, [first_step_label(entry.kind), _("Settings"), _("Transcribe")]
        )
        self.stepper.grid(row=0, column=0, padx=24, pady=(22, 0), sticky=ctk.EW)

        status_row = ctk.CTkFrame(self, fg_color="transparent")
        status_row.grid(row=1, column=0, padx=24, pady=(26, 0), sticky=ctk.EW)
        status_row.grid_columnconfigure(1, weight=1)
        self.lbl_icon = ctk.CTkLabel(status_row, text="", width=22)
        self.lbl_icon.grid(row=0, column=0, padx=(0, 10))
        self.lbl_status = ctk.CTkLabel(
            status_row, text="", font=theme.font(16, "bold"), anchor=ctk.W
        )
        self.lbl_status.grid(row=0, column=1, sticky=ctk.EW)

        self.lbl_message = ctk.CTkLabel(
            self,
            text="",
            font=theme.font(13),
            text_color=theme.HINT_TEXT,
            anchor=ctk.W,
            justify=ctk.LEFT,
        )
        self.lbl_message.grid(row=2, column=0, padx=24, pady=(6, 0), sticky=ctk.EW)
        bind_wraplength(self.lbl_message, margin=10, minimum=200)

        self.progress_bar = ctk.CTkProgressBar(self, height=8)
        self.progress_bar.grid(row=3, column=0, padx=24, pady=(14, 0), sticky=ctk.EW)

        self.frm_actions = ctk.CTkFrame(self, fg_color="transparent")
        self.frm_actions.grid(row=4, column=0, padx=24, pady=(18, 22), sticky=ctk.W)

        self.lbl_tip = ctk.CTkLabel(
            self,
            text="",
            font=theme.font(12),
            text_color=theme.HINT_TEXT,
            anchor=ctk.W,
            justify=ctk.LEFT,
        )
        self.lbl_tip.grid(row=5, column=0, padx=24, pady=(0, 20), sticky=ctk.EW)

        self.update_entry(entry)

    def destroy(self) -> None:
        self.progress_bar.stop()
        super().destroy()

    def update_entry(self, entry: HistoryEntry) -> None:
        self._entry = entry
        status = entry.status
        is_error = status in (
            EntryStatus.FAILED,
            EntryStatus.INTERRUPTED,
            EntryStatus.CANCELLED,
        )
        self.stepper.set_current(
            2 if status != EntryStatus.DONE else 3, is_error=is_error
        )
        self.lbl_icon.configure(image=status_icon(status, 20))

        for widget in self.frm_actions.winfo_children():
            widget.destroy()

        if status.is_active:
            self.lbl_status.configure(text=status_label(status))
            self.update_progress()
            label = (
                _("Stop watching") if status == EntryStatus.WATCHING else _("Cancel")
            )
            ctk.CTkButton(
                self.frm_actions,
                text=label,
                width=110,
                command=lambda: self._delegate.cancel_entry(entry.id),
                **theme.DANGER_BUTTON,
            ).grid(row=0, column=0)
            self.lbl_tip.configure(
                text=_(
                    "You can keep using Audiotext meanwhile. The result is saved in "
                    "your history and opens here when it's ready."
                )
            )
            self.lbl_tip.grid()
            return

        self._stop_progress()
        self.progress_bar.grid_remove()
        self.lbl_tip.grid_remove()

        if status == EntryStatus.FAILED:
            title = _("The transcription failed")
            message = entry.error or _("An unknown error occurred.")
        elif status == EntryStatus.INTERRUPTED:
            title = _("The transcription was interrupted")
            message = _("Audiotext was closed before it finished.")
        else:
            title = _("The transcription was cancelled")
            message = ""
        self.lbl_status.configure(text=title)
        self.lbl_message.configure(
            text=message,
            text_color=theme.ERROR_TEXT
            if status == EntryStatus.FAILED
            else theme.HINT_TEXT,
        )

        if entry.parent_id is None:
            # A recording can't go back to its settings, chosen before recording
            if entry.kind != AudioSource.MIC.value:
                ctk.CTkButton(
                    self.frm_actions,
                    text=_("Back"),
                    image=icons.icon("chevron_left", 12),
                    compound=ctk.LEFT,
                    width=90,
                    command=lambda: self._delegate.go_back_to_settings(entry.id),
                    **theme.SECONDARY_BUTTON,
                ).grid(row=0, column=0, padx=(0, 8))
            ctk.CTkButton(
                self.frm_actions,
                text=_("Try again"),
                image=icons.icon("refresh", 14, theme.ICON_ON_ACCENT),
                compound=ctk.LEFT,
                width=110,
                command=lambda: self._delegate.retry_entry(entry.id),
            ).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(
            self.frm_actions,
            text=_("Delete"),
            width=90,
            command=lambda: self._delegate.delete_entry(entry.id),
            **theme.SECONDARY_BUTTON,
        ).grid(row=0, column=2)

    def update_progress(self) -> None:
        if not self._entry.status.is_active:
            return

        if self._entry.status == EntryStatus.QUEUED:
            position = self._delegate.get_queue_position(self._entry.id)
            message = (
                _("Waiting for {count} transcription(s) to finish.").format(
                    count=position
                )
                if position
                else _("Waiting for the current transcription to finish.")
            )
            fraction = None
        else:
            message, fraction = self._delegate.get_progress_message(self._entry.id)

        self.lbl_message.configure(
            text=message or _("Starting…"), text_color=theme.HINT_TEXT
        )
        self.progress_bar.grid()

        if fraction is None:
            if not self._is_progress_indeterminate:
                self.progress_bar.configure(mode="indeterminate")
                self.progress_bar.start()
                self._is_progress_indeterminate = True
        else:
            self._stop_progress()
            self.progress_bar.set(fraction)

    def _stop_progress(self) -> None:
        if self._is_progress_indeterminate:
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
            self._is_progress_indeterminate = False
