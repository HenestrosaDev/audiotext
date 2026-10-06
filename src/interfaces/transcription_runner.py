from typing import Protocol

from models.transcription import Transcription


class TranscriptionRunner(Protocol):
    """Runs the transcriptions in the background (see `MainController`)."""

    def prepare_for_transcription(self, transcription: Transcription) -> None:
        """Validates the transcription and starts it in the background."""

    def cancel_transcription(self) -> None: ...

    def stop_recording_from_mic(self) -> None:
        """Stops the recording, which is transcribed right after."""

    def preload_model(self) -> None:
        """Loads the model of the current configuration, if it's needed."""
