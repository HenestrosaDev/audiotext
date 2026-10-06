from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from models.history import HistoryEntry
from views.ui_thread_queue import UiThreadQueue

if TYPE_CHECKING:
    from views.main_window.main_window import MainWindow


class CurrentWindow:
    """
    The view of the controllers, which outlive the main window: it's rebuilt when
    the interface language changes. It passes their calls on to the window being
    shown, and runs the callbacks of their background threads, so the ones sent
    while the window is rebuilt aren't lost.
    """

    def __init__(self, root: Any) -> None:
        """:param root: The root window of the app, which is never rebuilt."""
        self._window: MainWindow | None = None
        self._ui_queue = UiThreadQueue(root)

    @property
    def window(self) -> "MainWindow":
        if self._window is None:
            raise RuntimeError("The main window hasn't been created yet")
        return self._window

    @window.setter
    def window(self, window: "MainWindow") -> None:
        self._window = window

    def run_on_ui_thread(self, callback: Callable[..., Any], *args: Any) -> None:
        self._ui_queue.put(callback, *args)

    # HISTORY

    def show_status(self, message: str, is_error: bool = False) -> None:
        self.window.show_status(message, is_error=is_error)

    def refresh_sidebar(self) -> None:
        self.window.refresh_sidebar()

    def on_entry_changed(self, entry_id: str, is_structural: bool = False) -> None:
        self.window.on_entry_changed(entry_id, is_structural)

    def refresh_entry_view(self, entry_id: str) -> None:
        self.window.refresh_entry_view(entry_id)

    def on_reveal_failed(self, path: Path, error: Exception) -> None:
        self.window.messages.on_reveal_failed(path, error)

    def on_open_folder_failed(self, folder: Path, error: Exception) -> None:
        self.window.messages.on_open_folder_failed(folder, error)

    def on_summary_finished(self, entry: HistoryEntry, error: str | None) -> None:
        self.window.messages.on_summary_finished(entry, error)

    def on_translation_finished(self, entry: HistoryEntry, error: str | None) -> None:
        self.window.messages.on_translation_finished(entry, error)

    # QUEUE

    def select_entry(self, entry_id: str) -> None:
        self.window.select_entry(entry_id)

    def refresh_progress(self, entry_id: str) -> None:
        self.window.refresh_progress(entry_id)

    def on_recording_unavailable(self, entry: HistoryEntry) -> None:
        self.window.messages.on_recording_unavailable(entry)

    def on_transcription_finished(
        self, entry: HistoryEntry, status_message: str | None
    ) -> None:
        self.window.messages.on_transcription_finished(entry, status_message)

    def on_transcription_ready(self, entry: HistoryEntry) -> None:
        self.window.messages.on_transcription_ready(entry)

    def on_transcription_saved(self, folder: Path) -> None:
        self.window.messages.on_transcription_saved(folder)

    # MICROPHONE

    def is_recording(self) -> bool:
        return self.window.is_recording()

    def on_mic_progress(self, message: str) -> None:
        self.window.on_mic_progress(message)

    def on_mic_text(self, text: str) -> None:
        self.window.on_mic_text(text)

    def on_mic_finished(self, entry: HistoryEntry) -> None:
        self.window.on_mic_finished(entry)

    def on_recording_progress(self, elapsed_seconds: float, level: float) -> None:
        self.window.on_recording_progress(elapsed_seconds, level)

    def on_stop_recording_from_mic(self) -> None:
        self.window.on_stop_recording_from_mic()

    def on_live_text(self, text: str) -> None:
        self.window.on_live_text(text)

    def on_live_status(self, message: str) -> None:
        self.window.on_live_status(message)
