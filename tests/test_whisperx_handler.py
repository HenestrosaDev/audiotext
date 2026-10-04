import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

import handlers.whisperx_handler as whisperx_handler
from handlers.whisperx_handler import WhisperXHandler, is_model_downloaded
from models.config.config_whisperx import ConfigWhisperX
from models.transcription import Transcription
from utils.cancellation import CancellationToken, TranscriptionCancelledError
from utils.config_manager import ConfigManager

SEGMENTS = [
    {"start": 0.0, "end": 1.0, "text": " Hello "},
    {"start": 1.0, "end": 2.0, "text": "world. "},
]


@dataclass(frozen=True)
class FakeOptions:
    """Imitates the transcription options of a WhisperX model."""

    initial_prompt: str | None = None
    beam_size: int = 5


def fake_transcribe(_audio: Any, **kwargs: Any) -> dict[str, Any]:
    """Imitates WhisperX, which reports the progress after each batch."""
    for percentage in (50, 100):
        kwargs["progress_callback"](percentage)

    return {"segments": SEGMENTS, "language": kwargs["language"] or "en"}


@pytest.fixture
def whisperx(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replaces the WhisperX library, which needs to download models."""
    fake_whisperx = MagicMock()
    fake_whisperx.load_audio.return_value = np.zeros(32000, dtype=np.float32)
    fake_whisperx.load_model.return_value.transcribe.side_effect = fake_transcribe
    fake_whisperx.load_model.return_value.options = FakeOptions()
    fake_whisperx.load_align_model.side_effect = lambda **_: (MagicMock(), {})
    fake_whisperx.align.return_value = {"segments": SEGMENTS, "word_segments": []}

    monkeypatch.setitem(sys.modules, "whisperx", fake_whisperx)
    monkeypatch.setitem(sys.modules, "whisperx.utils", fake_whisperx.utils)
    monkeypatch.setattr(WhisperXHandler, "_release_memory", staticmethod(lambda: None))
    monkeypatch.setattr(whisperx_handler, "is_model_downloaded", lambda _size: True)
    return fake_whisperx


def make_transcription(**kwargs: Any) -> Transcription:
    defaults: dict[str, Any] = {
        "audio_source_path": Path("audio.mp3"),
        "language_code": "es",
        "output_file_types": ["txt"],
    }
    return Transcription(**(defaults | kwargs))


def set_model_size(model_size: str) -> None:
    ConfigManager.modify_value(
        ConfigWhisperX.Key.SECTION, ConfigWhisperX.Key.MODEL_SIZE, model_size
    )


def test_transcribe_file_joins_the_segments(whisperx: MagicMock) -> None:
    text = WhisperXHandler().transcribe_file(make_transcription())

    assert text == "Hello world."
    assert whisperx.load_model.call_args.args == ("large-v2", "cuda")
    assert whisperx.load_model.call_args.kwargs["compute_type"] == "float16"
    whisperx.align.assert_not_called()


def test_language_and_task_are_passed_on_each_transcription(
    whisperx: MagicMock,
) -> None:
    WhisperXHandler().transcribe_file(make_transcription(should_translate=True))

    transcribe_kwargs = whisperx.load_model.return_value.transcribe.call_args.kwargs
    assert transcribe_kwargs["language"] == "es"
    assert transcribe_kwargs["task"] == "translate"


def test_the_prompt_is_set_on_each_transcription(whisperx: MagicMock) -> None:
    handler = WhisperXHandler()
    model = whisperx.load_model.return_value

    handler.transcribe_file(
        make_transcription(prompt=" A talk ", keywords=["Audiotext", "WhisperX"])
    )
    assert model.options == FakeOptions(initial_prompt="Audiotext, WhisperX. A talk")

    handler.transcribe_file(make_transcription())
    # The other options are kept, and the model isn't loaded again
    assert model.options == FakeOptions(initial_prompt=None)
    assert whisperx.load_model.call_count == 1


def test_model_is_reused_when_language_or_task_change(whisperx: MagicMock) -> None:
    handler = WhisperXHandler()

    handler.transcribe_file(make_transcription())
    handler.transcribe_file(make_transcription(language_code="en"))
    handler.transcribe_file(make_transcription(should_translate=True))

    assert whisperx.load_model.call_count == 1


def test_model_is_reloaded_when_model_size_changes(whisperx: MagicMock) -> None:
    handler = WhisperXHandler()

    handler.transcribe_file(make_transcription())
    set_model_size("tiny")
    handler.transcribe_file(make_transcription())

    assert [call.args[0] for call in whisperx.load_model.call_args_list] == [
        "large-v2",
        "tiny",
    ]


def test_preload_model_loads_the_configured_model(whisperx: MagicMock) -> None:
    handler = WhisperXHandler()
    messages: list[str] = []

    handler.preload_model(lambda message, _fraction: messages.append(message))
    handler.transcribe_file(make_transcription())

    whisperx.load_model.assert_called_once()
    assert "Loading the large-v2 model" in messages[0]


def test_preload_model_does_not_download_the_model(
    whisperx: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(whisperx_handler, "is_model_downloaded", lambda _size: False)
    handler = WhisperXHandler()

    assert handler.preload_model() is False
    whisperx.load_model.assert_not_called()

    # The transcription downloads the model when it needs it
    handler.transcribe_file(make_transcription())
    whisperx.load_model.assert_called_once()


class TestIsModelDownloaded:
    @pytest.fixture
    def download_model(self, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
        import faster_whisper.utils

        fake_download_model = MagicMock()
        monkeypatch.setattr(faster_whisper.utils, "download_model", fake_download_model)
        return fake_download_model

    def test_complete_download(self, download_model: MagicMock, tmp_path: Path) -> None:
        (tmp_path / "model.bin").touch()
        download_model.return_value = str(tmp_path)

        assert is_model_downloaded("tiny")
        assert download_model.call_args.kwargs["local_files_only"] is True

    def test_interrupted_download(
        self, download_model: MagicMock, tmp_path: Path
    ) -> None:
        (tmp_path / "config.json").touch()
        download_model.return_value = str(tmp_path)

        assert not is_model_downloaded("tiny")

    def test_model_not_in_the_cache(self, download_model: MagicMock) -> None:
        from huggingface_hub.errors import LocalEntryNotFoundError

        download_model.side_effect = LocalEntryNotFoundError("Not cached")

        assert not is_model_downloaded("tiny")


def test_subtitles_are_aligned_with_a_cached_align_model(whisperx: MagicMock) -> None:
    handler = WhisperXHandler()
    srt_transcription = make_transcription(output_file_types=["srt"])

    handler.transcribe_file(srt_transcription)
    handler.transcribe_file(srt_transcription)

    whisperx.load_align_model.assert_called_once_with(language_code="es", device="cuda")
    assert whisperx.align.call_count == 2


def test_translated_subtitles_are_aligned_in_english(whisperx: MagicMock) -> None:
    WhisperXHandler().transcribe_file(
        make_transcription(output_file_types=["vtt"], should_translate=True)
    )

    assert whisperx.load_align_model.call_args.kwargs["language_code"] == "en"


def test_progress_is_reported(whisperx: MagicMock) -> None:
    updates: list[tuple[str, float | None]] = []

    WhisperXHandler().transcribe_file(
        make_transcription(),
        lambda message, fraction: updates.append((message, fraction)),
    )

    assert ("Transcribing…", 0.5) in updates
    assert ("Transcribing…", 1.0) in updates


def test_cancellation_aborts_the_transcription(whisperx: MagicMock) -> None:
    token = CancellationToken()

    def cancel_halfway(_message: str, fraction: float | None) -> None:
        if fraction == 0.5:
            token.cancel()

    with pytest.raises(TranscriptionCancelledError):
        WhisperXHandler().transcribe_file(make_transcription(), cancel_halfway, token)


def test_transcribe_without_output_file_types_raises(whisperx: MagicMock) -> None:
    with pytest.raises(ValueError, match="No output file types"):
        WhisperXHandler().transcribe_file(make_transcription(output_file_types=[]))


def test_save_transcription_writes_each_file_type(
    whisperx: MagicMock, tmp_path: Path
) -> None:
    handler = WhisperXHandler()
    handler.transcribe_file(make_transcription(should_translate=True))

    handler.save_transcription(tmp_path / "audio.txt", ["txt", "srt"], False)

    writer_formats = [call.args[0] for call in whisperx.utils.get_writer.call_args_list]
    assert writer_formats == ["txt", "srt"]
    writer = whisperx.utils.get_writer.return_value
    result, audio_path, options = writer.call_args.args
    assert result["language"] == "en"  # Translations are always in English
    assert audio_path == str(tmp_path / "audio.txt")
    assert options == {
        "highlight_words": False,
        "max_line_count": 2,
        "max_line_width": 42,
    }


def test_save_transcription_does_not_overwrite_existing_files(
    whisperx: MagicMock, tmp_path: Path
) -> None:
    (tmp_path / "audio.txt").write_text("previous transcription")
    handler = WhisperXHandler()
    handler.transcribe_file(make_transcription())

    handler.save_transcription(tmp_path / "audio.mp3", ["txt", "json"], False)

    writer_formats = [call.args[0] for call in whisperx.utils.get_writer.call_args_list]
    assert writer_formats == ["json"]


def test_save_without_transcription_raises(whisperx: MagicMock, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no transcription to save"):
        WhisperXHandler().save_transcription(tmp_path / "audio.txt", ["txt"], True)


def test_keeps_the_segments_and_the_audio_of_the_last_transcription(
    whisperx: MagicMock,
) -> None:
    handler = WhisperXHandler()
    assert handler.segments == [] and handler.audio is None

    handler.transcribe_file(make_transcription())

    assert [(s.start, s.end, s.text) for s in handler.segments] == [
        (0.0, 1.0, "Hello"),
        (1.0, 2.0, "world."),
    ]
    assert handler.audio is not None
    assert handler.audio.dtype == np.int16
    assert len(handler.audio) == 32000


def test_uses_the_config_of_the_provider(whisperx: MagicMock) -> None:
    config = ConfigManager.get_config_whisperx()
    config.model_size = "tiny"

    WhisperXHandler(config_provider=lambda: config).transcribe_file(
        make_transcription()
    )

    assert whisperx.load_model.call_args.args[0] == "tiny"


class TestDiarization:
    @pytest.fixture
    def diarize(
        self, whisperx: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> MagicMock:
        fake_diarize = MagicMock()
        monkeypatch.setitem(sys.modules, "whisperx.diarize", fake_diarize)
        monkeypatch.setenv("HF_TOKEN", "hf_token")

        def assign_word_speakers(_diarize_segments: Any, result: Any) -> Any:
            speakers = ["SPEAKER_00", "SPEAKER_01"]
            return {
                **result,
                "segments": [
                    {**segment, "speaker": speaker}
                    for segment, speaker in zip(
                        result["segments"], speakers, strict=True
                    )
                ],
            }

        whisperx.assign_word_speakers.side_effect = assign_word_speakers
        return fake_diarize

    def test_labels_the_speakers(self, whisperx: MagicMock, diarize: MagicMock) -> None:
        handler = WhisperXHandler()

        text = handler.transcribe_file(
            make_transcription(should_diarize=True, num_speakers=2)
        )

        assert text == "[SPEAKER_00]: Hello\n\n[SPEAKER_01]: world."
        assert [segment.speaker for segment in handler.segments] == [
            "SPEAKER_00",
            "SPEAKER_01",
        ]
        pipeline = diarize.DiarizationPipeline
        assert pipeline.call_args.kwargs["token"] == "hf_token"
        assert pipeline.return_value.call_args.kwargs["num_speakers"] == 2
        # Word timestamps make the assignment of the speakers more precise
        whisperx.align.assert_called_once()

    def test_the_model_is_reused(self, diarize: MagicMock) -> None:
        handler = WhisperXHandler()

        handler.transcribe_file(make_transcription(should_diarize=True))
        handler.transcribe_file(make_transcription(should_diarize=True))

        diarize.DiarizationPipeline.assert_called_once()

    def test_works_without_an_alignment_model(
        self, whisperx: MagicMock, diarize: MagicMock
    ) -> None:
        whisperx.load_align_model.side_effect = ValueError("No default align-model")

        text = WhisperXHandler().transcribe_file(
            make_transcription(should_diarize=True)
        )

        assert text.startswith("[SPEAKER_00]")

    def test_requires_a_hugging_face_token(
        self,
        whisperx: MagicMock,
        diarize: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("HF_TOKEN")

        with pytest.raises(ValueError, match="Hugging Face token"):
            WhisperXHandler().transcribe_file(make_transcription(should_diarize=True))

        # It fails before loading anything
        whisperx.load_model.assert_not_called()

    def test_invalid_token_shows_how_to_get_access(self, diarize: MagicMock) -> None:
        from huggingface_hub.errors import GatedRepoError

        diarize.DiarizationPipeline.side_effect = GatedRepoError("403")

        with pytest.raises(ValueError, match="accepted the conditions"):
            WhisperXHandler().transcribe_file(make_transcription(should_diarize=True))
