from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import speech_recognition as sr
from pydub import AudioSegment

import controllers.folder_transcriber as folder_transcriber
import controllers.main_controller as main_controller
import controllers.mic_recorder as mic_recorder
import utils.audio_utils as au
from controllers.directory_report import DirectoryReport, FileStatus
from controllers.main_controller import MainController
from controllers.transcription_saver import TranscriptionSaver, get_output_dir
from handlers.openai_api_handler import ApiTranscript, OpenAiApiHandler
from handlers.transcribers import (
    GoogleApiTranscriber,
    OpenAiApiTranscriber,
    WhisperXTranscriber,
)
from models.config.config_transcription import ConfigTranscription
from models.transcript_segment import TranscriptSegment
from models.transcription import Transcription, TranscriptionResult
from tests.conftest import FakeView, make_tone
from utils.cancellation import CancellationToken
from utils.config_manager import ConfigManager
from utils.enums import AudioSource, TranscriptionMethod


@pytest.fixture
def whisperx_handler() -> MagicMock:
    handler = MagicMock()
    handler.transcribe_file.return_value = "whisperx text"
    return handler


@pytest.fixture
def controller(
    fake_view: FakeView, whisperx_handler: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> MainController:
    # Run the background tasks synchronously to make the tests deterministic
    monkeypatch.setattr(
        MainController, "_start_background_task", staticmethod(lambda task: task())
    )
    return MainController(fake_view, whisperx_handler)


@pytest.fixture
def audio_file(tmp_path: Path, speech_with_pauses: AudioSegment) -> Path:
    file_path = tmp_path / "speech.wav"
    speech_with_pauses.export(file_path, format="wav")
    return file_path


def make_transcription(**kwargs: Any) -> Transcription:
    defaults: dict[str, Any] = {
        "audio_source": AudioSource.FILE,
        "language_code": "en",
        "method": TranscriptionMethod.WHISPERX,
        "output_file_types": ["txt"],
    }
    return Transcription(**(defaults | kwargs))


def create_files(directory: Path, *names: str) -> None:
    for name in names:
        (directory / name).parent.mkdir(parents=True, exist_ok=True)
        (directory / name).touch()


def get_files_to_transcribe(
    dir_path: Path, output_file_types: list[str], should_overwrite: bool
) -> list[Path]:
    saver = TranscriptionSaver(
        make_transcription(
            audio_source=AudioSource.DIRECTORY,
            audio_source_path=dir_path,
            output_file_types=output_file_types,
            should_overwrite=should_overwrite,
        )
    )
    return saver.get_files_to_transcribe(dir_path)


class TestGetFilesToTranscribe:
    def test_finds_supported_files_recursively(self, tmp_path: Path) -> None:
        create_files(tmp_path, "a.mp3", "b.MP4", "sub/c.wav", "notes.txt")

        files = get_files_to_transcribe(tmp_path, ["srt"], should_overwrite=False)

        assert files == [tmp_path / "a.mp3", tmp_path / "b.MP4", tmp_path / "sub/c.wav"]

    def test_skips_files_already_transcribed(self, tmp_path: Path) -> None:
        create_files(tmp_path, "a.mp3", "a.srt", "b.mp3")

        files = get_files_to_transcribe(tmp_path, ["srt"], should_overwrite=False)

        assert files == [tmp_path / "b.mp3"]

    def test_includes_files_already_transcribed_when_overwriting(
        self, tmp_path: Path
    ) -> None:
        create_files(tmp_path, "a.mp3", "a.srt")

        files = get_files_to_transcribe(tmp_path, ["srt"], should_overwrite=True)

        assert files == [tmp_path / "a.mp3"]

    def test_maps_api_response_formats_to_file_extensions(self, tmp_path: Path) -> None:
        create_files(tmp_path, "a.mp3", "a.txt")

        files = get_files_to_transcribe(tmp_path, ["text"], should_overwrite=False)

        assert files == []


class TestValidation:
    @pytest.mark.parametrize(
        ("transcription_kwargs", "expected_error"),
        [
            ({"output_file_types": []}, "No output file types selected"),
            ({"audio_source_path": Path("missing.mp3")}, "valid audio or video file"),
            (
                {"audio_source": AudioSource.DIRECTORY, "audio_source_path": Path("x")},
                "valid folder",
            ),
            ({"audio_source": AudioSource.YOUTUBE}, "valid URL"),
            (
                {"audio_source": AudioSource.YOUTUBE, "url": "not a url"},
                "valid URL",
            ),
            (
                {"method": TranscriptionMethod.GOOGLE_API, "language_code": None},
                "can't detect the language",
            ),
        ],
    )
    def test_invalid_settings_show_an_error(
        self,
        controller: MainController,
        fake_view: FakeView,
        whisperx_handler: MagicMock,
        transcription_kwargs: dict[str, Any],
        expected_error: str,
    ) -> None:
        controller.prepare_for_transcription(make_transcription(**transcription_kwargs))

        assert expected_error in fake_view.errors[-1]
        assert fake_view.processed_statuses == [None]
        whisperx_handler.transcribe_file.assert_not_called()

    def test_whisperx_can_detect_the_language(
        self,
        controller: MainController,
        fake_view: FakeView,
        whisperx_handler: MagicMock,
        audio_file: Path,
    ) -> None:
        controller.prepare_for_transcription(
            make_transcription(language_code=None, audio_source_path=audio_file)
        )

        assert fake_view.errors == []
        assert whisperx_handler.transcribe_file.call_args.args[0].language_code is None


class TestFileTranscription:
    def test_transcribes_file_with_google_api(
        self,
        controller: MainController,
        fake_view: FakeView,
        audio_file: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            sr.Recognizer, "recognize_google", MagicMock(return_value="hi")
        )
        transcription = make_transcription(
            method=TranscriptionMethod.GOOGLE_API,
            audio_source_path=audio_file,
            should_autosave=True,
        )

        controller.prepare_for_transcription(transcription)

        assert fake_view.displayed_texts == ["hi. hi. hi."]
        assert fake_view.processed_statuses[0].startswith("Done in")  # type: ignore[union-attr]
        assert audio_file.with_suffix(".txt").read_text() == "hi. hi. hi."
        assert fake_view.saved_folders == [audio_file.parent.resolve()]
        assert ("Transcribing chunk 2 of 3…", pytest.approx(1 / 3)) in (
            fake_view.progress_updates
        )

    def test_youtube_audio_is_downloaded_and_removed_after_transcribing(
        self,
        controller: MainController,
        fake_view: FakeView,
        whisperx_handler: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        downloaded_file = tmp_path / "yt-audio.mp3"
        downloaded_file.touch()
        download = MagicMock(return_value=downloaded_file)
        monkeypatch.setattr(main_controller.UrlHandler, "download", download)
        transcription = make_transcription(
            audio_source=AudioSource.YOUTUBE, url="https://youtu.be/id"
        )

        controller.prepare_for_transcription(transcription)

        assert download.call_args.args[:2] == (
            "https://youtu.be/id",
            main_controller.URL_DOWNLOAD_PATH,
        )
        assert fake_view.displayed_texts == ["whisperx text"]
        assert not downloaded_file.exists()

    def test_url_media_is_kept_when_the_history_needs_it(
        self,
        controller: MainController,
        fake_view: FakeView,
        whisperx_handler: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        media_path = tmp_path / "media" / "entry" / "video"
        downloaded_file = media_path.with_suffix(".mp4")
        downloaded_file.parent.mkdir(parents=True)
        downloaded_file.touch()
        download = MagicMock(return_value=downloaded_file)
        monkeypatch.setattr(main_controller.UrlHandler, "download", download)
        segments = [TranscriptSegment(0, 1, "whisperx text")]
        whisperx_handler.segments = segments
        whisperx_handler.result_language = "en"

        controller.prepare_for_transcription(
            make_transcription(
                audio_source=AudioSource.YOUTUBE,
                url="https://example.com/video.mp4",
                media_path=media_path,
            )
        )

        assert download.call_args.args[1] == media_path
        assert downloaded_file.exists()
        assert fake_view.downloaded_media == [downloaded_file]
        assert fake_view.transcribed_files == [
            (downloaded_file, "whisperx text", segments, "en")
        ]

    def test_errors_are_shown_without_replacing_the_text(
        self,
        controller: MainController,
        fake_view: FakeView,
        whisperx_handler: MagicMock,
        audio_file: Path,
    ) -> None:
        whisperx_handler.transcribe_file.side_effect = RuntimeError("CUDA error")

        controller.prepare_for_transcription(
            make_transcription(audio_source_path=audio_file)
        )

        assert fake_view.errors == ["RuntimeError: CUDA error"]
        assert fake_view.displayed_texts == []
        assert fake_view.processed_statuses == [None]


class TestDirectoryTranscription:
    def transcribe_directory(
        self, controller: MainController, directory: Path, **kwargs: Any
    ) -> None:
        controller.prepare_for_transcription(
            make_transcription(
                audio_source=AudioSource.DIRECTORY,
                audio_source_path=directory,
                should_autosave=True,
                **kwargs,
            )
        )

    def test_transcribes_and_saves_every_file(
        self,
        controller: MainController,
        fake_view: FakeView,
        whisperx_handler: MagicMock,
        tmp_path: Path,
    ) -> None:
        create_files(tmp_path, "a.mp3", "b.mp3")

        self.transcribe_directory(controller, tmp_path)

        saved_paths = [
            call.kwargs["file_path"]
            for call in whisperx_handler.save_transcription.call_args_list
        ]
        assert saved_paths == [tmp_path / "a.txt", tmp_path / "b.txt"]
        assert fake_view.displayed_texts[-1] == (
            "Transcribed 2 of 2 files.\n\n✓ a.mp3\n✓ b.mp3"
        )
        assert fake_view.processed_statuses == ["Transcribed 2 of 2 files."]
        assert fake_view.saved_folders == [tmp_path]

    def test_shows_the_status_of_each_file_while_transcribing(
        self,
        controller: MainController,
        fake_view: FakeView,
        whisperx_handler: MagicMock,
        tmp_path: Path,
    ) -> None:
        create_files(tmp_path, "a.mp3", "b.mp3")

        self.transcribe_directory(controller, tmp_path)

        assert fake_view.displayed_texts[:2] == [
            "▶ a.mp3\n• b.mp3",
            "✓ a.mp3\n▶ b.mp3",
        ]

    def test_progress_combines_files_and_steps(
        self,
        controller: MainController,
        fake_view: FakeView,
        whisperx_handler: MagicMock,
        tmp_path: Path,
    ) -> None:
        create_files(tmp_path, "a.mp3", "b.mp3")

        def transcribe_file(_transcription: Any, on_progress: Any, _token: Any) -> str:
            on_progress("Transcribing…", 0.5)
            return "text"

        whisperx_handler.transcribe_file.side_effect = transcribe_file

        self.transcribe_directory(controller, tmp_path)

        assert fake_view.progress_updates == [
            ("File 1 of 2 (a.mp3): Transcribing…", 0.25),
            ("File 2 of 2 (b.mp3): Transcribing…", 0.75),
        ]

    def test_failed_files_do_not_stop_the_transcription(
        self,
        controller: MainController,
        fake_view: FakeView,
        whisperx_handler: MagicMock,
        tmp_path: Path,
    ) -> None:
        create_files(tmp_path, "a.mp3", "b.mp3", "c.mp3")
        whisperx_handler.transcribe_file.side_effect = [
            "text",
            RuntimeError("corrupt file"),
            "text",
        ]

        self.transcribe_directory(controller, tmp_path)

        assert whisperx_handler.transcribe_file.call_count == 3
        assert fake_view.displayed_texts[-1] == (
            "Transcribed 2 of 3 files.\n\n"
            "✓ a.mp3\n✗ b.mp3 — RuntimeError: corrupt file\n✓ c.mp3"
        )

    def test_empty_directory_shows_error(
        self,
        controller: MainController,
        fake_view: FakeView,
        whisperx_handler: MagicMock,
        tmp_path: Path,
    ) -> None:
        self.transcribe_directory(controller, tmp_path)

        assert "doesn't contain files to transcribe" in fake_view.errors[-1]
        whisperx_handler.transcribe_file.assert_not_called()


class TestCancellation:
    def test_cancelling_stops_the_transcription_without_saving(
        self,
        controller: MainController,
        fake_view: FakeView,
        whisperx_handler: MagicMock,
        audio_file: Path,
    ) -> None:
        def transcribe_file(_transcription: Any, _on_progress: Any, token: Any) -> str:
            controller.cancel_transcription()  # The user clicks "Cancel"
            token.raise_if_cancelled()
            return "text"

        whisperx_handler.transcribe_file.side_effect = transcribe_file

        controller.prepare_for_transcription(
            make_transcription(audio_source_path=audio_file, should_autosave=True)
        )

        assert fake_view.processed_statuses == ["Transcription cancelled."]
        assert ("Cancelling…", None) in fake_view.progress_updates
        assert fake_view.displayed_texts == []
        whisperx_handler.save_transcription.assert_not_called()

    def test_cancelling_a_directory_skips_the_remaining_files(
        self,
        controller: MainController,
        fake_view: FakeView,
        whisperx_handler: MagicMock,
        tmp_path: Path,
    ) -> None:
        create_files(tmp_path, "a.mp3", "b.mp3")

        def transcribe_file(_transcription: Any, _on_progress: Any, _token: Any) -> str:
            controller.cancel_transcription()
            return "text"

        whisperx_handler.transcribe_file.side_effect = transcribe_file

        controller.prepare_for_transcription(
            make_transcription(
                audio_source=AudioSource.DIRECTORY, audio_source_path=tmp_path
            )
        )

        assert whisperx_handler.transcribe_file.call_count == 1
        assert fake_view.processed_statuses == ["Transcription cancelled."]

    def test_a_new_transcription_is_not_affected_by_a_previous_cancellation(
        self,
        controller: MainController,
        fake_view: FakeView,
        whisperx_handler: MagicMock,
        audio_file: Path,
    ) -> None:
        controller._is_transcribing = True
        controller.cancel_transcription()

        controller.prepare_for_transcription(
            make_transcription(audio_source_path=audio_file)
        )

        assert fake_view.displayed_texts == ["whisperx text"]

    def test_cancel_without_transcription_does_nothing(
        self, controller: MainController, fake_view: FakeView
    ) -> None:
        controller.cancel_transcription()

        assert fake_view.progress_updates == []


class TestPreloadModel:
    def test_preloads_the_model_if_whisperx_is_selected(
        self,
        controller: MainController,
        fake_view: FakeView,
        whisperx_handler: MagicMock,
    ) -> None:
        controller.preload_model()

        whisperx_handler.preload_model.assert_called_once()
        assert fake_view.statuses == ["WhisperX model ready."]

    def test_does_not_show_a_status_if_the_model_is_not_downloaded(
        self,
        controller: MainController,
        fake_view: FakeView,
        whisperx_handler: MagicMock,
    ) -> None:
        whisperx_handler.preload_model.return_value = False

        controller.preload_model()

        assert fake_view.statuses == []
        assert fake_view.errors == []

    def test_does_not_preload_with_other_methods(
        self, controller: MainController, whisperx_handler: MagicMock
    ) -> None:
        ConfigManager.modify_value(
            ConfigTranscription.Key.SECTION,
            ConfigTranscription.Key.METHOD,
            TranscriptionMethod.GOOGLE_API.value,
        )

        controller.preload_model()

        whisperx_handler.preload_model.assert_not_called()

    def test_does_not_preload_during_a_transcription(
        self, controller: MainController, whisperx_handler: MagicMock
    ) -> None:
        controller._is_transcribing = True

        controller.preload_model()

        whisperx_handler.preload_model.assert_not_called()

    def test_preload_errors_are_shown(
        self,
        controller: MainController,
        fake_view: FakeView,
        whisperx_handler: MagicMock,
    ) -> None:
        whisperx_handler.preload_model.side_effect = OSError("No internet")

        controller.preload_model()

        assert fake_view.errors == [
            "Could not load the WhisperX model: OSError: No internet"
        ]


class FakeMicrophone:
    """Imitates `audio_utils.Microphone`, returning the given chunks of audio."""

    SAMPLE_WIDTH = 2

    def __init__(self, controller: MainController, chunks: list[bytes]) -> None:
        self._controller = controller
        self._chunks = chunks
        self.sample_rate = 16000
        self.device_indexes: list[int | None] = []

    def __call__(self, device_index: int | None = None) -> "FakeMicrophone":
        self.device_indexes.append(device_index)
        return self

    def __enter__(self) -> "FakeMicrophone":
        return self

    def __exit__(self, *_args: Any) -> None:
        pass

    def read(self) -> bytes:
        chunk = self._chunks.pop(0)

        if not self._chunks:
            self._controller.stop_recording_from_mic()  # The user clicks "Stop"

        return chunk


class TestMicRecording:
    @pytest.fixture(autouse=True)
    def recording_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
        path = tmp_path / "mic-output.wav"
        monkeypatch.setattr(main_controller, "MIC_RECORDING_PATH", path)
        monkeypatch.setattr(mic_recorder, "PROGRESS_INTERVAL_SECONDS", 0)
        return path

    def test_recording_is_transcribed_and_removed(
        self,
        controller: MainController,
        fake_view: FakeView,
        whisperx_handler: MagicMock,
        recording_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        chunk = make_tone(duration_ms=100).set_frame_rate(16000).raw_data
        microphone = FakeMicrophone(controller, [chunk, chunk])
        monkeypatch.setattr(au, "Microphone", microphone)

        def transcribe_file(transcription: Any, _on_progress: Any, _token: Any) -> str:
            recorded_audio = AudioSegment.from_wav(transcription.audio_source_path)
            assert len(recorded_audio) == pytest.approx(200, abs=5)
            return "recorded text"

        whisperx_handler.transcribe_file.side_effect = transcribe_file

        controller.prepare_for_transcription(
            make_transcription(audio_source=AudioSource.MIC, mic_device_index=3)
        )

        assert microphone.device_indexes == [3]
        assert fake_view.displayed_texts == ["recorded text"]
        assert fake_view.stop_recording_calls == 1
        assert len(fake_view.recording_updates) == 2
        assert all(level > 0 for _elapsed, level in fake_view.recording_updates)
        assert not recording_path.exists()

    def test_recording_without_audio_shows_error(
        self,
        controller: MainController,
        fake_view: FakeView,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(au, "Microphone", FakeMicrophone(controller, [b""]))

        controller.prepare_for_transcription(
            make_transcription(audio_source=AudioSource.MIC)
        )

        assert fake_view.errors == ["No audio was recorded."]
        assert fake_view.stop_recording_calls == 2  # By the user and by the error


class TestSaveTranscription:
    def save(
        self,
        transcriber: Any,
        tmp_path: Path,
        text: str = "new",
        **transcription_kwargs: Any,
    ) -> Path:
        saver = TranscriptionSaver(make_transcription(**transcription_kwargs))
        return saver.save(
            transcriber, TranscriptionResult(text), tmp_path / "audio.mp3"
        )

    def test_saves_next_to_the_file(self, tmp_path: Path) -> None:
        folder = self.save(GoogleApiTranscriber(), tmp_path)

        assert (tmp_path / "audio.txt").read_text() == "new"
        assert folder == tmp_path.resolve()

    def test_existing_files_are_not_overwritten(self, tmp_path: Path) -> None:
        existing_file = tmp_path / "audio.txt"
        existing_file.write_text("previous")

        self.save(GoogleApiTranscriber(), tmp_path)

        assert existing_file.read_text() == "previous"

    def test_existing_files_are_overwritten_if_requested(self, tmp_path: Path) -> None:
        existing_file = tmp_path / "audio.txt"
        existing_file.write_text("previous")

        self.save(GoogleApiTranscriber(), tmp_path, should_overwrite=True)

        assert existing_file.read_text() == "new"

    @pytest.mark.parametrize(
        "transcriber", [GoogleApiTranscriber(), OpenAiApiTranscriber()]
    )
    def test_without_text_raises_an_error(
        self, transcriber: Any, tmp_path: Path
    ) -> None:
        with pytest.raises(ValueError, match="no transcription to save"):
            self.save(transcriber, tmp_path, text="")

        assert list(tmp_path.glob("audio.*")) == []

    def test_api_transcriptions_are_saved_in_the_response_format(
        self, tmp_path: Path
    ) -> None:
        self.save(
            OpenAiApiTranscriber(),
            tmp_path,
            text="hello",
            output_file_types=["json"],
            api_response_format="json",
        )

        assert (tmp_path / "audio.json").read_text() == '{"text": "hello"}'

    def test_whisperx_with_several_file_types_uses_the_file_stem(
        self, whisperx_handler: MagicMock, tmp_path: Path
    ) -> None:
        self.save(
            WhisperXTranscriber(whisperx_handler),
            tmp_path,
            output_file_types=["srt", "txt"],
            should_overwrite=True,
        )

        whisperx_handler.save_transcription.assert_called_once_with(
            file_path=tmp_path / "audio",
            output_file_types=["srt", "txt"],
            should_overwrite=True,
        )


class TestOpenAiApi:
    @pytest.fixture
    def api_transcript(self, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
        transcribe_file = MagicMock(
            return_value=ApiTranscript(
                "Hello world.",
                [
                    TranscriptSegment(0.0, 1.0, "Hello", "SPEAKER_A"),
                    TranscriptSegment(1.0, 2.0, "world.", "SPEAKER_A"),
                ],
                "en",
                2.0,
            )
        )
        monkeypatch.setattr(OpenAiApiHandler, "transcribe_file", transcribe_file)
        return transcribe_file

    def test_the_segments_and_the_language_are_sent_to_the_view(
        self,
        controller: MainController,
        fake_view: FakeView,
        api_transcript: MagicMock,
        audio_file: Path,
    ) -> None:
        controller.prepare_for_transcription(
            make_transcription(
                method=TranscriptionMethod.WHISPER_API,
                audio_source_path=audio_file,
                api_model="gpt-4o-transcribe-diarize",
            )
        )

        assert api_transcript.call_args.args[0].api_model == "gpt-4o-transcribe-diarize"
        [(file_path, text, segments, language)] = fake_view.transcribed_files
        assert (file_path, text, language) == (audio_file, "Hello world.", "en")
        assert [segment.text for segment in segments] == ["Hello", "world."]

    def test_the_files_of_a_folder_are_saved_in_the_response_format(
        self,
        controller: MainController,
        fake_view: FakeView,
        api_transcript: MagicMock,
        tmp_path: Path,
    ) -> None:
        create_files(tmp_path, "a.mp3")

        controller.prepare_for_transcription(
            make_transcription(
                method=TranscriptionMethod.WHISPER_API,
                audio_source=AudioSource.DIRECTORY,
                audio_source_path=tmp_path,
                should_autosave=True,
                output_file_types=["srt"],
                api_response_format="srt",
            )
        )

        assert fake_view.errors == []
        assert (tmp_path / "a.srt").read_text() == (
            "1\n00:00:00,000 --> 00:00:01,000\n[SPEAKER_A]: Hello\n\n"
            "2\n00:00:01,000 --> 00:00:02,000\n[SPEAKER_A]: world.\n"
        )

    def test_formats_with_timestamps_need_a_model_that_returns_them(
        self,
        controller: MainController,
        fake_view: FakeView,
        api_transcript: MagicMock,
        tmp_path: Path,
    ) -> None:
        create_files(tmp_path, "a.mp3")
        transcription = make_transcription(
            method=TranscriptionMethod.WHISPER_API,
            audio_source=AudioSource.DIRECTORY,
            audio_source_path=tmp_path,
            should_autosave=True,
            output_file_types=["vtt"],
            api_response_format="vtt",
            api_model="gpt-transcribe",
        )

        controller.prepare_for_transcription(transcription)

        assert "doesn't return timestamps" in fake_view.errors[0]
        api_transcript.assert_not_called()

        # Translations are made by Whisper, which returns them
        transcription.should_translate = True
        controller.prepare_for_transcription(transcription)
        assert (tmp_path / "a.vtt").exists()


class TestDirectoryReport:
    def test_renders_the_status_of_each_file_relative_to_the_directory(
        self, tmp_path: Path
    ) -> None:
        files = [tmp_path / "a.mp3", tmp_path / "sub" / "b.mp3"]
        report = DirectoryReport(tmp_path, files)

        report.update(files[0], FileStatus.FAILED, "Error")

        assert report.render("Summary") == "Summary\n\n✗ a.mp3 — Error\n• sub/b.mp3"
        assert (report.done, report.failed, report.total) == (0, 1, 2)


class FakeFolderWatcher:
    """Returns a batch of files on each poll."""

    batches: list[list[Path]] = []

    def __init__(self, _dir_path: Path) -> None:
        self._batches = iter(self.batches)

    def poll(self) -> list[Path]:
        return next(self._batches, [])


class TestWatchFolder:
    @pytest.fixture(autouse=True)
    def fake_watcher(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(folder_transcriber, "FolderWatcher", FakeFolderWatcher)
        monkeypatch.setattr(folder_transcriber, "WATCH_POLL_INTERVAL_SECONDS", 0)

    def watch(self, controller: MainController, directory: Path) -> None:
        controller.prepare_for_transcription(
            make_transcription(
                audio_source=AudioSource.WATCH,
                audio_source_path=directory,
                should_autosave=True,
            )
        )

    def stop_after(
        self, controller: MainController, handler: MagicMock, transcriptions: int
    ) -> None:
        """Stops watching (as the user would) after some transcriptions."""

        def transcribe_file(_transcription: Any, _on_progress: Any, _token: Any) -> str:
            if handler.transcribe_file.call_count >= transcriptions:
                controller.cancel_transcription()
            return "text"

        handler.transcribe_file.side_effect = transcribe_file

    def test_transcribes_and_saves_the_new_files(
        self,
        controller: MainController,
        fake_view: FakeView,
        whisperx_handler: MagicMock,
        tmp_path: Path,
    ) -> None:
        create_files(tmp_path, "a.mp3", "b.mp3")
        FakeFolderWatcher.batches = [[tmp_path / "a.mp3"], [], [tmp_path / "b.mp3"]]
        self.stop_after(controller, whisperx_handler, transcriptions=2)

        self.watch(controller, tmp_path)

        saved_paths = [
            call.kwargs["file_path"]
            for call in whisperx_handler.save_transcription.call_args_list
        ]
        assert saved_paths == [tmp_path / "a.txt", tmp_path / "b.txt"]
        assert fake_view.displayed_texts[0].startswith("Waiting for new files")
        assert fake_view.displayed_texts[-1] == "✓ a.mp3\n✓ b.mp3"
        assert fake_view.processed_statuses == [
            "Stopped watching the folder. Files transcribed: 2."
        ]
        assert fake_view.saved_folders == [tmp_path]

    def test_failed_files_do_not_stop_the_watcher(
        self,
        controller: MainController,
        fake_view: FakeView,
        whisperx_handler: MagicMock,
        tmp_path: Path,
    ) -> None:
        create_files(tmp_path, "a.mp3", "b.mp3")
        FakeFolderWatcher.batches = [[tmp_path / "a.mp3", tmp_path / "b.mp3"]]

        def transcribe_file(transcription: Any, _on_progress: Any, _token: Any) -> str:
            if transcription.audio_source_path.name == "a.mp3":
                raise ValueError("Broken file")
            controller.cancel_transcription()
            return "text"

        whisperx_handler.transcribe_file.side_effect = transcribe_file

        self.watch(controller, tmp_path)

        assert fake_view.displayed_texts[-1] == "✗ a.mp3 — Broken file\n✓ b.mp3"
        assert fake_view.errors == []

    def test_files_with_transcription_are_skipped(
        self,
        controller: MainController,
        fake_view: FakeView,
        whisperx_handler: MagicMock,
        tmp_path: Path,
    ) -> None:
        create_files(tmp_path, "a.mp3", "a.txt", "b.mp3")
        FakeFolderWatcher.batches = [[tmp_path / "a.mp3", tmp_path / "b.mp3"]]
        self.stop_after(controller, whisperx_handler, transcriptions=1)

        self.watch(controller, tmp_path)

        assert whisperx_handler.transcribe_file.call_count == 1
        assert fake_view.displayed_texts[-1] == "✓ b.mp3"

    def test_stopping_without_new_files(
        self,
        controller: MainController,
        fake_view: FakeView,
        whisperx_handler: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        FakeFolderWatcher.batches = []
        # The user stops watching while waiting for files
        monkeypatch.setattr(
            CancellationToken, "wait", lambda _self, _timeout: True, raising=True
        )

        self.watch(controller, tmp_path)

        assert fake_view.processed_statuses == [
            "Stopped watching the folder. Files transcribed: 0."
        ]
        assert fake_view.saved_folders == []
        whisperx_handler.transcribe_file.assert_not_called()

    def test_requires_a_folder(
        self, controller: MainController, fake_view: FakeView, audio_file: Path
    ) -> None:
        self.watch(controller, audio_file)

        assert fake_view.errors == ["Please select a valid folder."]


def test_autosave_uses_the_output_dir(
    controller: MainController,
    whisperx_handler: MagicMock,
    audio_file: Path,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "out"

    controller.prepare_for_transcription(
        make_transcription(
            audio_source_path=audio_file, should_autosave=True, output_dir=output_dir
        )
    )

    saved_path = whisperx_handler.save_transcription.call_args.kwargs["file_path"]
    assert saved_path == output_dir / "speech.txt"


def test_folders_mirror_their_subfolders_in_the_output_dir(
    controller: MainController,
    fake_view: FakeView,
    whisperx_handler: MagicMock,
    tmp_path: Path,
) -> None:
    source_dir, output_dir = tmp_path / "source", tmp_path / "out"
    create_files(source_dir, "a/x.mp3", "b/x.mp3", "c/y.mp3")
    # Already transcribed in the output dir, so it's skipped
    create_files(output_dir, "c/y.txt")

    controller.prepare_for_transcription(
        make_transcription(
            audio_source=AudioSource.DIRECTORY,
            audio_source_path=source_dir,
            should_autosave=True,
            output_dir=output_dir,
        )
    )

    saved_paths = [
        call.kwargs["file_path"]
        for call in whisperx_handler.save_transcription.call_args_list
    ]
    assert fake_view.errors == []
    assert saved_paths == [output_dir / "a" / "x.txt", output_dir / "b" / "x.txt"]
    assert (output_dir / "a").is_dir()


def test_get_output_dir() -> None:
    file_path = Path("/source/sub/a.mp3")

    assert get_output_dir(file_path, None) == Path("/source/sub")
    assert get_output_dir(file_path, Path("/out")) == Path("/out")
    assert get_output_dir(file_path, Path("/out"), Path("/source")) == Path("/out/sub")
    assert get_output_dir(file_path, Path("/out"), Path("/other")) == Path("/out")
