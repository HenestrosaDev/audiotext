import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from openai.types.audio import Transcription as OpenAiTranscription
from openai.types.audio import TranscriptionDiarized, TranscriptionVerbose
from pydub import AudioSegment

import handlers.openai_api_handler as openai_api_handler
from handlers.openai_api_handler import (
    ApiTranscript,
    OpenAiApiHandler,
    build_prompt,
    get_api_model,
    language_code,
    plan_chunks,
    render_response,
)
from models.config.config_whisper_api import ConfigWhisperApi
from models.transcript_segment import TranscriptSegment, TranscriptWord
from models.transcription import Transcription
from tests.conftest import make_tone
from utils.cancellation import CancellationToken, TranscriptionCancelledError
from utils.config_manager import ConfigManager


@pytest.fixture
def openai_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    client = MagicMock()
    monkeypatch.setattr(openai_api_handler, "OpenAI", MagicMock(return_value=client))
    return client


@pytest.fixture
def audio_file(tmp_path: Path) -> Path:
    path = tmp_path / "audio.wav"
    make_tone(duration_ms=500).export(path, format="wav")
    return path


def verbose_segment(start: float, end: float, text: str) -> dict[str, Any]:
    return {
        "id": 0,
        "seek": 0,
        "start": start,
        "end": end,
        "text": text,
        "tokens": [],
        "temperature": 0.0,
        "avg_logprob": 0.0,
        "compression_ratio": 1.0,
        "no_speech_prob": 0.0,
    }


def verbose_response(
    segments: list[dict[str, Any]],
    words: list[dict[str, Any]] | None = None,
    language: str = "english",
) -> TranscriptionVerbose:
    return TranscriptionVerbose.model_validate(
        {
            "duration": 1.0,
            "language": language,
            "text": "".join(segment["text"] for segment in segments).strip(),
            "segments": segments,
            "words": words,
        }
    )


def diarized_response(segments: list[tuple[float, float, str, str]]) -> Any:
    return TranscriptionDiarized.model_validate(
        {
            "duration": 1.0,
            "task": "transcribe",
            "text": " ".join(text for _start, _end, _speaker, text in segments),
            "segments": [
                {
                    "id": str(idx),
                    "start": start,
                    "end": end,
                    "speaker": speaker,
                    "text": text,
                    "type": "transcript.text.segment",
                }
                for idx, (start, end, speaker, text) in enumerate(segments)
            ],
        }
    )


def make_transcription(audio_file: Path, **kwargs: Any) -> Transcription:
    return Transcription(audio_source_path=audio_file, **kwargs)


def set_config(key: ConfigWhisperApi.Key, value: str) -> None:
    ConfigManager.modify_value(ConfigWhisperApi.Key.SECTION, key, value)


def request_params(openai_client: MagicMock, idx: int = -1) -> dict[str, Any]:
    params: dict[str, Any] = openai_client.audio.transcriptions.create.call_args_list[
        idx
    ].kwargs
    return params


def test_whisper_returns_segments_with_their_words(
    openai_client: MagicMock, audio_file: Path
) -> None:
    openai_client.audio.transcriptions.create.return_value = verbose_response(
        [verbose_segment(0.0, 0.2, " Hello"), verbose_segment(0.2, 0.5, " world.")],
        words=[
            {"word": "Hello", "start": 0.0, "end": 0.2},
            {"word": "world.", "start": 0.25, "end": 0.5},
        ],
    )

    result = OpenAiApiHandler.transcribe_file(make_transcription(audio_file))

    assert result.text == "Hello world."
    assert result.language == "en"
    assert result.segments == [
        TranscriptSegment(
            0.0, 0.2, "Hello", words=(TranscriptWord(0.0, 0.2, "Hello"),)
        ),
        TranscriptSegment(
            0.2, 0.5, "world.", words=(TranscriptWord(0.25, 0.5, "world."),)
        ),
    ]
    params = request_params(openai_client)
    assert params["model"] == "whisper-1"
    assert params["response_format"] == "verbose_json"
    assert params["timestamp_granularities"] == ["segment", "word"]
    assert params["file"].name == "audiotext-audio.mp3"
    assert "language" not in params
    assert "prompt" not in params


def test_only_segment_timestamps_are_requested_if_configured(
    openai_client: MagicMock, audio_file: Path
) -> None:
    set_config(ConfigWhisperApi.Key.TIMESTAMP_GRANULARITIES, "segment")
    openai_client.audio.transcriptions.create.return_value = verbose_response(
        [verbose_segment(0.0, 0.5, "Hello")]
    )

    OpenAiApiHandler.transcribe_file(make_transcription(audio_file, language_code="es"))

    params = request_params(openai_client)
    assert params["timestamp_granularities"] == ["segment"]
    assert params["language"] == "es"


def test_gpt_transcribe_returns_text_without_timestamps(
    openai_client: MagicMock, audio_file: Path
) -> None:
    openai_client.audio.transcriptions.create.return_value = OpenAiTranscription(
        text="Hello world."
    )

    result = OpenAiApiHandler.transcribe_file(
        make_transcription(
            audio_file,
            api_model="gpt-transcribe",
            prompt=" An interview ",
            keywords=["Audiotext", "WhisperX"],
        )
    )

    assert result == ApiTranscript("Hello world.", [], None, 0.5)
    params = request_params(openai_client)
    assert params["model"] == "gpt-transcribe"
    assert params["response_format"] == "json"
    # The context and the keywords are given apart
    assert params["prompt"] == "An interview"
    assert params["keywords"] == ["Audiotext", "WhisperX"]
    assert "timestamp_granularities" not in params


def test_gpt_transcribe_takes_a_list_of_languages(
    openai_client: MagicMock, audio_file: Path
) -> None:
    openai_client.audio.transcriptions.create.return_value = OpenAiTranscription(
        text="Hola"
    )

    OpenAiApiHandler.transcribe_file(
        make_transcription(audio_file, api_model="gpt-transcribe", language_code="es")
    )

    params = request_params(openai_client)
    assert params["languages"] == ["es"]
    assert "language" not in params


def test_gpt_transcribe_returns_the_detected_language(
    openai_client: MagicMock, audio_file: Path
) -> None:
    openai_client.audio.transcriptions.create.return_value = (
        OpenAiTranscription.model_validate(
            {"text": "Hola", "languages": [{"code": "es"}, {"code": "en"}]}
        )
    )

    result = OpenAiApiHandler.transcribe_file(
        make_transcription(audio_file, api_model="gpt-transcribe")
    )

    assert result.language == "es"
    assert "languages" not in request_params(openai_client)


def test_gpt_transcribe_doesnt_get_the_previous_chunk_as_prompt(
    openai_client: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(openai_api_handler, "MAX_CHUNK_MS", 1500)
    audio_file = long_audio(tmp_path, tones=2, tone_ms=800, silence_ms=600)
    openai_client.audio.transcriptions.create.side_effect = [
        OpenAiTranscription(text=f"Part {idx}.") for idx in range(1, 3)
    ]

    result = OpenAiApiHandler.transcribe_file(
        make_transcription(audio_file, api_model="gpt-transcribe", prompt="A talk")
    )

    assert result.text == "Part 1. Part 2."
    assert request_params(openai_client, 0)["prompt"] == "A talk"
    assert request_params(openai_client, 1)["prompt"] == "A talk"
    assert "keywords" not in request_params(openai_client, 1)


def test_the_configured_model_is_used_by_default(
    openai_client: MagicMock, audio_file: Path
) -> None:
    set_config(ConfigWhisperApi.Key.MODEL, "gpt-transcribe")
    openai_client.audio.transcriptions.create.return_value = OpenAiTranscription(
        text="Hi"
    )

    OpenAiApiHandler.transcribe_file(make_transcription(audio_file))

    assert request_params(openai_client)["model"] == "gpt-transcribe"


def test_translations_always_use_whisper(
    openai_client: MagicMock, audio_file: Path
) -> None:
    openai_client.audio.translations.create.return_value = verbose_response(
        [verbose_segment(0.0, 0.5, "Hello")], language="spanish"
    )

    result = OpenAiApiHandler.transcribe_file(
        make_transcription(
            audio_file,
            api_model="gpt-transcribe",
            language_code="es",
            should_translate=True,
        )
    )

    openai_client.audio.transcriptions.create.assert_not_called()
    params = openai_client.audio.translations.create.call_args.kwargs
    assert params["model"] == "whisper-1"
    assert "language" not in params
    assert "timestamp_granularities" not in params
    assert result.language == "en"
    assert result.text == "Hello"


def test_diarization_labels_the_speakers(
    openai_client: MagicMock, audio_file: Path
) -> None:
    openai_client.audio.transcriptions.create.return_value = diarized_response(
        [(0.0, 0.2, "A", "Hi."), (0.2, 0.4, "B", "Hello."), (0.4, 0.5, "B", "Bye.")]
    )

    result = OpenAiApiHandler.transcribe_file(
        make_transcription(
            audio_file, api_model="gpt-4o-transcribe-diarize", prompt="ignored"
        )
    )

    assert [segment.speaker for segment in result.segments] == [
        "SPEAKER_A",
        "SPEAKER_B",
        "SPEAKER_B",
    ]
    assert result.text == "[SPEAKER_A]: Hi.\n\n[SPEAKER_B]: Hello. Bye."
    params = request_params(openai_client)
    assert params["response_format"] == "diarized_json"
    assert params["chunking_strategy"] == "auto"
    # The diarization model doesn't accept a prompt
    assert "prompt" not in params


def long_audio(tmp_path: Path, tones: int, tone_ms: int, silence_ms: int) -> Path:
    silence = AudioSegment.silent(duration=silence_ms, frame_rate=44100)
    audio = make_tone(tone_ms)
    for _idx in range(tones - 1):
        audio += silence + make_tone(tone_ms)
    path = tmp_path / "long.wav"
    audio.export(path, format="wav")
    return path


def test_long_audios_are_transcribed_in_chunks(
    openai_client: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(openai_api_handler, "MAX_CHUNK_MS", 1500)
    audio_file = long_audio(tmp_path, tones=3, tone_ms=800, silence_ms=600)
    openai_client.audio.transcriptions.create.side_effect = [
        verbose_response([verbose_segment(0.0, 0.8, f"Part {idx}.")])
        for idx in range(1, 4)
    ]
    progress: list[tuple[str, float | None]] = []

    result = OpenAiApiHandler.transcribe_file(
        make_transcription(audio_file, prompt="Names", keywords=["Audiotext"]),
        on_progress=lambda message, fraction: progress.append((message, fraction)),
    )

    assert result.text == "Part 1. Part 2. Part 3."
    starts = [segment.start for segment in result.segments]
    # Each chunk is cut in a silence (800-1400 ms and 2200-2800 ms), in the
    # middle of the part of it before the limit
    assert starts == pytest.approx([0.0, 1.1, 2.4], abs=0.05)
    # Whisper has no keywords, so they're in the prompt, with the previous text
    assert request_params(openai_client, 0)["prompt"] == "Audiotext. Names"
    assert request_params(openai_client, 2)["prompt"] == (
        "Audiotext. Names Part 1. Part 2."
    )
    assert "keywords" not in request_params(openai_client, 0)
    assert progress[1:] == [
        ("Transcribing chunk 1 of 3…", 0),
        ("Transcribing chunk 2 of 3…", pytest.approx(1 / 3)),
        ("Transcribing chunk 3 of 3…", pytest.approx(2 / 3)),
    ]


def test_the_speakers_keep_their_labels_in_the_next_chunks(
    openai_client: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(openai_api_handler, "MAX_CHUNK_MS", 3000)
    audio_file = long_audio(tmp_path, tones=2, tone_ms=2500, silence_ms=500)
    openai_client.audio.transcriptions.create.side_effect = [
        diarized_response([(0.0, 2.5, "A", "Hi.")]),
        diarized_response([(0.0, 2.0, "SPEAKER_A", "Bye.")]),
    ]

    result = OpenAiApiHandler.transcribe_file(
        make_transcription(audio_file, api_model="gpt-4o-transcribe-diarize")
    )

    assert "known_speaker_names" not in request_params(openai_client, 0)
    params = request_params(openai_client, 1)
    assert params["known_speaker_names"] == ["SPEAKER_A"]
    assert params["known_speaker_references"][0].startswith("data:audio/wav;base64,")
    assert result.text == "[SPEAKER_A]: Hi. Bye."


def test_cancellation_stops_before_the_next_request(
    openai_client: MagicMock, audio_file: Path
) -> None:
    token = CancellationToken()
    token.cancel()

    with pytest.raises(TranscriptionCancelledError):
        OpenAiApiHandler.transcribe_file(
            make_transcription(audio_file), cancellation_token=token
        )

    openai_client.audio.transcriptions.create.assert_not_called()


def test_audio_too_large_for_the_api_raises(
    openai_client: MagicMock, audio_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(openai_api_handler, "MAX_REQUEST_BYTES", 10)

    with pytest.raises(ValueError, match="too large"):
        OpenAiApiHandler.transcribe_file(make_transcription(audio_file))


def test_plan_chunks_keeps_short_audios_whole() -> None:
    assert plan_chunks(make_tone(1000), max_ms=1500) == [(0, 1000)]


def test_plan_chunks_cuts_at_the_limit_without_silences() -> None:
    assert plan_chunks(make_tone(2500), max_ms=1000) == [
        (0, 1000),
        (1000, 2000),
        (2000, 2500),
    ]


def test_build_prompt_adds_the_end_of_the_previous_text() -> None:
    previous = "word " * 100

    prompt = build_prompt(" Audiotext ", previous)

    assert prompt.startswith("Audiotext word")
    assert len(prompt) <= len("Audiotext ") + 200
    assert build_prompt("", "") == ""


def test_language_code() -> None:
    assert language_code("Spanish") == "es"
    assert language_code("es") == "es"
    assert language_code("klingon") is None
    assert language_code(None) is None


def test_unknown_models_are_assumed_to_return_text() -> None:
    model = get_api_model("gpt-9-transcribe")

    assert model.api_format == "json"
    assert model.response_formats == ["text", "json"]
    assert get_api_model(None).name == "whisper-1"


def test_render_response() -> None:
    transcript = ApiTranscript(
        "Hello world.",
        [TranscriptSegment(0.0, 1.0, "Hello"), TranscriptSegment(1.0, 2.0, "world.")],
        "en",
        2.0,
    )

    assert render_response(transcript, "text") == "Hello world."
    assert json.loads(render_response(transcript, "json")) == {"text": "Hello world."}
    assert render_response(transcript, "srt").startswith(
        "1\n00:00:00,000 --> 00:00:01,000\nHello\n"
    )
    assert render_response(transcript, "vtt").startswith("WEBVTT")
    verbose = json.loads(render_response(transcript, "verbose_json"))
    assert verbose["language"] == "en"
    assert verbose["segments"][1] == {
        "id": 1,
        "start": 1.0,
        "end": 2.0,
        "text": "world.",
    }


def test_render_response_without_segments_uses_a_single_cue() -> None:
    transcript = ApiTranscript("Hello.", [], None, 3.0)

    assert render_response(transcript, "srt") == (
        "1\n00:00:00,000 --> 00:00:03,000\nHello.\n"
    )
