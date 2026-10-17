from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import utils.notifications as notifications
from models.history import EntryStatus, HistoryEntry
from utils.config_manager import ConfigManager
from utils.i18n import P_, _

# How long the files of a watched folder transcribed one after the other are
# waited for, to notify them together
GROUPED_NOTIFICATION_DELAY_MS = 5000


class StatusDisplay(Protocol):
    def show_status(self, message: str, is_error: bool = False) -> None: ...

    def after(self, ms: int, func: Callable[[], Any]) -> str: ...

    def after_cancel(self, id: str) -> None: ...

    def refresh_entry_view(self, entry_id: str) -> None:
        """Shows the changes of an entry if it's shown."""


class StatusMessages:
    """
    Words what the controllers report once something finishes or fails, e.g. a
    summary, and shows it in the status bar of the window (or as a notification
    of the system).
    """

    def __init__(self, display: StatusDisplay) -> None:
        self._display = display
        # The files of watched folders waiting to be notified, by folder
        self._ready_files: dict[str, list[str]] = {}
        self._notify_after_id: str | None = None

    # TRANSCRIPTIONS

    def on_transcription_finished(
        self, entry: HistoryEntry, status_message: str | None
    ) -> None:
        if entry.status == EntryStatus.FAILED:
            self._display.show_status(f"{entry.title}: {entry.error}", is_error=True)
        elif status_message:
            self._display.show_status(f"{entry.title}: {status_message}")

    def on_transcription_ready(
        self, entry: HistoryEntry, folder_title: str | None = None
    ) -> None:
        """
        :param folder_title: The title of the watched folder of the file, if it's
                             one. Its files transcribed one after the other are
                             notified together.
        """
        if not ConfigManager.get_config_system().notify_when_done:
            return
        if folder_title is None:
            notifications.notify(_("Transcription ready"), entry.title)
            return

        self._ready_files.setdefault(folder_title, []).append(entry.title)
        if self._notify_after_id is not None:
            self._display.after_cancel(self._notify_after_id)
        self._notify_after_id = self._display.after(
            GROUPED_NOTIFICATION_DELAY_MS, self._notify_ready_files
        )

    def _notify_ready_files(self) -> None:
        self._notify_after_id = None
        ready_files, self._ready_files = self._ready_files, {}
        for folder_title, titles in ready_files.items():
            if len(titles) == 1:
                notifications.notify(_("Transcription ready"), titles[0])
            else:
                notifications.notify(
                    _("Transcription ready"),
                    P_(
                        "{count} file transcribed in {folder}",
                        "{count} files transcribed in {folder}",
                        len(titles),
                    ).format(count=len(titles), folder=folder_title),
                )

    def on_transcription_saved(self, folder: Path) -> None:
        self._display.show_status(_("Saved in {folder}.").format(folder=folder))

    def on_recording_unavailable(self, entry: HistoryEntry) -> None:
        self._display.show_status(
            _("The recording is no longer available."), is_error=True
        )

    # FILES

    def on_reveal_failed(self, path: Path, error: Exception) -> None:
        if isinstance(error, FileNotFoundError):
            message = _("The file was moved or deleted: {path}").format(path=path)
        else:
            message = _("Could not open the file manager: {error}").format(error=error)
        self._display.show_status(message, is_error=True)

    def on_open_folder_failed(self, folder: Path, error: Exception) -> None:
        self._display.show_status(
            _("Could not open the folder: {error}").format(error=error), is_error=True
        )

    # SUMMARIES AND TRANSLATIONS

    def on_summary_finished(self, entry: HistoryEntry, error: str | None) -> None:
        if error is None:
            self._display.show_status(
                _("The summary of “{title}” is ready.").format(title=entry.title)
            )
        else:
            self._display.show_status(
                _("Could not summarize “{title}”: {error}").format(
                    title=entry.title, error=error
                ),
                is_error=True,
            )
        self._display.refresh_entry_view(entry.id)

    def on_translation_finished(self, entry: HistoryEntry, error: str | None) -> None:
        if error is None:
            self._display.show_status(
                _("The translation of “{title}” is ready.").format(title=entry.title)
            )
        else:
            self._display.show_status(
                _("Could not translate “{title}”: {error}").format(
                    title=entry.title, error=error
                ),
                is_error=True,
            )
        self._display.refresh_entry_view(entry.id)
