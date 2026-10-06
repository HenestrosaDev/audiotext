from collections.abc import Callable
from typing import Any, Protocol


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

    def show_status(self, message: str, is_error: bool = False) -> None: ...

    def refresh_sidebar(self) -> None:
        """Shows the list of entries again, e.g. after adding or moving one."""

    def on_entry_changed(self, entry_id: str, is_structural: bool = False) -> None:
        """
        :param is_structural: Whether the change affects the order or the sections
                              of the list (e.g. pinning or adding).
        """

    def refresh_entry_view(self, entry_id: str) -> None:
        """Shows the changes of an entry (or of a file of it) if it's shown."""


class TranscriptionQueueView(HistoryView, Protocol):
    """What the queue of transcriptions needs from the view."""

    def select_entry(self, entry_id: str) -> None: ...

    def refresh_progress(self, entry_id: str) -> None:
        """Shows the progress (or the position in the queue) of an entry."""

    # MICROPHONE

    def is_recording(self) -> bool: ...

    def on_mic_progress(self, message: str) -> None: ...

    def on_mic_text(self, text: str) -> None:
        """Shows the transcription of the recording, once it's done."""

    def on_mic_finished(self, error: str | None) -> None:
        """
        :param error: Why the transcription of the recording didn't finish, or None
                      if it did.
        """
