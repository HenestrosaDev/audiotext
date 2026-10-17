from pathlib import Path
from typing import Protocol

from models.transcription import Transcription


class TranscriptionRunner(Protocol):
    """Runs the transcriptions in the background (see `MainController`)."""

    def prepare_for_transcription(self, transcription: Transcription) -> None:
        """Validates the transcription and starts it in the background."""

    def cancel_transcription(self) -> None: ...

    def pause_watch(self, is_urgent: bool = False) -> bool:
        """
        Pauses the folder being watched, so something else can be transcribed.

        :param is_urgent: Whether to stop the file being transcribed right away.
        :return: Whether it'll be paused, which it isn't if no folder is watched.
        """
        ...

    def retranscribe_files(self, files: list[Path]) -> bool:
        """
        Transcribes some files of the folder being transcribed again.

        :return: Whether they'll be transcribed, which they aren't if no folder is
                 being transcribed or it's already done.
        """
        ...

    def stop_recording_from_mic(self) -> None:
        """Stops the recording, which is transcribed right after."""

    def preload_model(self) -> None:
        """Loads the model of the current configuration, if it's needed."""
