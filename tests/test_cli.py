import io
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import speech_recognition as sr
from pydub import AudioSegment

import cli
import utils.config_manager as cm
import utils.constants as c
import utils.update_checker as update_checker
from models.config.config_transcription import ConfigTranscription
from utils.enums import AudioSource, TranscriptionMethod


def parse(*argv: str) -> Any:
    return cli.build_parser().parse_args(list(argv))


@pytest.fixture
def audio_file(tmp_path: Path, speech_with_pauses: AudioSegment) -> Path:
    file_path = tmp_path / "speech.wav"
    speech_with_pauses.export(file_path, format="wav")
    return file_path


def run(*argv: str) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    exit_code = cli.run(list(argv), stdout=stdout, stderr=stderr)
    return exit_code, stdout.getvalue(), stderr.getvalue()


class TestBuildTranscription:
    def test_detects_the_audio_source(self, tmp_path: Path) -> None:
        cases = {
            ("transcribe", "audio.mp3"): AudioSource.FILE,
            ("transcribe", str(tmp_path)): AudioSource.DIRECTORY,
            ("transcribe", "https://youtu.be/x"): AudioSource.YOUTUBE,
            ("watch", str(tmp_path)): AudioSource.WATCH,
        }

        for argv, audio_source in cases.items():
            args = parse(*argv, "-m", "google")
            transcription = cli.build_transcription(args, None)
            assert transcription.audio_source == audio_source

    def test_youtube_url(self) -> None:
        args = parse("transcribe", "https://youtu.be/x", "-m", "google")

        assert cli.build_transcription(args, None).url == "https://youtu.be/x"

    def test_always_saves_and_uses_the_given_options(self, tmp_path: Path) -> None:
        args = parse(
            "transcribe",
            "a.mp3",
            "-m",
            "google",
            "-l",
            "es",
            "-o",
            str(tmp_path),
            "--overwrite",
        )

        transcription = cli.build_transcription(args, None)

        assert transcription.method == TranscriptionMethod.GOOGLE_API
        assert transcription.language_code == "es"
        assert transcription.should_autosave
        assert transcription.should_overwrite
        assert transcription.output_dir == tmp_path
        assert transcription.output_file_types == ["txt"]

    def test_auto_language(self) -> None:
        args = parse("transcribe", "a.mp3", "-m", "google", "-l", "auto")

        assert cli.build_transcription(args, None).language_code is None

    def test_whisperx_options_override_the_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        args = parse(
            "transcribe",
            "a.mp3",
            "-m",
            "whisperx",
            "-t",
            "srt,.vtt",
            "--diarize",
            "--speakers",
            "3",
            "--model-size",
            "tiny",
            "--translate",
        )

        config = cli.get_whisperx_config(args)
        transcription = cli.build_transcription(args, config)

        assert config.model_size == "tiny"
        assert transcription.output_file_types == ["srt", "vtt"]
        assert transcription.should_diarize
        assert transcription.num_speakers == 3
        assert transcription.should_translate

    def test_whisper_api_options(self) -> None:
        args = parse(
            "transcribe",
            "a.mp3",
            "-m",
            "whisper-api",
            "--openai-model",
            "gpt-transcribe",
            "--prompt",
            " A talk ",
            "--keywords",
            "Audiotext, WhisperX",
            "--translate",
        )

        transcription = cli.build_transcription(args, None)

        assert transcription.api_model == "gpt-transcribe"
        assert transcription.api_response_format == "text"
        assert transcription.output_file_types == ["text"]
        assert transcription.prompt == "A talk"
        assert transcription.keywords == ["Audiotext", "WhisperX"]
        assert transcription.should_translate

    def test_the_configured_prompt_and_model_are_used_by_default(self) -> None:
        cm.ConfigManager.modify_value(
            ConfigTranscription.Key.SECTION, ConfigTranscription.Key.PROMPT, "A talk"
        )
        cm.ConfigManager.modify_value(
            ConfigTranscription.Key.SECTION, ConfigTranscription.Key.KEYWORDS, "Names"
        )

        transcription = cli.build_transcription(
            parse("transcribe", "a.mp3", "-m", "whisper-api"), None
        )

        assert transcription.prompt == "A talk"
        assert transcription.keywords == ["Names"]
        assert transcription.api_model == "whisper-1"

    def test_google_ignores_the_prompt_and_the_translation(self) -> None:
        args = parse(
            "transcribe",
            "a.mp3",
            "-m",
            "google",
            "-p",
            "A talk",
            "-k",
            "Names",
            "--translate",
        )

        transcription = cli.build_transcription(args, None)

        assert transcription.prompt == ""
        assert transcription.keywords == []
        assert not transcription.should_translate

    def test_runs_on_the_cpu_without_gpu(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import torch

        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)

        config = cli.get_whisperx_config(
            parse("transcribe", "a.mp3", "--compute-type", "float16")
        )

        assert config.use_cpu
        assert config.compute_type == "int8"


@pytest.mark.parametrize(
    "argv",
    [
        ["transcribe", "a.mp3", "-l", "xx"],
        ["transcribe", "a.mp3", "-t", "txt,doc"],
        ["transcribe", "a.mp3", "--speakers", "-1"],
        ["transcribe", "a.mp3", "-m", "other"],
        ["transcribe", "a.mp3", "--openai-model", "gpt-1"],
        ["transcribe"],
    ],
)
def test_invalid_arguments(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        parse(*argv)

    assert exc_info.value.code == 2


class TestRun:
    @pytest.fixture(autouse=True)
    def google_api(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            sr.Recognizer, "recognize_google", MagicMock(return_value="hi")
        )

    def test_transcribes_saves_and_prints_the_text(
        self, audio_file: Path, tmp_path: Path
    ) -> None:
        output_dir = tmp_path / "out"

        exit_code, stdout, stderr = run(
            "transcribe", str(audio_file), "-m", "google", "-l", "en", "-o",
            str(output_dir),
        )  # fmt: skip

        assert exit_code == cli.EXIT_SUCCESS
        assert stdout == "hi. hi. hi.\n"
        assert (output_dir / "speech.txt").read_text() == "hi. hi. hi."
        assert "Done in" in stderr

    def test_quiet_only_prints_the_text(self, audio_file: Path) -> None:
        _exit_code, stdout, stderr = run(
            "transcribe", str(audio_file), "-m", "google", "-l", "en", "-q"
        )

        assert stdout == "hi. hi. hi.\n"
        assert stderr == ""

    def test_folder_prints_the_status_of_each_file(
        self, audio_file: Path, tmp_path: Path
    ) -> None:
        exit_code, stdout, stderr = run(
            "transcribe", str(tmp_path), "-m", "google", "-l", "en"
        )

        assert exit_code == cli.EXIT_SUCCESS
        assert stdout == ""
        assert "✓ speech.wav" in stderr
        assert "Transcribed 1 of 1 files." in stderr
        assert audio_file.with_suffix(".txt").exists()

    def test_errors_return_an_error_code(self, tmp_path: Path) -> None:
        exit_code, stdout, stderr = run(
            "transcribe", str(tmp_path / "missing.mp3"), "-m", "google", "-l", "en",
            "-q",
        )  # fmt: skip

        assert exit_code == cli.EXIT_ERROR
        assert stdout == ""
        assert stderr == "Error: Please select a valid audio or video file.\n"


class TestCheckUpdate:
    @pytest.fixture
    def latest_version(self, monkeypatch: pytest.MonkeyPatch) -> Any:
        """Sets the version of the latest release, instead of asking GitHub."""

        def set_version(version: str) -> None:
            monkeypatch.setattr(
                update_checker,
                "fetch_latest_release",
                lambda: update_checker.Release(version, "https://example.com/v"),
            )

        return set_version

    def test_a_new_version_is_available(self, latest_version: Any) -> None:
        latest_version("99.0.0")

        exit_code, stdout, stderr = run("check-update")

        assert exit_code == cli.EXIT_SUCCESS
        assert "Audiotext 99.0.0 is available" in stdout
        assert "https://example.com/v" in stdout
        assert stderr == ""

    def test_the_latest_version_is_installed(self, latest_version: Any) -> None:
        latest_version(c.APP_VERSION)

        exit_code, stdout, _stderr = run("check-update")

        assert exit_code == cli.EXIT_SUCCESS
        assert stdout == f"Audiotext {c.APP_VERSION} is the latest version.\n"

    def test_the_check_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fail() -> None:
            raise update_checker.UpdateCheckError("No connection")

        monkeypatch.setattr(update_checker, "fetch_latest_release", fail)

        exit_code, stdout, stderr = run("check-update")

        assert exit_code == cli.EXIT_ERROR
        assert stdout == ""
        assert "No connection" in stderr


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        parse("--version")

    assert exc_info.value.code == 0
    assert capsys.readouterr().out == f"audiotext {c.APP_VERSION}\n"
