from pathlib import Path

import pytest
import speech_recognition as sr
from pydub import AudioSegment

from handlers.audio_handler import AudioHandler, TranscriptionFunc
from models.transcription import Transcription
from tests.conftest import make_tone
from utils.cancellation import CancellationToken, TranscriptionCancelledError


def numbered_transcription_func() -> tuple[list[sr.AudioData], TranscriptionFunc]:
    received_chunks: list[sr.AudioData] = []

    def transcribe(audio_data: sr.AudioData, _transcription: Transcription) -> str:
        received_chunks.append(audio_data)
        return f"chunk{len(received_chunks)} "

    return received_chunks, transcribe


def test_split_audio_into_chunks_splits_on_silence(
    speech_with_pauses: AudioSegment,
) -> None:
    chunks = AudioHandler.split_audio_into_chunks(speech_with_pauses)

    assert len(chunks) == 3


def test_all_chunks_are_transcribed_and_joined() -> None:
    received_chunks, transcribe = numbered_transcription_func()
    chunks = [make_tone(), make_tone(), make_tone()]

    text = AudioHandler.process_audio_chunks(chunks, Transcription(), transcribe)

    assert len(received_chunks) == 3
    assert text == "chunk1 chunk2 chunk3"


def test_chunks_without_recognizable_speech_are_skipped() -> None:
    calls = 0

    def transcribe(_audio_data: sr.AudioData, _transcription: Transcription) -> str:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise sr.UnknownValueError()
        return f"chunk{calls} "

    chunks = [make_tone(), make_tone(), make_tone()]

    text = AudioHandler.process_audio_chunks(chunks, Transcription(), transcribe)

    assert text == "chunk1 chunk3"


def test_other_transcription_errors_are_propagated() -> None:
    def transcribe(_audio_data: sr.AudioData, _transcription: Transcription) -> str:
        raise sr.RequestError("API unavailable")

    with pytest.raises(sr.RequestError):
        AudioHandler.process_audio_chunks([make_tone()], Transcription(), transcribe)


def test_get_transcription_reads_the_file_and_splits_it(
    tmp_path: Path, speech_with_pauses: AudioSegment
) -> None:
    file_path = tmp_path / "speech.WAV"  # Upper case extensions are supported
    speech_with_pauses.export(file_path, format="wav")
    received_chunks, transcribe = numbered_transcription_func()

    text = AudioHandler.get_transcription(
        transcription=Transcription(audio_source_path=file_path),
        should_split_on_silence=True,
        transcription_func=transcribe,
    )

    assert text == "chunk1 chunk2 chunk3"


def test_get_transcription_without_splitting_sends_the_whole_audio(
    tmp_path: Path, speech_with_pauses: AudioSegment
) -> None:
    file_path = tmp_path / "speech.wav"
    speech_with_pauses.export(file_path, format="wav")
    received_chunks, transcribe = numbered_transcription_func()

    AudioHandler.get_transcription(
        transcription=Transcription(audio_source_path=file_path),
        should_split_on_silence=False,
        transcription_func=transcribe,
    )

    assert len(received_chunks) == 1


def test_unsupported_file_type_raises(tmp_path: Path) -> None:
    file_path = tmp_path / "notes.txt"
    file_path.write_text("not audio")

    with pytest.raises(ValueError, match="Unsupported file type"):
        AudioHandler.load_audio_file(file_path)


def test_progress_is_reported_for_each_chunk() -> None:
    _, transcribe = numbered_transcription_func()
    updates: list[tuple[str, float | None]] = []

    AudioHandler.process_audio_chunks(
        [make_tone(), make_tone()],
        Transcription(),
        transcribe,
        on_progress=lambda message, fraction: updates.append((message, fraction)),
    )

    assert updates == [
        ("Transcribing chunk 1 of 2…", 0.0),
        ("Transcribing chunk 2 of 2…", 0.5),
    ]


def test_cancellation_stops_before_the_next_chunk() -> None:
    received_chunks, transcribe = numbered_transcription_func()
    token = CancellationToken()

    def cancel_after_first_chunk(
        audio_data: sr.AudioData, transcription: Transcription
    ) -> str:
        token.cancel()
        return transcribe(audio_data, transcription)

    with pytest.raises(TranscriptionCancelledError):
        AudioHandler.process_audio_chunks(
            [make_tone(), make_tone()],
            Transcription(),
            cancel_after_first_chunk,
            cancellation_token=token,
        )

    assert len(received_chunks) == 1
