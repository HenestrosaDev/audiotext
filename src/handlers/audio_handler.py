import logging
from collections.abc import Callable
from pathlib import Path

import speech_recognition as sr
from pydub import AudioSegment
from pydub.silence import split_on_silence

from models.transcription import Transcription
from utils import constants as c
from utils.audio_utils import audio_segment_to_audio_data
from utils.cancellation import CancellationToken
from utils.i18n import _
from utils.progress import ProgressCallback, ignore_progress

logger = logging.getLogger(__name__)

TranscriptionFunc = Callable[[sr.AudioData, Transcription], str]

# Minimum duration (ms) of silence required to consider a segment as a split point
MIN_SILENCE_LEN_MS = 500
# Audio this many decibels below the average loudness is considered silence
SILENCE_THRESHOLD_OFFSET_DB = 40
# Silence (ms) kept at the beginning and end of each chunk
KEEP_SILENCE_MS = 100


class AudioHandler:
    @staticmethod
    def get_transcription(
        transcription: Transcription,
        should_split_on_silence: bool,
        transcription_func: TranscriptionFunc,
        on_progress: ProgressCallback = ignore_progress,
        cancellation_token: CancellationToken | None = None,
    ) -> str:
        """
        Transcribes the audio of the file referenced by `transcription` using the
        given transcription function.

        :param transcription: An instance of Transcription containing information
                              about the audio file.
        :param should_split_on_silence: Whether the audio should be split into chunks
                                        based on silence, transcribing each chunk
                                        separately. Useful for APIs that limit the
                                        duration of the audio per request.
        :param transcription_func: The function to use for transcription.
        :param on_progress: Called with the progress of the transcription.
        :param cancellation_token: Checked between chunks to abort the process.
        :raises ValueError: If the file type is not supported.
        :raises TranscriptionCancelledError: If the token is cancelled.
        :return: The transcribed text.
        """
        on_progress(_("Loading audio…"), None)
        audio = AudioHandler.load_audio_file(transcription.audio_source_path)

        if should_split_on_silence:
            audio_chunks = AudioHandler.split_audio_into_chunks(audio)
        else:
            audio_chunks = [audio]

        return AudioHandler.process_audio_chunks(
            audio_chunks,
            transcription,
            transcription_func,
            on_progress,
            cancellation_token,
        )

    @staticmethod
    def load_audio_file(file_path: Path) -> AudioSegment:
        """
        Loads the audio from an audio file or the audio track from a video file.

        :param file_path: Path to the file to be loaded.
        :raises ValueError: If the file type is not supported.
        :return: The loaded audio.
        """
        if file_path.suffix.lower() not in c.SUPPORTED_FILE_EXTENSIONS:
            raise ValueError(
                _("Unsupported file type: {extension}").format(
                    extension=file_path.suffix
                )
            )

        # FFmpeg extracts the audio track when the file is a video
        return AudioSegment.from_file(file_path)

    @staticmethod
    def split_audio_into_chunks(sound: AudioSegment) -> list[AudioSegment]:
        """
        Split the audio into chunks based on silence.

        :param sound: The audio to be split.
        :return: List of audio chunks.
        """
        chunks: list[AudioSegment] = split_on_silence(
            sound,
            min_silence_len=MIN_SILENCE_LEN_MS,
            silence_thresh=sound.dBFS - SILENCE_THRESHOLD_OFFSET_DB,
            keep_silence=KEEP_SILENCE_MS,
        )
        return chunks

    @staticmethod
    def process_audio_chunks(
        audio_chunks: list[AudioSegment],
        transcription: Transcription,
        transcription_func: TranscriptionFunc,
        on_progress: ProgressCallback = ignore_progress,
        cancellation_token: CancellationToken | None = None,
    ) -> str:
        """
        Transcribes each audio chunk and joins the results. Chunks without
        recognizable speech are skipped.

        :param audio_chunks: List of audio chunks.
        :param transcription: Transcription object containing transcription details.
        :param transcription_func: The function to use for transcription.
        :param on_progress: Called before transcribing each chunk.
        :param cancellation_token: Checked between chunks to abort the process.
        :raises TranscriptionCancelledError: If the token is cancelled.
        :return: The combined transcribed text.
        """
        token = cancellation_token or CancellationToken()
        texts = []

        for idx, audio_chunk in enumerate(audio_chunks):
            token.raise_if_cancelled()

            if len(audio_chunks) == 1:
                on_progress(_("Transcribing…"), None)
            else:
                on_progress(
                    _("Transcribing chunk {current} of {total}…").format(
                        current=idx + 1, total=len(audio_chunks)
                    ),
                    idx / len(audio_chunks),
                )

            audio_data = audio_segment_to_audio_data(audio_chunk)

            try:
                texts.append(transcription_func(audio_data, transcription))
            except sr.UnknownValueError:
                logger.info("No speech recognized in chunk %d. Skipping.", idx)

        return "".join(texts).strip()
