from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from models.history import HistoryEntry


class HistoryView(Protocol):
    """
    What the controllers of the history need from the view to show the changes of
    its entries. They're always called from the UI thread.
    """

    def run_on_ui_thread(self, callback: Callable[..., Any], *args: Any) -> None:
        """
        Schedules a callback to be run on the UI thread, since the summaries and
        the translations are made in a background thread.
        """

    def refresh_sidebar(self) -> None:
        """Shows the list of entries again, e.g. after adding or moving one."""

    def on_entry_changed(self, entry_id: str, is_structural: bool = False) -> None:
        """
        :param is_structural: Whether the change affects the order or the sections
                              of the list (e.g. pinning or adding).
        """

    def refresh_entry_view(self, entry_id: str) -> None:
        """Shows the changes of an entry (or of a file of it) if it's shown."""

    def on_reveal_failed(self, path: Path, error: Exception) -> None:
        """
        :param error: `FileNotFoundError` if the file was moved or deleted, or why
                      the file manager couldn't be opened.
        """

    def on_open_folder_failed(self, folder: Path, error: Exception) -> None: ...

    def on_summary_finished(self, entry: HistoryEntry, error: str | None) -> None:
        """:param error: Why the summary failed, or None if it's ready."""

    def on_translation_finished(self, entry: HistoryEntry, error: str | None) -> None:
        """:param error: Why the translation failed, or None if it's ready."""


class TranscriptionQueueView(HistoryView, Protocol):
    """What the queue of transcriptions needs from the view."""

    def select_entry(self, entry_id: str) -> None: ...

    def refresh_progress(self, entry_id: str) -> None:
        """Shows the progress (or the position in the queue) of an entry."""

    def show_status(self, message: str, is_error: bool = False) -> None:
        """Shows a message of what runs the transcriptions."""

    def on_recording_unavailable(self, entry: HistoryEntry) -> None:
        """The recording of an entry can't be transcribed again, since it's gone."""

    def on_transcription_finished(
        self, entry: HistoryEntry, status_message: str | None
    ) -> None:
        """
        Called once the transcription of an entry finishes, is cancelled or fails,
        as its status says.

        :param status_message: A summary of the result, if any.
        """

    def on_transcription_ready(self, entry: HistoryEntry) -> None:
        """
        The transcription of an entry is done, or that of a file of a watched
        folder, which is never done.
        """

    def on_transcription_saved(self, folder: Path) -> None:
        """A transcription that isn't in the history was saved in a folder."""

    # MICROPHONE

    def is_recording(self) -> bool: ...

    def on_mic_progress(self, message: str) -> None: ...

    def on_mic_text(self, text: str) -> None:
        """Shows the transcription of the recording, once it's done."""

    def on_mic_finished(self, entry: HistoryEntry) -> None:
        """
        Called once the transcription of the recording of an entry finishes, is
        cancelled or fails, as its status says.
        """
