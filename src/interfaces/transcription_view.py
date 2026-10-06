from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from models.transcript_segment import TranscriptSegment


class RecordingView(Protocol):
    """
    What the controller needs from a view to show a recording from the microphone
    while it's being made. They're always called from the UI thread.
    """

    def on_recording_progress(self, elapsed_seconds: float, level: float) -> None: ...

    def on_stop_recording_from_mic(self) -> None: ...

    def on_live_text(self, text: str) -> None:
        """Shows the text of the recording in progress, as it's said."""

    def on_live_status(self, message: str) -> None: ...


class TranscriptionView(Protocol):
    """
    What the controller needs from a view to report the progress and the result of
    a transcription. The controller calls these methods through
    `run_on_ui_thread`, so they're always called from the UI thread.
    """

    def run_on_ui_thread(self, callback: Callable[..., Any], *args: Any) -> None:
        """
        Schedules a callback to be run on the UI thread, since the transcription
        runs in a background thread.
        """

    def display_text(self, text: str) -> None:
        """Shows the transcribed text, or the status of the files of a folder."""

    def show_status(self, message: str) -> None:
        """Shows a message that is not related to a transcription in progress."""

    def show_error(self, message: str) -> None: ...

    def on_transcription_progress(self, message: str, fraction: float | None) -> None:
        """
        :param fraction: The completed fraction (between 0 and 1), or None if the
                         progress can't be measured.
        """

    def on_processed_transcription(self, status: str | None = None) -> None:
        """
        Called once the transcription finishes, is cancelled or fails.

        :param status: A summary of the result, or None if it failed.
        """

    def on_transcription_saved(self, folder: Path) -> None: ...

    def on_media_downloaded(self, file_path: Path) -> None: ...

    def on_files_queued(self, files: list[Path]) -> None:
        """Called with the files of a folder before transcribing them."""

    def on_file_started(self, file_path: Path) -> None: ...

    def on_file_transcribed(
        self,
        file_path: Path,
        text: str,
        segments: list[TranscriptSegment],
        language: str | None,
    ) -> None: ...

    def on_file_failed(self, file_path: Path, error: str) -> None: ...


class IgnoreHistoryEvents:
    """
    Ignores the events that the history of the main window needs, for views that
    don't keep a history of the transcriptions (e.g. the command line).
    """

    def on_live_text(self, text: str) -> None:
        pass

    def on_live_status(self, message: str) -> None:
        pass

    def on_media_downloaded(self, file_path: Path) -> None:
        pass

    def on_files_queued(self, files: list[Path]) -> None:
        pass

    def on_file_started(self, file_path: Path) -> None:
        pass

    def on_file_transcribed(
        self,
        file_path: Path,
        text: str,
        segments: list[TranscriptSegment],
        language: str | None,
    ) -> None:
        pass

    def on_file_failed(self, file_path: Path, error: str) -> None:
        pass
