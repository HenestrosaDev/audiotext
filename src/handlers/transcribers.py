"""
The transcription methods behind the `Transcriber` interface, so the controller
doesn't depend on how each method transcribes and saves its results.
"""

from pathlib import Path

import handlers.google_api_handler as google_api
import utils.config_manager as cm
from handlers.audio_handler import get_transcription
from handlers.openai_api_handler import ApiTranscript, OpenAiApiHandler, render_response
from handlers.whisperx_handler import WhisperXHandler
from interfaces.transcriber import Transcriber
from models.transcription import Transcription, TranscriptionResult
from utils.cancellation import CancellationToken
from utils.enums import TranscriptionMethod
from utils.i18n import _
from utils.media import is_vertical_video
from utils.progress import ProgressCallback


def ensure_text(text: str) -> None:
    """
    :raises ValueError: If there is no text to save.
    """
    if not text:
        raise ValueError(
            _("There is no transcription to save. Please generate it first.")
        )


def has_vertical_video(transcription: Transcription) -> bool:
    """Whether the transcribed file is a video taller than it's wide."""
    return is_vertical_video(
        transcription.media_path or transcription.audio_source_path
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
            text,
            self._handler.segments,
            self._handler.result_language,
            raw=self._handler.raw_result,
        )

    def save(
        self, result: TranscriptionResult, transcription: Transcription, file_path: Path
    ) -> None:
        # The WhisperX writers need the result as WhisperX returns it, which has
        # the timings of the words and the speakers
        self._handler.save_transcription(
            result=result.raw,
            file_path=file_path,
            output_file_types=transcription.output_file_types,
            should_overwrite=transcription.should_overwrite,
            is_vertical=has_vertical_video(transcription),
        )


class GoogleApiTranscriber:
    def transcribe(
        self,
        transcription: Transcription,
        on_progress: ProgressCallback,
        cancellation_token: CancellationToken,
    ) -> TranscriptionResult:
        text = get_transcription(
            transcription=transcription,
            transcription_func=google_api.transcribe,
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
    def __init__(self, handler: OpenAiApiHandler | None = None) -> None:
        self._handler = handler or OpenAiApiHandler()

    def transcribe(
        self,
        transcription: Transcription,
        on_progress: ProgressCallback,
        cancellation_token: CancellationToken,
    ) -> TranscriptionResult:
        transcript = self._handler.transcribe_file(
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
            render_response(
                transcript, response_format, has_vertical_video(transcription)
            ),
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
