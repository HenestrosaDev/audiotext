import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

import handlers.mlx_handler as mlx_handler
import handlers.whisperx_handler as whisperx_handler
import utils.devices as devices
from handlers.whisperx_handler import WhisperXHandler
from models.config.config_whisperx import ConfigWhisperX
from tests.test_whisperx_handler import FakeOptions, make_transcription, set_model_size
from utils.cancellation import CancellationToken, TranscriptionCancelledError
from utils.config_manager import ConfigManager

# 3000 frames: 30 seconds
FRAMES = 3000


class FakeMlxWhisper:
    """Imitates `mlx_whisper.transcribe`, which reports its progress to tqdm."""

    def __init__(self) -> None:
        self.tqdm: Any = SimpleNamespace(tqdm=MagicMock())
        self.ModelHolder = MagicMock()
        self.calls: list[dict[str, Any]] = []

    def transcribe(self, audio: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if kwargs["language"] is None:
            print("Detected language: English")
        # Like MLX Whisper, which uses the tqdm of its module
        tqdm = sys.modules["mlx_whisper.transcribe"].tqdm
        with tqdm.tqdm(total=FRAMES, unit="frames", disable=False) as bar:
            bar.update(FRAMES // 2)
            bar.update(FRAMES // 2)
        return {
            "text": " Hello world.",
            "segments": [
                {"start": 0.0, "end": 1.5, "text": " Hello", "tokens": [1]},
                # Silence that the model wrote as nothing
                {"start": 1.5, "end": 2.0, "text": " ", "tokens": []},
                {"start": 2.0, "end": 3.0, "text": " world.", "tokens": [2]},
            ],
            "language": kwargs["language"] or "en",
        }


@pytest.fixture
def mlx_whisper(monkeypatch: pytest.MonkeyPatch) -> FakeMlxWhisper:
    """Replaces MLX and MLX Whisper, which only run on Apple Silicon."""
    fake = FakeMlxWhisper()
    module = ModuleType("mlx_whisper.transcribe")
    module.__dict__.update(
        tqdm=fake.tqdm, ModelHolder=fake.ModelHolder, transcribe=fake.transcribe
    )
    # Like MLX Whisper, whose function hides the module of the same name
    package = ModuleType("mlx_whisper")
    package.__dict__["transcribe"] = fake.transcribe
    mlx_core = ModuleType("mlx.core")
    mlx_core.__dict__["float16"] = "float16"
    monkeypatch.setitem(sys.modules, "mlx_whisper", package)
    monkeypatch.setitem(sys.modules, "mlx_whisper.transcribe", module)
    monkeypatch.setitem(sys.modules, "mlx", ModuleType("mlx"))
    monkeypatch.setitem(sys.modules, "mlx.core", mlx_core)
    return fake


def transcribe(**kwargs: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "audio": np.zeros(16000, dtype=np.float32),
        "model_size": "large-v3-turbo",
        "language": None,
        "task": "transcribe",
        "prompt": "Audiotext.",
        "on_progress": lambda _message, _fraction: None,
        "message": "Transcribing…",
        "cancellation_token": CancellationToken(),
    }
    return mlx_handler.transcribe(**(values | kwargs))


def test_the_result_is_like_the_one_of_whisperx(mlx_whisper: FakeMlxWhisper) -> None:
    result = transcribe(language="es", task="translate")

    assert result == {
        "segments": [
            {"start": 0.0, "end": 1.5, "text": " Hello"},
            {"start": 2.0, "end": 3.0, "text": " world."},
        ],
        "language": "es",
    }
    call = mlx_whisper.calls[0]
    assert call["path_or_hf_repo"] == "mlx-community/whisper-large-v3-turbo"
    assert (call["language"], call["task"], call["initial_prompt"]) == (
        "es",
        "translate",
        "Audiotext.",
    )
    assert call["condition_on_previous_text"] is False
    mlx_whisper.ModelHolder.get_model.assert_called_once_with(
        "mlx-community/whisper-large-v3-turbo", "float16"
    )


def test_the_progress_is_reported_and_its_bar_restored(
    mlx_whisper: FakeMlxWhisper,
) -> None:
    original_tqdm = mlx_whisper.tqdm
    progress: list[tuple[str, float | None]] = []

    transcribe(
        on_progress=lambda message, fraction: progress.append((message, fraction))
    )

    assert progress == [
        ("Transcribing…", 0.0),
        ("Transcribing…", 0.5),
        ("Transcribing…", 1.0),
    ]
    assert sys.modules["mlx_whisper.transcribe"].tqdm is original_tqdm
    original_tqdm.tqdm.assert_not_called()


def test_cancelling_aborts_the_transcription(mlx_whisper: FakeMlxWhisper) -> None:
    token = CancellationToken()

    def cancel_halfway(_message: str, fraction: float | None) -> None:
        if fraction and fraction >= 0.5:
            token.cancel()

    with pytest.raises(TranscriptionCancelledError):
        transcribe(on_progress=cancel_halfway, cancellation_token=token)

    assert sys.modules["mlx_whisper.transcribe"].tqdm is mlx_whisper.tqdm


def test_only_the_converted_models_have_an_mlx_version() -> None:
    assert mlx_handler.has_mlx_model("large-v2")
    assert mlx_handler.has_mlx_model("distil-large-v3")
    assert not mlx_handler.has_mlx_model("distil-large-v3.5")

    with pytest.raises(ValueError):
        mlx_handler.load_model("distil-large-v3.5")


class TestIsModelDownloaded:
    @pytest.fixture
    def snapshot_download(self, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
        import huggingface_hub

        download = MagicMock()
        monkeypatch.setattr(huggingface_hub, "snapshot_download", download)
        return download

    def test_complete_download(
        self, snapshot_download: MagicMock, tmp_path: Path
    ) -> None:
        (tmp_path / "weights.npz").touch()
        snapshot_download.return_value = str(tmp_path)

        assert mlx_handler.is_model_downloaded("small")
        assert snapshot_download.call_args.kwargs == {"local_files_only": True}

    def test_interrupted_download(
        self, snapshot_download: MagicMock, tmp_path: Path
    ) -> None:
        (tmp_path / "config.json").touch()
        snapshot_download.return_value = str(tmp_path)

        assert not mlx_handler.is_model_downloaded("small")

    def test_not_in_the_cache_or_not_converted(
        self, snapshot_download: MagicMock
    ) -> None:
        from huggingface_hub.errors import LocalEntryNotFoundError

        snapshot_download.side_effect = LocalEntryNotFoundError("Not cached")

        assert not mlx_handler.is_model_downloaded("small")
        assert not mlx_handler.is_model_downloaded("distil-large-v3.5")


@pytest.fixture
def mac(monkeypatch: pytest.MonkeyPatch, mlx_whisper: FakeMlxWhisper) -> None:
    """Like a Mac with Apple Silicon, whose GPU can only be used by MLX."""
    monkeypatch.setattr(devices, "is_mlx_available", lambda: True)
    monkeypatch.setattr(devices, "is_cuda_available", lambda: False)
    ConfigManager.modify_value(
        ConfigWhisperX.Key.SECTION, ConfigWhisperX.Key.USE_CPU, "False"
    )


@pytest.fixture
def whisperx(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replaces WhisperX, whose alignment still runs after MLX."""
    fake_whisperx = MagicMock()
    fake_whisperx.load_audio.return_value = np.zeros(32000, dtype=np.float32)
    fake_whisperx.load_align_model.side_effect = lambda **_: (MagicMock(), {})
    fake_whisperx.align.side_effect = lambda segments, *_args, **_kwargs: {
        "segments": segments,
        "word_segments": [],
    }
    fake_whisperx.load_model.return_value.options = FakeOptions()
    fake_whisperx.load_model.return_value.transcribe.return_value = {
        "segments": [{"start": 0.0, "end": 1.0, "text": "On the CPU"}],
        "language": "en",
    }
    monkeypatch.setitem(sys.modules, "whisperx", fake_whisperx)
    monkeypatch.setattr(WhisperXHandler, "_release_memory", staticmethod(lambda: None))
    monkeypatch.setattr(whisperx_handler, "is_model_downloaded", lambda _size: True)
    monkeypatch.setattr(mlx_handler, "is_model_downloaded", lambda _size: True)
    return fake_whisperx


@pytest.mark.usefixtures("mac")
class TestWhisperXOnAMac:
    def test_mlx_transcribes_and_the_cpu_aligns(
        self, whisperx: MagicMock, mlx_whisper: FakeMlxWhisper
    ) -> None:
        set_model_size("large-v3-turbo")
        handler = WhisperXHandler()

        text = handler.transcribe_file(make_transcription(output_file_types=["srt"]))

        assert text == "Hello world."
        assert handler.result_language == "es"
        assert handler.audio is not None
        whisperx.load_model.assert_not_called()
        whisperx.load_align_model.assert_called_once_with(
            language_code="es", device="cpu"
        )
        assert len(mlx_whisper.calls) == 1

    def test_models_without_an_mlx_version_run_on_the_cpu(
        self, whisperx: MagicMock, mlx_whisper: FakeMlxWhisper
    ) -> None:
        set_model_size("distil-large-v3.5")

        text = WhisperXHandler().transcribe_file(make_transcription())

        assert text == "On the CPU"
        assert whisperx.load_model.call_args.args == ("distil-large-v3.5", "cpu")
        assert mlx_whisper.calls == []

    def test_the_cpu_can_be_chosen(
        self, whisperx: MagicMock, mlx_whisper: FakeMlxWhisper
    ) -> None:
        ConfigManager.modify_value(
            ConfigWhisperX.Key.SECTION, ConfigWhisperX.Key.USE_CPU, "True"
        )

        WhisperXHandler().transcribe_file(make_transcription())

        assert whisperx.load_model.call_args.args[1] == "cpu"
        assert mlx_whisper.calls == []

    def test_the_mlx_model_is_preloaded(
        self, whisperx: MagicMock, mlx_whisper: FakeMlxWhisper
    ) -> None:
        set_model_size("small")

        assert WhisperXHandler().preload_model()

        mlx_whisper.ModelHolder.get_model.assert_called_once_with(
            "mlx-community/whisper-small-mlx", "float16"
        )
        whisperx.load_model.assert_not_called()


def test_nothing_is_printed(
    mlx_whisper: FakeMlxWhisper, capsys: pytest.CaptureFixture[str]
) -> None:
    result = transcribe(language=None)

    # The command line prints the transcription to stdout
    assert capsys.readouterr().out == ""
    assert result["language"] == "en"
