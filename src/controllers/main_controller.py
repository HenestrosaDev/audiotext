import dataclasses
import functools
import logging
import tempfile
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import utils.audio_utils as au
import utils.config_manager as cm
from controllers.folder_transcriber import FolderTranscriber
from controllers.mic_recorder import MicRecorder
from controllers.transcription_saver import TranscriptionSaver
from controllers.transcription_validator import validate_transcription
from handlers.live_transcriber import LiveTranscriber
from handlers.transcribers import create_transcribers
from handlers.url_handler import UrlHandler
from handlers.whisperx_handler import WhisperXHandler
from interfaces.transcriber import Transcriber
from interfaces.transcription_view import RecordingView, TranscriptionView
from models.transcription import Transcription, TranscriptionResult
from utils.cancellation import CancellationToken, TranscriptionCancelledError
from utils.enums import AudioSource, TranscriptionMethod
from utils.errors import format_error
from utils.i18n import _
from utils.progress import ProgressCallback
from utils.time_format import format_elapsed_time

logger = logging.getLogger(__name__)

MIC_RECORDING_PATH = Path(tempfile.gettempdir()) / "audiotext-mic-output.wav"
URL_DOWNLOAD_PATH = Path(tempfile.gettempdir()) / "audiotext-url-download"


class MainController:
    """
    Runs the transcriptions requested by the view in a background thread, so the
    UI stays responsive, and reports their progress and results to the view.
    """

    def __init__(
        self,
        view: TranscriptionView,
        recording_view: RecordingView,
        whisperx_handler: WhisperXHandler | None = None,
        transcribers: Mapping[TranscriptionMethod, Transcriber] | None = None,
    ) -> None:
        """
        :param recording_view: Shows the recordings from the microphone while
                               they're being made.
        :param whisperx_handler: Transcribes with WhisperX and keeps its models
                                 loaded. By default, it uses the configuration of
                                 `config.ini`.
        :param transcribers: The transcriber of each transcription method. By
                             default, the ones of the app.
        """
        self.view = view
        self.recording_view = recording_view
        self._is_transcribing = False
        self._cancellation_token = CancellationToken()

        self._whisperx_handler = whisperx_handler or WhisperXHandler()
        self._transcribers = transcribers or create_transcribers(self._whisperx_handler)
        self._mic_recorder = MicRecorder(
            LiveTranscriber(
                on_text=lambda text: self._ui(self.recording_view.on_live_text, text),
                on_status=lambda message: self._ui(
                    self.recording_view.on_live_status, message
                ),
            ),
            on_progress=lambda elapsed_seconds, level: self._ui(
                self.recording_view.on_recording_progress, elapsed_seconds, level
            ),
        )

    # PUBLIC METHODS

    def prepare_for_transcription(self, transcription: Transcription) -> None:
        """
        Validates the transcription settings and starts the transcription process in
        a background thread.
        """
        try:
            validate_transcription(transcription)
        except Exception as e:
            self._show_failure(e)
            return

        self._cancellation_token = CancellationToken()
        self._is_transcribing = True

        self._start_background_task(
            lambda: self._run_process(self._get_process(transcription))
        )

    def cancel_transcription(self) -> None:
        """
        Requests the cancellation of the transcription in progress. The process stops
        at the next safe point (between files, chunks or batches).
        """
        if self._is_transcribing:
            self._cancellation_token.cancel()
            self._report_progress(_("Cancelling…"), None)

    def stop_recording_from_mic(self) -> None:
        """
        Stops recording audio from the microphone. The recorded audio is transcribed
        right after.
        """
        self._mic_recorder.stop()
        self.recording_view.on_stop_recording_from_mic()

    def preload_model(self) -> None:
        """
        Loads the WhisperX model of the current configuration in the background, so
        the transcription can start right away. It does nothing if WhisperX is not
        the selected transcription method or if the model is not downloaded yet, as
        it's downloaded when the user transcribes with it.
        """
        config_transcription = cm.ConfigManager.get_config_transcription()

        if config_transcription.method != TranscriptionMethod.WHISPERX.value:
            return

        # The transcription in progress will load the model when it needs it
        if not self._is_transcribing:
            self._start_background_task(self._preload_model)

    # PROCESSES

    def _get_process(self, transcription: Transcription) -> Callable[[], str]:
        """
        :return: The process that transcribes the audio source of the transcription,
                 which returns a summary of the result.
        """
        source = transcription.audio_source

        if source == AudioSource.MIC:
            return functools.partial(self._transcribe_recording, transcription)
        if source == AudioSource.YOUTUBE:
            return functools.partial(self._transcribe_url, transcription)
        if source in (AudioSource.DIRECTORY, AudioSource.WATCH):
            folder_transcriber = FolderTranscriber(
                transcription.audio_source_path,
                self.view,
                TranscriptionSaver(transcription),
                functools.partial(self._transcribe_file, transcription),
                self._cancellation_token,
            )
            if source == AudioSource.WATCH:
                return folder_transcriber.watch
            return folder_transcriber.transcribe_all

        return functools.partial(
            self._transcribe_single_file,
            transcription,
            transcription.audio_source_path,
        )

    def _run_process(self, process: Callable[[], str]) -> None:
        """
        Runs a transcription process. Upon completion, cancellation or error, it
        notifies the view that the transcription has been processed, along with a
        summary of the result.
        """
        status: str | None = None
        error_message = None

        try:
            status = process()
        except TranscriptionCancelledError:
            status = _("Transcription cancelled.")
        except Exception as e:
            logger.error("An error occurred", exc_info=e)
            error_message = format_error(e)
        finally:
            self._is_transcribing = False
            # The error is shown first, so the view knows the result has failed
            # when it's notified that the process has finished
            if error_message:
                self._ui(self.view.show_error, error_message)

            self._ui(self.view.on_processed_transcription, status)

    def _transcribe_url(self, transcription: Transcription) -> str:
        assert transcription.url
        self._report_progress(_("Downloading…"), None)
        file_path = UrlHandler.download(
            transcription.url,
            transcription.media_path or URL_DOWNLOAD_PATH,
            self._cancellation_token,
        )
        self._ui(self.view.on_media_downloaded, file_path)

        return self._transcribe_single_file(transcription, file_path)

    def _transcribe_recording(self, transcription: Transcription) -> str:
        try:
            recording_path = self._mic_recorder.record(
                transcription, transcription.media_path or MIC_RECORDING_PATH
            )
        except Exception:
            self._ui(self.recording_view.on_stop_recording_from_mic)
            raise

        return self._transcribe_single_file(transcription, recording_path)

    def _transcribe_single_file(
        self, transcription: Transcription, file_path: Path
    ) -> str:
        start_time = time.monotonic()
        self._transcribe_file(transcription, file_path, self._report_progress)

        return _("Done in {duration}.").format(
            duration=format_elapsed_time(time.monotonic() - start_time)
        )

    def _transcribe_file(
        self,
        transcription: Transcription,
        file_path: Path,
        on_progress: ProgressCallback,
    ) -> None:
        """
        Transcribes the audio of a file, sends the result to the view and saves it
        if autosave is enabled. Temporary audio files (microphone and URL) are
        removed after the transcription unless the history keeps them.
        """
        transcriber = self._get_transcriber(transcription.method)
        source = transcription.audio_source
        has_several_files = bool(source and source.has_several_files)

        try:
            result = self._transcribe_audio(
                transcriber,
                dataclasses.replace(transcription, audio_source_path=file_path),
                on_progress,
            )
        finally:
            if source and source.is_temporary and transcription.media_path is None:
                file_path.unlink(missing_ok=True)

        self._ui(
            self.view.on_file_transcribed,
            file_path,
            result.text,
            result.segments,
            result.language,
        )

        if not has_several_files:
            self._ui(self.view.display_text, result.text)

        if transcription.should_autosave:
            folder = TranscriptionSaver(transcription).save(
                transcriber, result, file_path
            )
            # The files of a folder are notified once all of them are transcribed
            if not has_several_files:
                self._ui(self.view.on_transcription_saved, folder)

    def _transcribe_audio(
        self,
        transcriber: Transcriber,
        transcription: Transcription,
        on_progress: ProgressCallback,
    ) -> TranscriptionResult:
        """
        Transcribes the audio of the transcription, isolating the speech first if
        the transcription requires it.
        """
        if not transcription.should_isolate_speech:
            return transcriber.transcribe(
                transcription, on_progress, self._cancellation_token
            )

        on_progress(_("Isolating the speech…"), None)
        isolated_path = au.isolate_speech(
            transcription.audio_source_path,
            Path(tempfile.gettempdir())
            / f"audiotext-speech-{threading.get_ident()}.wav",
        )

        try:
            self._cancellation_token.raise_if_cancelled()
            return transcriber.transcribe(
                dataclasses.replace(transcription, audio_source_path=isolated_path),
                on_progress,
                self._cancellation_token,
            )
        finally:
            isolated_path.unlink(missing_ok=True)

    def _get_transcriber(self, method: TranscriptionMethod | None) -> Transcriber:
        """
        :raises ValueError: If the transcription method is not supported.
        """
        if method is None or method not in self._transcribers:
            raise ValueError(f"Unsupported transcription method: {method}")

        return self._transcribers[method]

    def _preload_model(self) -> None:
        try:
            is_loaded = self._whisperx_handler.preload_model(
                on_progress=lambda message, _fraction: self._show_status(message)
            )

            if is_loaded:
                self._show_status(_("WhisperX model ready."))
        except Exception as e:
            logger.error("Could not preload the WhisperX model", exc_info=e)

            if not self._is_transcribing:
                self._ui(
                    self.view.show_error,
                    _("Could not load the WhisperX model: {error}").format(
                        error=format_error(e)
                    ),
                )

    # VIEW UPDATES

    @staticmethod
    def _start_background_task(task: Callable[[], None]) -> None:
        threading.Thread(target=task, daemon=True).start()

    def _ui(self, callback: Callable[..., Any], *args: Any) -> None:
        """
        Schedules a view update on the UI thread, since Tkinter widgets must not be
        modified from background threads.
        """
        self.view.run_on_ui_thread(callback, *args)

    def _report_progress(self, message: str, fraction: float | None) -> None:
        self._ui(self.view.on_transcription_progress, message, fraction)

    def _show_status(self, message: str) -> None:
        # The progress of a transcription takes precedence over other statuses
        if not self._is_transcribing:
            self._ui(self.view.show_status, message)

    def _show_failure(self, e: Exception) -> None:
        """Shows the error of a transcription that couldn't start."""
        logger.error("Could not start the transcription", exc_info=e)
        self._ui(self.view.show_error, format_error(e))
        self._ui(self.view.on_processed_transcription, None)
