from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from models.config.config_transcription import ConfigTranscription
from models.transcription_settings import TranscriptionSettings
from utils.i18n import L_, _
from views.localization import localize
from views.settings.cards.base import SettingsCard
from views.settings.option_labels import save_config

DEBOUNCE_DELAY_MS = 600


class FolderCard(SettingsCard):
    """Whether to transcribe the files of a folder or to watch it for new files."""

    def __init__(
        self,
        master: Any,
        on_change: Callable[[], None],
        config_transcription: ConfigTranscription,
    ) -> None:
        super().__init__(master, L_("Folder"), on_change)
        self.swi_watch = self._switch(
            2,
            L_("Watch folder"),
            config_transcription.watch_folder,
            ConfigTranscription.Key.WATCH_FOLDER,
        )
        self.lbl_watch_hint = self._hint(3, pady=(4, 16))
        # Only while watching, since the folder is transcribed otherwise
        self.swi_existing = self._switch(
            4,
            L_("Transcribe the files already in the folder"),
            config_transcription.watch_transcribe_existing,
            ConfigTranscription.Key.WATCH_TRANSCRIBE_EXISTING,
        )
        self.lbl_existing_hint = self._hint(5, pady=(4, 16))

        # Which of its files are transcribed
        self.swi_subfolders = self._switch(
            6,
            L_("Include subfolders"),
            config_transcription.folder_include_subfolders,
            ConfigTranscription.Key.FOLDER_INCLUDE_SUBFOLDERS,
        )
        self._field_label(7, L_("Skip files matching"))
        self._debounce_after_id: str | None = None
        self._exclude_patterns = ctk.StringVar(
            self, config_transcription.folder_exclude_patterns
        )
        self.ent_exclude = localize(
            ctk.CTkEntry(self, textvariable=self._exclude_patterns),
            placeholder_text=L_("e.g. *.wav, drafts/*"),
        )
        self.ent_exclude.grid(row=8, column=0, columnspan=2, padx=18, sticky=ctk.EW)
        self._exclude_patterns.trace_add("write", lambda *_args: self._debounce_save())
        self._hint(
            9,
            L_(
                "Names or paths of the files to skip, separated by commas. Hidden "
                "files are always skipped."
            ),
            (2, 16),
        )
        self.interactive_widgets.append(self.ent_exclude)

    def destroy(self) -> None:
        if self._debounce_after_id:
            self.after_cancel(self._debounce_after_id)
            self._save_patterns()
        super().destroy()

    def _debounce_save(self) -> None:
        if self._debounce_after_id:
            self.after_cancel(self._debounce_after_id)
        self._debounce_after_id = self.after(DEBOUNCE_DELAY_MS, self._save_patterns)

    def _save_patterns(self) -> None:
        self._debounce_after_id = None
        save_config(
            ConfigTranscription.Key.FOLDER_EXCLUDE_PATTERNS,
            self._exclude_patterns.get().strip(),
        )

    def update_settings(self, settings: TranscriptionSettings) -> None:
        settings.watch = bool(self.swi_watch.get())
        settings.transcribe_existing = settings.watch and bool(self.swi_existing.get())
        settings.include_subfolders = bool(self.swi_subfolders.get())
        settings.exclude_patterns = self._exclude_patterns.get().strip()

    def refresh(self, settings: TranscriptionSettings) -> None:
        if settings.watch:
            self.lbl_watch_hint.configure(
                text=_(
                    "Keeps running and transcribes the files added to the folder, "
                    "until you stop it."
                )
            )
            self.lbl_watch_hint.grid_configure(pady=(4, 0))
            self.swi_existing.grid()
            self.lbl_existing_hint.configure(
                text=_(
                    "First transcribes the files it already contains that don't "
                    "have a transcription yet."
                )
                if settings.transcribe_existing
                else _("The files it already contains are skipped.")
            )
            self.lbl_existing_hint.grid()
        else:
            self.lbl_watch_hint.configure(
                text=_(
                    "Transcribes the audio and video files of the folder and its "
                    "subfolders. Files that already have a transcription are "
                    "skipped. You can transcribe them again from the folder."
                )
            )
            self.lbl_watch_hint.grid_configure(pady=(4, 16))
            self.swi_existing.grid_remove()
            self.lbl_existing_hint.grid_remove()
