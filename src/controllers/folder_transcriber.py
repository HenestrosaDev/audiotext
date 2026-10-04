import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from controllers.directory_report import DirectoryReport, FileStatus
from controllers.transcription_saver import TranscriptionSaver
from interfaces.transcription_view import TranscriptionView
from utils.cancellation import CancellationToken, TranscriptionCancelledError
from utils.errors import format_error
from utils.folder_watcher import FolderWatcher
from utils.i18n import _
from utils.progress import ProgressCallback

logger = logging.getLogger(__name__)

# How often a watched folder is scanned for new files
WATCH_POLL_INTERVAL_SECONDS = 2.0

# Transcribes a file, reporting its progress, and saves its transcription
TranscribeFile = Callable[[Path, ProgressCallback], None]


class FolderTranscriber:
    """
    Transcribes the files of a folder one after the other, showing the status of
    each file in the view. If a file fails, the error is shown in its status and
    the rest of the files are transcribed.
    """

    def __init__(
        self,
        dir_path: Path,
        view: TranscriptionView,
        saver: TranscriptionSaver,
        transcribe_file: TranscribeFile,
        cancellation_token: CancellationToken,
    ) -> None:
        self._dir_path = dir_path
        self._view = view
        self._saver = saver
        self._transcribe_file = transcribe_file
        self._cancellation_token = cancellation_token

    def transcribe_all(self) -> str:
        """
        Transcribes the supported files of the folder and its subfolders.

        :raises ValueError: If the folder doesn't contain files to transcribe.
        :raises TranscriptionCancelledError: If the transcription is cancelled.
        :return: A summary of the result.
        """
        files = self._saver.get_files_to_transcribe(self._dir_path)

        if not files:
            raise ValueError(
                _(
                    "The folder doesn't contain files to transcribe. The files that "
                    "already have a transcription are skipped unless you check "
                    "'Overwrite existing files'."
                )
            )

        report = DirectoryReport(self._dir_path, files)
        self._ui(self._view.on_files_queued, files)

        for idx, file_path in enumerate(files):
            self._cancellation_token.raise_if_cancelled()

            try:
                self._transcribe_reported_file(
                    file_path,
                    report,
                    self._directory_progress(idx, len(files), file_path),
                )
            except TranscriptionCancelledError:
                report.update(file_path, FileStatus.PENDING)
                self._ui(self._view.display_text, report.render())
                raise

        summary = _("Transcribed {done} of {total} files.").format(
            done=report.done, total=report.total
        )
        self._ui(self._view.display_text, report.render(summary))
        self._ui(self._view.on_transcription_saved, self._saver.get_output_root())

        return summary

    def watch(self) -> str:
        """
        Transcribes the files added to the folder until the process is cancelled.
        The files that the folder already contains are ignored.

        :return: A summary of the result.
        """
        report = DirectoryReport(self._dir_path, [])
        waiting_message = _("Waiting for new files in {folder}…").format(
            folder=self._dir_path
        )

        try:
            watcher = FolderWatcher(self._dir_path)
            self._ui(self._view.display_text, waiting_message)

            while True:
                self._ui(self._view.on_transcription_progress, waiting_message, None)

                if self._cancellation_token.wait(WATCH_POLL_INTERVAL_SECONDS):
                    raise TranscriptionCancelledError()

                for file_path in watcher.poll():
                    self._transcribe_watched_file(file_path, report)
        except TranscriptionCancelledError:
            return _("Stopped watching the folder. Files transcribed: {done}.").format(
                done=report.done
            )
        finally:
            if report.done:
                self._ui(
                    self._view.on_transcription_saved, self._saver.get_output_root()
                )

    def _transcribe_watched_file(
        self, file_path: Path, report: DirectoryReport
    ) -> None:
        """
        :raises TranscriptionCancelledError: If the transcription is cancelled.
        """
        if self._saver.should_skip(file_path):
            return

        try:
            self._transcribe_reported_file(
                file_path, report, self._watched_file_progress(file_path)
            )
        except TranscriptionCancelledError:
            report.update(file_path, FileStatus.PENDING, _("cancelled"))
            raise
        finally:
            self._ui(self._view.display_text, report.render())

    def _transcribe_reported_file(
        self, file_path: Path, report: DirectoryReport, on_progress: ProgressCallback
    ) -> None:
        """
        Transcribes a file, updating its status in the report. Errors are shown in
        the report instead of being raised.

        :raises TranscriptionCancelledError: If the transcription is cancelled.
        """
        report.update(file_path, FileStatus.IN_PROGRESS)
        self._ui(self._view.display_text, report.render())
        self._ui(self._view.on_file_started, file_path)

        try:
            self._transcribe_file(file_path, on_progress)
            report.update(file_path, FileStatus.DONE)
        except TranscriptionCancelledError:
            raise
        except Exception as e:
            logger.error("Could not transcribe %s", file_path, exc_info=e)
            report.update(file_path, FileStatus.FAILED, format_error(e))
            self._ui(self._view.on_file_failed, file_path, format_error(e))

    def _directory_progress(
        self, file_idx: int, total_files: int, file_path: Path
    ) -> ProgressCallback:
        """
        Returns a progress callback that reports the progress of a file as part of
        the progress of the whole folder.
        """

        def on_progress(message: str, fraction: float | None) -> None:
            self._ui(
                self._view.on_transcription_progress,
                _("File {current} of {total} ({name}): {message}").format(
                    current=file_idx + 1,
                    total=total_files,
                    name=file_path.name,
                    message=message,
                ),
                (file_idx + (fraction or 0)) / total_files,
            )

        return on_progress

    def _watched_file_progress(self, file_path: Path) -> ProgressCallback:
        def on_progress(message: str, fraction: float | None) -> None:
            self._ui(
                self._view.on_transcription_progress,
                _("{name}: {message}").format(name=file_path.name, message=message),
                fraction,
            )

        return on_progress

    def _ui(self, callback: Callable[..., Any], *args: Any) -> None:
        self._view.run_on_ui_thread(callback, *args)
