from pathlib import Path
from typing import Protocol

from models.transcription import Transcription, TranscriptionResult
from utils.cancellation import CancellationToken
from utils.progress import ProgressCallback


class Transcriber(Protocol):
    """A transcription method, which transcribes files and saves their results."""

    def transcribe(
        self,
        transcription: Transcription,
        on_progress: ProgressCallback,
        cancellation_token: CancellationToken,
    ) -> TranscriptionResult:
        """
        Transcribes the file of `transcription.audio_source_path`.

        :raises TranscriptionCancelledError: If the token is cancelled.
        """
        ...

    def save(
        self, result: TranscriptionResult, transcription: Transcription, file_path: Path
    ) -> None:
        """
        Saves the result in the output file types of the transcription.

        :param file_path: The path of the output files. If there are several output
                          file types, each one replaces its extension.
        :raises ValueError: If there is no text to save.
        """
        ...
