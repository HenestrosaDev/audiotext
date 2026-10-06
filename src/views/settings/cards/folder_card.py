from collections.abc import Callable
from typing import Any

from models.config.config_transcription import ConfigTranscription
from models.transcription_settings import TranscriptionSettings
from utils.i18n import _
from views.settings.cards.base import SettingsCard


class FolderCard(SettingsCard):
    """Whether to transcribe the files of a folder or to watch it for new files."""

    def __init__(
        self,
        master: Any,
        on_change: Callable[[], None],
        config_transcription: ConfigTranscription,
    ) -> None:
        super().__init__(master, lambda: _("Folder"), on_change)
        self.swi_watch = self._switch(
            2,
            lambda: _("Watch the folder"),
            config_transcription.watch_folder,
            ConfigTranscription.Key.WATCH_FOLDER,
        )
        self.lbl_watch_hint = self._hint(3, pady=(4, 16))

    def update_settings(self, settings: TranscriptionSettings) -> None:
        settings.watch = bool(self.swi_watch.get())

    def refresh(self, settings: TranscriptionSettings) -> None:
        self.lbl_watch_hint.configure(
            text=_(
                "Keeps running and transcribes the files added to the folder, "
                "until you stop it. The files it already contains are skipped."
            )
            if settings.watch
            else _(
                "Transcribes the audio and video files of the folder and its "
                "subfolders. Files that already have a transcription are skipped "
                "unless you overwrite them."
            )
        )
