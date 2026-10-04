"""
Transcribes audio with the OpenAI API.

The API rejects files larger than 25 MB, and the newer models also limit the
duration of the audio, so long audios are split into chunks that are transcribed
one after the other. Each chunk is cut at a silence, so no word is split, and the
timestamps of each chunk are shifted to the position of the chunk in the audio.

The response of each model is turned into segments with timestamps (when the model
returns them), so the transcription can be played and exported like the WhisperX
ones. The response formats of the files saved automatically are generated from
them, since the responses of several chunks can't be joined as they are.
"""

import base64
import bisect
import json
import logging
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from openai import OpenAI
from pydub import AudioSegment
from pydub.silence import detect_silence

import utils.config_manager as cm
from handlers.audio_handler import AudioHandler
from models.config.config_whisper_api import ConfigWhisperApi
from models.transcript_segment import TranscriptSegment, TranscriptWord, join_segments
from models.transcription import Transcription
from utils import constants as c
from utils.cancellation import CancellationToken
from utils.enums import TimestampGranularities, WhisperApiResponseFormats
from utils.env_keys import EnvKeys
from utils.exporters import segments_to_srt, segments_to_vtt
from utils.i18n import _
from utils.progress import ProgressCallback, ignore_progress

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 300.0
# The API rejects larger files
MAX_REQUEST_BYTES = 25 * 1024 * 1024
# The newer models reject longer audios, so every model gets chunks of this length
MAX_CHUNK_MS = 10 * 60 * 1000
# A chunk is cut at the longest silence of its last seconds
SPLIT_SEARCH_MS = 30 * 1000
MIN_SPLIT_SILENCE_MS = 300
# Audio this many decibels below the average loudness is considered silence
SILENCE_THRESHOLD_OFFSET_DB = 16
# Whisper works at 16 kHz, so a higher rate only makes the requests bigger
EXPORT_FRAME_RATE = 16000
EXPORT_BITRATE = "48k"
# Characters of the previous chunk given as context to the next one
PROMPT_CONTEXT_CHARS = 200
# Duration of the samples of each speaker sent with the next chunks, so the
# speakers keep their labels. The API accepts samples of 2 to 10 seconds
SPEAKER_SAMPLE_MIN_MS = 2000
SPEAKER_SAMPLE_MAX_MS = 10000
MAX_KNOWN_SPEAKERS = 4

WHISPER_1 = "whisper-1"
# Translations are always into English
TRANSLATION_LANGUAGE = "en"

ALL_RESPONSE_FORMATS = [
    response_format.value for response_format in WhisperApiResponseFormats
]
TEXT_RESPONSE_FORMATS = [
    WhisperApiResponseFormats.TEXT.value,
    WhisperApiResponseFormats.JSON.value,
]


@dataclass(frozen=True)
class ApiModel:
    """A transcription model of the OpenAI API and what it supports."""

    name: str
    # Format of the responses requested to the API
    api_format: str
    has_timestamps: bool
    has_speakers: bool = False
    supports_prompt: bool = True
    # Takes the context of the audio as the prompt, its keywords and a list of its
    # possible languages. Otherwise, the prompt has the keywords and the end of the
    # previous chunk, and a single language is given
    takes_context_inputs: bool = False
    # Only Whisper translates (into English)
    can_translate: bool = False

    @property
    def response_formats(self) -> list[str]:
        """The formats of the files that can be generated from its responses."""
        return ALL_RESPONSE_FORMATS if self.has_timestamps else TEXT_RESPONSE_FORMATS


API_MODELS = {
    model.name: model
    for model in [
        ApiModel(WHISPER_1, "verbose_json", has_timestamps=True, can_translate=True),
        ApiModel(
            "gpt-transcribe", "json", has_timestamps=False, takes_context_inputs=True
        ),
        ApiModel(
            "gpt-4o-transcribe-diarize",
            "diarized_json",
            has_timestamps=True,
            has_speakers=True,
            supports_prompt=False,
        ),
    ]
}


def get_api_model(name: str | None) -> ApiModel:
    """
    :param name: The name of the model. Models unknown to this version are
                 assumed to only return text.
    """
    if not name:
        return API_MODELS[WHISPER_1]

    return API_MODELS.get(name) or ApiModel(name, "json", has_timestamps=False)


@dataclass
class ApiTranscript:
    """The result of transcribing an audio with the API."""

    text: str
    segments: list[TranscriptSegment]
    language: str | None
    duration: float


def plan_chunks(audio: AudioSegment, max_ms: int) -> list[tuple[int, int]]:
    """
    Splits the audio into chunks no longer than `max_ms`, cutting each one at the
    longest silence of its last seconds (or at the limit, if there is none).

    :return: The start and end of each chunk, in milliseconds.
    """
    total_ms = len(audio)
    if total_ms <= max_ms:
        return [(0, total_ms)]

    # A silent audio has no loudness, so no part is quieter than the rest
    silence_threshold = audio.dBFS - SILENCE_THRESHOLD_OFFSET_DB
    chunks = []
    start = 0

    while total_ms - start > max_ms:
        limit = start + max_ms
        window_start = max(limit - SPLIT_SEARCH_MS, start + 1)
        silences = detect_silence(
            audio[window_start:limit],
            min_silence_len=MIN_SPLIT_SILENCE_MS,
            silence_thresh=silence_threshold,
            seek_step=10,
        )

        if silences:
            silence_start, silence_end = max(silences, key=lambda s: s[1] - s[0])
            end = window_start + (silence_start + silence_end) // 2
        else:
            end = limit

        chunks.append((start, end))
        start = end

    chunks.append((start, total_ms))
    return chunks


def build_prompt(user_prompt: str, previous_text: str) -> str:
    """
    Joins the prompt of the user and the end of the previous chunk, which helps
    Whisper to keep the style and the spelling of the names between chunks.
    """
    context = previous_text[-PROMPT_CONTEXT_CHARS:]
    if len(previous_text) > PROMPT_CONTEXT_CHARS and " " in context:
        # Starts at a whole word
        context = context.split(" ", 1)[1]

    return " ".join(part for part in (user_prompt.strip(), context.strip()) if part)


def language_code(name: str | None) -> str | None:
    """
    Whisper returns the name of the language in English (e.g. "spanish").

    :return: Its ISO 639-1 code, or None if it's unknown.
    """
    if not name:
        return None

    name = name.casefold()
    if name in c.AUDIO_LANGUAGES:
        return name

    return next(
        (
            code
            for code, language in c.AUDIO_LANGUAGES.items()
            if language.casefold() == name
        ),
        None,
    )


def detected_language(data: dict[str, Any]) -> str | None:
    """
    Whisper returns the language of the audio, while `gpt-transcribe` returns the
    languages it detected (the first one is taken).

    :return: Its ISO 639-1 code, or None if it's unknown.
    """
    if languages := data.get("languages"):
        return language_code(languages[0].get("code"))

    return language_code(data.get("language"))


def render_response(transcript: ApiTranscript, response_format: str) -> str:
    """
    Writes the transcription in one of the response formats of the API, to save
    it in a file.
    """
    segments = transcript.segments or [
        TranscriptSegment(0, transcript.duration, transcript.text)
    ]

    if response_format == WhisperApiResponseFormats.SRT.value:
        return segments_to_srt(segments)
    if response_format == WhisperApiResponseFormats.VTT.value:
        return segments_to_vtt(segments)
    if response_format == WhisperApiResponseFormats.JSON.value:
        return json.dumps({"text": transcript.text}, ensure_ascii=False)
    if response_format == WhisperApiResponseFormats.VERBOSE_JSON.value:
        data: dict[str, Any] = {
            "task": "transcribe",
            "language": transcript.language,
            "duration": transcript.duration,
            "text": transcript.text,
            "segments": [
                {"id": idx} | segment.to_dict()
                for idx, segment in enumerate(transcript.segments)
            ],
        }
        return json.dumps(data, ensure_ascii=False, indent=2)

    return transcript.text


def _to_dict(response: Any) -> dict[str, Any]:
    if isinstance(response, str):
        return {"text": response}

    data: dict[str, Any] = response.model_dump()
    return data


def _parse_segments(data: dict[str, Any], offset: float) -> list[TranscriptSegment]:
    """
    Reads the segments of a response, shifting their timestamps by the start of
    the chunk. The words are returned apart from the segments, so they are
    assigned to the segment they belong to.
    """
    segments = [
        TranscriptSegment(
            start=offset + float(segment["start"]),
            end=offset + float(segment["end"]),
            text=str(segment["text"]).strip(),
            speaker=segment.get("speaker"),
        )
        for segment in data.get("segments") or []
        if str(segment["text"]).strip()
    ]
    words = [
        TranscriptWord(
            offset + float(word["start"]),
            offset + float(word["end"]),
            str(word["word"]).strip(),
        )
        for word in data.get("words") or []
    ]

    if not words or not segments:
        return segments

    starts = [segment.start for segment in segments]
    words_by_segment: list[list[TranscriptWord]] = [[] for _segment in segments]
    for word in words:
        idx = max(bisect.bisect_right(starts, word.start) - 1, 0)
        words_by_segment[idx].append(word)

    return [
        TranscriptSegment(
            segment.start,
            segment.end,
            segment.text,
            segment.speaker,
            tuple(segment_words),
        )
        for segment, segment_words in zip(segments, words_by_segment, strict=True)
    ]


class OpenAiApiHandler:
    @staticmethod
    def transcribe_file(
        transcription: Transcription,
        on_progress: ProgressCallback = ignore_progress,
        cancellation_token: CancellationToken | None = None,
    ) -> ApiTranscript:
        """
        Transcribes the audio of a file with the OpenAI API.

        :param transcription: The file and the options of the transcription.
        :param on_progress: Called before transcribing each chunk.
        :param cancellation_token: Checked before each request to abort the process.
        :raises ValueError: If the file type is not supported.
        :raises TranscriptionCancelledError: If the token is cancelled.
        :return: The transcription, with its timestamps if the model returns them.
        """
        token = cancellation_token or CancellationToken()
        config = cm.ConfigManager.get_config_whisper_api()
        model = get_api_model(transcription.api_model or config.model)
        if transcription.should_translate and not model.can_translate:
            logger.info("%s can't translate, so %s is used", model.name, WHISPER_1)
            model = API_MODELS[WHISPER_1]

        on_progress(_("Loading audio…"), None)
        audio = (
            AudioHandler.load_audio_file(transcription.audio_source_path)
            .set_channels(1)
            .set_frame_rate(EXPORT_FRAME_RATE)
        )
        chunks = plan_chunks(audio, MAX_CHUNK_MS)

        client = OpenAI(
            api_key=EnvKeys.OPENAI_API_KEY.get_value(),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        segments: list[TranscriptSegment] = []
        texts: list[str] = []
        language = (
            TRANSLATION_LANGUAGE
            if transcription.should_translate
            else transcription.language_code
        )
        speaker_samples: dict[str, str] = {}

        for idx, (start_ms, end_ms) in enumerate(chunks):
            token.raise_if_cancelled()

            if len(chunks) == 1:
                on_progress(_("Transcribing…"), None)
            else:
                on_progress(
                    _("Transcribing chunk {current} of {total}…").format(
                        current=idx + 1, total=len(chunks)
                    ),
                    idx / len(chunks),
                )

            chunk = audio[start_ms:end_ms]
            response = OpenAiApiHandler._request(
                client,
                model,
                chunk,
                transcription,
                config,
                prompt=(
                    transcription.prompt.strip()
                    if model.takes_context_inputs
                    else build_prompt(transcription.whisper_prompt, " ".join(texts))
                ),
                speaker_samples=speaker_samples,
            )
            data = _to_dict(response)
            chunk_segments = _parse_segments(data, offset=start_ms / 1000)

            if model.has_speakers:
                chunk_segments = OpenAiApiHandler._label_speakers(chunk_segments)
                OpenAiApiHandler._add_speaker_samples(
                    speaker_samples, chunk, chunk_segments, offset_ms=start_ms
                )

            segments.extend(chunk_segments)
            if text := str(data.get("text", "")).strip():
                texts.append(text)
            if not language:
                language = detected_language(data)

        has_speakers = any(segment.speaker for segment in segments)
        return ApiTranscript(
            text=join_segments(segments) if has_speakers else " ".join(texts),
            segments=segments if model.has_timestamps else [],
            language=language,
            duration=len(audio) / 1000,
        )

    @staticmethod
    def _request(
        client: OpenAI,
        model: ApiModel,
        chunk: AudioSegment,
        transcription: Transcription,
        config: ConfigWhisperApi,
        prompt: str,
        speaker_samples: dict[str, str],
    ) -> Any:
        params: dict[str, Any] = {
            "model": model.name,
            "file": OpenAiApiHandler._encode(chunk),
            "response_format": model.api_format,
            "temperature": config.temperature,
        }

        if prompt and model.supports_prompt:
            params["prompt"] = prompt

        # Translations don't take the language of the audio nor the timestamps
        if transcription.should_translate:
            return client.audio.translations.create(**params)

        # Without a language, the API detects it
        if transcription.language_code and model.takes_context_inputs:
            params["languages"] = [transcription.language_code]
        elif transcription.language_code:
            params["language"] = transcription.language_code

        if transcription.keywords and model.takes_context_inputs:
            params["keywords"] = transcription.keywords

        # The segments are always requested, since they have the timestamps
        if model.api_format == WhisperApiResponseFormats.VERBOSE_JSON.value:
            params["timestamp_granularities"] = [
                TimestampGranularities.SEGMENT.value,
                *(
                    [TimestampGranularities.WORD.value]
                    if TimestampGranularities.WORD.value
                    in config.timestamp_granularities
                    else []
                ),
            ]

        if model.has_speakers:
            # Required for audios longer than 30 seconds
            params["chunking_strategy"] = "auto"
            if speaker_samples:
                params["known_speaker_names"] = list(speaker_samples)
                params["known_speaker_references"] = list(speaker_samples.values())

        return client.audio.transcriptions.create(**params)

    @staticmethod
    def _encode(chunk: AudioSegment) -> BytesIO:
        """
        Compresses the audio to MP3, to reduce the size of the request.

        :raises ValueError: If the audio is still too large for the API.
        """
        file = BytesIO()
        chunk.export(file, format="mp3", bitrate=EXPORT_BITRATE)
        size = len(file.getvalue())
        logger.info("Compressed audio size: %.2f MB", size / (1024 * 1024))

        if size > MAX_REQUEST_BYTES:
            raise ValueError(
                _("The audio is too large for the OpenAI API ({size} MB).").format(
                    size=round(size / (1024 * 1024))
                )
            )

        file.seek(0)
        # The API identifies the format by the name of the file
        file.name = "audiotext-audio.mp3"
        return file

    @staticmethod
    def _label_speakers(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
        """
        Names the speakers like WhisperX does. The API labels them with letters (A,
        B…), or with the names of the samples sent with the request.
        """
        return [
            TranscriptSegment(
                segment.start,
                segment.end,
                segment.text,
                segment.speaker
                if not segment.speaker or segment.speaker.startswith("SPEAKER_")
                else f"SPEAKER_{segment.speaker}",
                segment.words,
            )
            for segment in segments
        ]

    @staticmethod
    def _add_speaker_samples(
        samples: dict[str, str],
        chunk: AudioSegment,
        segments: list[TranscriptSegment],
        offset_ms: int,
    ) -> None:
        """
        Keeps a sample of the voice of each new speaker, which is sent with the next
        chunks so the API gives the same speaker the same label in all of them.
        """
        for segment in sorted(segments, key=lambda s: s.end - s.start, reverse=True):
            speaker = segment.speaker
            if not speaker or speaker in samples or len(samples) >= MAX_KNOWN_SPEAKERS:
                continue

            start_ms = round(segment.start * 1000) - offset_ms
            end_ms = min(
                round(segment.end * 1000) - offset_ms, start_ms + SPEAKER_SAMPLE_MAX_MS
            )
            if end_ms - start_ms < SPEAKER_SAMPLE_MIN_MS:
                continue

            file = BytesIO()
            chunk[start_ms:end_ms].export(file, format="wav")
            encoded = base64.b64encode(file.getvalue()).decode("ascii")
            samples[speaker] = f"data:audio/wav;base64,{encoded}"
