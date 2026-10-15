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
import utils.devices as devices
import utils.update_checker as update_checker
from handlers.ai_providers import AiProvider
from models.config.config_transcription import ConfigTranscription
from models.summary import TranscriptSummary
from models.transcript_segment import TranscriptSegment
from models.translation import TranscriptTranslation
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

    def test_whisperx_saves_its_types_and_exports_the_others(self) -> None:
        args = parse("transcribe", "a.mp3", "-m", "whisperx", "-t", "srt,md,docx")

        transcription = cli.build_transcription(args, cli.get_whisperx_config(args))

        assert transcription.output_file_types == ["srt"]
        assert transcription.should_autosave
        assert cli.get_exported_types(transcription, args.output_types) == [
            "md",
            "docx",
        ]

    @pytest.mark.parametrize(
        ("method", "output_types"), [("whisperx", "md"), ("google", "txt,md")]
    )
    def test_the_types_that_the_method_does_not_save_are_exported(
        self, method: str, output_types: str
    ) -> None:
        args = parse("transcribe", "a.mp3", "-m", method, "-t", output_types)
        config = cli.get_whisperx_config(args) if method == "whisperx" else None

        transcription = cli.build_transcription(args, config)

        # Which also skips the files of a folder that have them
        assert transcription.output_file_types == output_types.split(",")
        assert not transcription.should_autosave
        assert cli.get_exported_types(transcription, args.output_types) == (
            output_types.split(",")
        )

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
        monkeypatch.setattr(devices, "is_cuda_available", lambda: False)

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
        ["transcribe", "a.mp3", "--translate-to", "auto"],
        ["transcribe", "a.mp3", "--summary-provider", "other"],
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

    def test_exports_the_types_that_the_method_does_not_save(
        self, audio_file: Path, tmp_path: Path
    ) -> None:
        output_dir = tmp_path / "out"

        exit_code, _stdout, stderr = run(
            "transcribe", str(audio_file), "-m", "google", "-l", "en", "-o",
            str(output_dir), "-t", "txt,md,docx",
        )  # fmt: skip

        assert exit_code == cli.EXIT_SUCCESS
        assert (output_dir / "speech.txt").read_text() == "hi. hi. hi.\n"
        assert "hi. hi. hi." in (output_dir / "speech.md").read_text()
        assert (output_dir / "speech.docx").exists()
        assert f"Saved {output_dir / 'speech.md'}." in stderr

    def test_summarizes_and_translates(
        self, audio_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple[Any, ...]] = []

        class FakeSummaryHandler:
            def summarize(self, text: str, *args: Any) -> TranscriptSummary:
                calls.append(("summarize", text, *args))
                return TranscriptSummary("A short talk.", ("They say hi",))

        class FakeTranslationHandler:
            def translate(self, text: str, *_args: Any, **kwargs: Any) -> Any:
                calls.append(("translate", text, kwargs["language"]))
                return TranscriptTranslation(language="es", text="hola. hola.")

        monkeypatch.setattr(cli, "SummaryHandler", FakeSummaryHandler)
        monkeypatch.setattr(cli, "TranslationHandler", FakeTranslationHandler)
        monkeypatch.setattr(cli, "has_api_key", lambda _provider: True)
        monkeypatch.setattr(
            cli.translation_handler, "has_api_key", lambda _provider: True
        )

        exit_code, _stdout, stderr = run(
            "transcribe", str(audio_file), "-m", "google", "-l", "en",
            "--summarize", "--summary-provider", "anthropic", "--summary-model",
            "claude-x", "--translate-to", "es",
        )  # fmt: skip

        assert exit_code == cli.EXIT_SUCCESS, stderr
        summary = audio_file.with_name("speech.summary.md").read_text()
        assert "A short talk." in summary and "They say hi" in summary
        # Saved like the transcription (txt for Google)
        assert audio_file.with_name("speech.es.txt").read_text() == "hola. hola.\n"
        assert calls == [
            ("summarize", "hi. hi. hi.", [], AiProvider.ANTHROPIC, "claude-x"),
            ("translate", "hi. hi. hi.", "es"),
        ]

    def test_a_missing_key_stops_before_transcribing(
        self, audio_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(cli, "has_api_key", lambda _provider: False)
        recognize = MagicMock(return_value="hi")
        monkeypatch.setattr(sr.Recognizer, "recognize_google", recognize)

        exit_code, stdout, stderr = run(
            "transcribe", str(audio_file), "-m", "google", "-l", "en", "--summarize"
        )

        assert exit_code == cli.EXIT_ERROR
        assert stdout == ""
        assert "can't summarize" in stderr
        recognize.assert_not_called()

    def test_the_errors_of_the_follow_ups_are_reported(
        self, audio_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class FailingSummaryHandler:
            def summarize(self, *_args: Any) -> TranscriptSummary:
                raise ValueError("The model didn't return a valid summary.")

        monkeypatch.setattr(cli, "SummaryHandler", FailingSummaryHandler)
        monkeypatch.setattr(cli, "has_api_key", lambda _provider: True)

        exit_code, stdout, stderr = run(
            "transcribe", str(audio_file), "-m", "google", "-l", "en", "--summarize"
        )

        # The transcription is still saved and printed
        assert exit_code == cli.EXIT_ERROR
        assert stdout == "hi. hi. hi.\n"
        assert audio_file.with_suffix(".txt").exists()
        assert (
            "Error: Could not summarize speech.wav: The model didn't return a valid "
            "summary." in stderr
        )


class TestFollowUps:
    def test_existing_files_are_kept_unless_overwritten(self, tmp_path: Path) -> None:
        file_path = tmp_path / "talk.mp3"
        segments = [TranscriptSegment(0, 1, "Hi.")]
        (tmp_path / "talk.md").write_text("old")

        saved, errors = cli.FollowUps(output_types=["md", "srt"]).run(
            file_path, "Hi.", segments
        )

        assert saved == [tmp_path / "talk.srt"]
        assert errors == []
        assert (tmp_path / "talk.md").read_text() == "old"

        cli.FollowUps(output_types=["md"], should_overwrite=True).run(
            file_path, "Hi.", segments
        )
        assert "Hi." in (tmp_path / "talk.md").read_text()

    def test_the_subfolders_are_recreated_in_the_output_folder(
        self, tmp_path: Path
    ) -> None:
        source_dir, output_dir = tmp_path / "in", tmp_path / "out"
        follow_ups = cli.FollowUps(
            output_types=["txt"], output_dir=output_dir, source_dir=source_dir
        )

        follow_ups.run(source_dir / "day 1" / "talk.v2.mp3", "Hi.", [])

        # The dots of its name are kept
        assert (output_dir / "day 1" / "talk.v2.txt").read_text() == "Hi.\n"

    def test_timed_formats_need_the_timestamps(self, tmp_path: Path) -> None:
        saved, errors = cli.FollowUps(output_types=["srt"]).run(
            tmp_path / "talk.mp3", "Hi.", []
        )

        assert saved == []
        assert errors == [
            "Could not save talk.srt: The .srt format needs the timestamps"
        ]


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


def test_the_gpu_of_a_mac_transcribes_with_float_types_for_the_cpu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(devices, "is_cuda_available", lambda: False)
    monkeypatch.setattr(devices, "is_mlx_available", lambda: True)

    config = cli.get_whisperx_config(
        parse("transcribe", "a.mp3", "--compute-type", "float16")
    )

    # MLX transcribes on the GPU, and faster-whisper (e.g. alignment) on the CPU
    assert not config.use_cpu
    assert config.compute_type == "int8"
