"""
The transcription methods behind the `Transcriber` interface, so the controller
doesn't depend on how each method transcribes and saves its results.
"""

from pathlib import Path

import utils.config_manager as cm
from handlers.audio_handler import AudioHandler
from handlers.google_api_handler import GoogleApiHandler
from handlers.openai_api_handler import ApiTranscript, OpenAiApiHandler, render_response
from handlers.whisperx_handler import WhisperXHandler
from interfaces.transcriber import Transcriber
from models.transcription import Transcription, TranscriptionResult
from utils.cancellation import CancellationToken
from utils.enums import TranscriptionMethod
from utils.i18n import _
from utils.progress import ProgressCallback


def ensure_text(text: str) -> None:
    """
    :raises ValueError: If there is no text to save.
    """
    if not text:
        raise ValueError(
            _("There is no transcription to save. Please generate it first.")
        )


def write_text(file_path: Path, text: str, should_overwrite: bool) -> None:
    """
    :raises ValueError: If there is no text to write.
    """
    ensure_text(text)

    if should_overwrite or not file_path.exists():
        file_path.write_text(text, encoding="utf-8")


class WhisperXTranscriber:
    def __init__(self, handler: WhisperXHandler) -> None:
        self._handler = handler

    def transcribe(
        self,
        transcription: Transcription,
        on_progress: ProgressCallback,
        cancellation_token: CancellationToken,
    ) -> TranscriptionResult:
        text = self._handler.transcribe_file(
            transcription, on_progress, cancellation_token
        )
        return TranscriptionResult(
            text, self._handler.segments, self._handler.result_language
        )

    def save(
        self, result: TranscriptionResult, transcription: Transcription, file_path: Path
    ) -> None:
        # The WhisperX writers need the result of the handler, which has the timings
        # of the words and the speakers. The controller saves each file right after
        # transcribing it, so the handler still keeps it
        self._handler.save_transcription(
            file_path=file_path,
            output_file_types=transcription.output_file_types,
            should_overwrite=transcription.should_overwrite,
        )


class GoogleApiTranscriber:
    def transcribe(
        self,
        transcription: Transcription,
        on_progress: ProgressCallback,
        cancellation_token: CancellationToken,
    ) -> TranscriptionResult:
        text = AudioHandler.get_transcription(
            transcription=transcription,
            transcription_func=GoogleApiHandler.transcribe,
            # Splitting avoids exceeding the duration limit of each request
            should_split_on_silence=True,
            on_progress=on_progress,
            cancellation_token=cancellation_token,
        )
        return TranscriptionResult(text)

    def save(
        self, result: TranscriptionResult, transcription: Transcription, file_path: Path
    ) -> None:
        write_text(file_path, result.text, transcription.should_overwrite)


class OpenAiApiTranscriber:
    def transcribe(
        self,
        transcription: Transcription,
        on_progress: ProgressCallback,
        cancellation_token: CancellationToken,
    ) -> TranscriptionResult:
        transcript = OpenAiApiHandler.transcribe_file(
            transcription, on_progress, cancellation_token
        )
        return TranscriptionResult(
            transcript.text,
            transcript.segments,
            transcript.language,
            transcript.duration,
        )

    def save(
        self, result: TranscriptionResult, transcription: Transcription, file_path: Path
    ) -> None:
        """Saves the result in the response format of the API."""
        ensure_text(result.text)
        response_format = (
            transcription.api_response_format
            or cm.ConfigManager.get_config_whisper_api().response_format
        )
        transcript = ApiTranscript(
            result.text, result.segments, result.language, result.duration
        )
        write_text(
            file_path,
            render_response(transcript, response_format),
            transcription.should_overwrite,
        )


def create_transcribers(
    whisperx_handler: WhisperXHandler,
) -> dict[TranscriptionMethod, Transcriber]:
    return {
        TranscriptionMethod.WHISPERX: WhisperXTranscriber(whisperx_handler),
        TranscriptionMethod.GOOGLE_API: GoogleApiTranscriber(),
        TranscriptionMethod.WHISPER_API: OpenAiApiTranscriber(),
    }
