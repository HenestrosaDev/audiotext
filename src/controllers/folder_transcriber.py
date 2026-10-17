import logging
import threading
import time
from collections import deque
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
from utils.time_format import format_elapsed_time

logger = logging.getLogger(__name__)

# How often a watched folder is scanned for new files
WATCH_POLL_INTERVAL_SECONDS = 2.0


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


# Transcribes a file, reporting its progress, and saves its transcription,
# replacing the existing one if the flag is set
TranscribeFile = Callable[[Path, ProgressCallback, bool], None]


class WatchPausedError(Exception):
    """Raised to stop watching a folder that is paused (see `pause`)."""


class FolderTranscriber:
    """
    Transcribes the files of a folder one after the other, showing the status of
    each file in the view. If a file fails, the error is shown in its status and
    the rest of the files are transcribed.

    While it runs, more files of the folder can be transcribed again (see
    `retranscribe`), e.g. a file that the user wants to transcribe again while the
    folder is watched. A watched folder can also be paused (see `pause`), so
    something else is transcribed meanwhile.
    """

    def __init__(
        self,
        dir_path: Path,
        view: TranscriptionView,
        saver: TranscriptionSaver,
        transcribe_file: TranscribeFile,
        cancellation_token: CancellationToken,
        retranscribed_files: list[Path] | None = None,
        should_scan_folder: bool = True,
        should_overwrite: bool = False,
        should_transcribe_existing: bool = False,
        watch_known_files: dict[Path, tuple[int, int]] | None = None,
        should_wait_for_folder: bool = False,
    ) -> None:
        """
        :param retranscribed_files: Files of the folder transcribed again,
                                    replacing their transcriptions.
        :param should_scan_folder: Whether the files of the folder are transcribed.
                                   If not, only the `retranscribed_files` are.
        :param should_overwrite: Whether the files that already have a
                                 transcription are transcribed again.
        :param should_transcribe_existing: Whether watching the folder transcribes
                                           the files it already contains first.
        :param watch_known_files: The files that a paused watch had seen, to go
                                  on from where it left off.
        :param should_wait_for_folder: Whether watching the folder while it isn't
                                       available waits until it is.
        """
        self._dir_path = dir_path
        self._view = view
        self._saver = saver
        self._transcribe_file = transcribe_file
        self._cancellation_token = cancellation_token
        self._should_scan_folder = should_scan_folder
        self._should_overwrite = should_overwrite
        self._should_transcribe_existing = should_transcribe_existing
        self._watch_known_files = watch_known_files
        self._should_wait_for_folder = should_wait_for_folder
        # The files to transcribe again, requested from the UI thread
        self._lock = threading.Lock()
        self._requested: list[Path] = list(retranscribed_files or [])
        self._is_closed = False
        self._is_watching = False
        self._is_pause_requested = False
        # How long the files took to transcribe, by their size, to estimate how
        # long the rest will take
        self._done_bytes = 0
        self._done_seconds = 0.0

    def retranscribe(self, files: list[Path]) -> bool:
        """
        Transcribes some files of the folder again once the current one is done,
        replacing their transcriptions. It can be called from any thread.

        :return: Whether they'll be transcribed, which they aren't if the folder is
                 already done.
        """
        with self._lock:
            if self._is_closed:
                return False
            self._requested.extend(files)
            return True

    def pause(self) -> bool:
        """
        Stops watching the folder once the current file is done, so it can be
        watched again later from where it left off (see
        `TranscriptionView.on_watch_paused`). It can be called from any thread.

        :return: Whether it'll be paused, which it isn't if it's not watching.
        """
        with self._lock:
            if self._is_closed or not self._is_watching:
                return False
            self._is_pause_requested = True
            return True

    def _raise_if_paused(self) -> None:
        with self._lock:
            if self._is_pause_requested:
                raise WatchPausedError()

    def _take_requested(self, is_last: bool = False) -> list[Path]:
        """
        :param is_last: Whether no more files are accepted after these, since the
                        process ends if there are none.
        """
        with self._lock:
            requested, self._requested = self._requested, []
            if is_last and not requested:
                self._is_closed = True
            return requested

    def _close(self) -> None:
        with self._lock:
            self._is_closed = True

    def transcribe_all(self) -> str:
        """
        Transcribes the supported files of the folder and its subfolders that
        don't have a transcription yet, and the ones transcribed again.

        :raises ValueError: If the folder doesn't contain any supported file.
        :raises TranscriptionCancelledError: If the transcription is cancelled.
        :return: A summary of the result.
        """
        try:
            return self._transcribe_all()
        finally:
            self._close()

    def _transcribe_all(self) -> str:
        files: list[Path] = []
        if self._should_scan_folder:
            folder_files = self._saver.list_files(self._dir_path)
            files = [f for f in folder_files if not self._saver.should_skip(f)]
            if skipped := [f for f in folder_files if f not in files]:
                self._ui(self._view.on_files_skipped, skipped)
        # Transcribed again even if they have a transcription
        overwritten: set[Path] = set()
        for file_path in self._take_requested():
            overwritten.add(file_path)
            if file_path not in files:
                files.append(file_path)

        if not files:
            if not self._saver.list_files(self._dir_path):
                raise ValueError(
                    _("The folder doesn't contain audio or video files to transcribe.")
                )
            summary = _("All the files already have a transcription.")
            self._ui(self._view.display_text, summary)
            return summary

        report = DirectoryReport(self._dir_path, files)
        self._ui(self._view.on_files_queued, files)
        pending = deque(files)
        sizes = {file_path: file_size(file_path) for file_path in files}

        while True:
            if not pending:
                # Files can still be requested while the last one is transcribed
                requested = self._take_requested(is_last=True)
                if not requested:
                    break
                self._queue_requested(requested, pending, overwritten, report)
            self._cancellation_token.raise_if_cancelled()

            file_path = pending.popleft()
            total = report.total
            idx = total - len(pending) - 1
            for other in pending:
                if other not in sizes:
                    sizes[other] = file_size(other)
            remaining_bytes = sum(sizes[other] for other in pending)
            start_time = time.monotonic()
            try:
                self._transcribe_reported_file(
                    file_path,
                    report,
                    self._directory_progress(
                        idx, total, file_path, sizes.get(file_path, 0), remaining_bytes
                    ),
                    self._should_overwrite or file_path in overwritten,
                )
            except TranscriptionCancelledError:
                report.update(file_path, FileStatus.PENDING)
                self._ui(self._view.display_text, report.render())
                raise
            self._done_bytes += sizes.get(file_path, 0)
            self._done_seconds += time.monotonic() - start_time
            self._queue_requested(self._take_requested(), pending, overwritten, report)

        summary = _("Transcribed {done} of {total} files.").format(
            done=report.done, total=report.total
        )
        self._ui(self._view.display_text, report.render(summary))
        self._ui(self._view.on_transcription_saved, self._saver.get_output_root())

        return summary

    def _queue_requested(
        self,
        requested: list[Path],
        pending: deque[Path],
        overwritten: set[Path],
        report: DirectoryReport,
    ) -> None:
        """Adds the files requested meanwhile to the ones left to transcribe."""
        if not requested:
            return
        for file_path in requested:
            overwritten.add(file_path)
            if file_path not in pending:
                pending.append(file_path)
                report.update(file_path, FileStatus.PENDING)
        self._ui(self._view.on_files_queued, requested)

    def watch(self) -> str:
        """
        Transcribes the files added to the folder, and the ones changed, until the
        process is cancelled or paused. The files that the folder already
        contains are ignored, unless it was asked to transcribe them first.

        :return: A summary of the result, or "" if it's paused.
        """
        report = DirectoryReport(self._dir_path, [])
        waiting_message = _("Waiting for new files in {folder}…").format(
            folder=self._dir_path
        )
        with self._lock:
            self._is_watching = not self._is_closed
        # The new files not transcribed yet, and the ones to transcribe again
        unfinished: list[Path] = []
        retranscribing: list[Path] = []
        watcher: FolderWatcher | None = None

        try:
            # Once it's available, so its files aren't taken for new ones
            self._wait_for_folder()
            # Before listing the existing files, so the ones added meanwhile are
            # found by the watcher
            watcher = FolderWatcher(
                self._dir_path, self._watch_known_files, self._saver.file_filter
            )
            if self._should_transcribe_existing and self._watch_known_files is None:
                unfinished = self._saver.get_files_to_transcribe(self._dir_path)
                if unfinished:
                    self._ui(self._view.on_files_queued, list(unfinished))
                self._transcribe_watched_files(report, unfinished)
            self._ui(self._view.display_text, waiting_message)

            while True:
                retranscribing += self._take_requested()
                self._transcribe_watched_files(
                    report, retranscribing, should_overwrite=True
                )
                self._raise_if_paused()
                self._ui(self._view.on_transcription_progress, waiting_message, None)

                if self._cancellation_token.wait(WATCH_POLL_INTERVAL_SECONDS):
                    raise TranscriptionCancelledError()
                self._raise_if_paused()
                # E.g. on a drive that was disconnected. Its files are found again
                # as they were once it's back
                if not self._dir_path.is_dir():
                    self._wait_for_folder()

                unfinished = watcher.poll()
                changed = watcher.changed_files
                # The ones changed are transcribed again
                retranscribing += [f for f in unfinished if f in changed]
                unfinished = [f for f in unfinished if f not in changed]
                self._transcribe_watched_files(report, unfinished)
        except (TranscriptionCancelledError, WatchPausedError):
            if self._is_pause_requested and watcher is not None:
                watcher.forget(unfinished)
                self._ui(
                    self._view.on_watch_paused,
                    watcher.known_files,
                    list(unfinished),
                    list(retranscribing),
                )
                return ""
            return _("Stopped watching the folder. Files transcribed: {done}.").format(
                done=report.done
            )
        finally:
            self._close()
            if report.done:
                self._ui(
                    self._view.on_transcription_saved, self._saver.get_output_root()
                )

    def _wait_for_folder(self) -> None:
        """
        Waits until the watched folder is available, if it should.

        :raises TranscriptionCancelledError: If the transcription is cancelled.
        :raises WatchPausedError: If the watch is paused.
        """
        if not self._should_wait_for_folder:
            return
        message = _("Waiting for the folder to be available: {folder}").format(
            folder=self._dir_path
        )
        while not self._dir_path.is_dir():
            self._ui(self._view.on_transcription_progress, message, None)
            if self._cancellation_token.wait(WATCH_POLL_INTERVAL_SECONDS):
                raise TranscriptionCancelledError()
            self._raise_if_paused()

    def _transcribe_watched_files(
        self,
        report: DirectoryReport,
        files: list[Path],
        should_overwrite: bool = False,
    ) -> None:
        """
        Transcribes some files, removing each one from the list once it's done, so
        the list keeps the ones left if it's paused or cancelled.

        :raises TranscriptionCancelledError: If the transcription is cancelled.
        :raises WatchPausedError: If the watch is paused.
        """
        while files:
            self._raise_if_paused()
            self._transcribe_watched_file(files[0], report, should_overwrite)
            files.pop(0)

    def _transcribe_watched_file(
        self, file_path: Path, report: DirectoryReport, should_overwrite: bool = False
    ) -> None:
        """
        :param should_overwrite: Whether to transcribe it again if it already has a
                                 transcription.
        :raises TranscriptionCancelledError: If the transcription is cancelled.
        """
        if not should_overwrite and self._saver.should_skip(file_path):
            return

        try:
            self._transcribe_reported_file(
                file_path,
                report,
                self._watched_file_progress(file_path),
                should_overwrite,
            )
        except TranscriptionCancelledError:
            report.update(file_path, FileStatus.PENDING, _("cancelled"))
            raise
        finally:
            self._ui(self._view.display_text, report.render())

    def _transcribe_reported_file(
        self,
        file_path: Path,
        report: DirectoryReport,
        on_progress: ProgressCallback,
        should_overwrite: bool = False,
    ) -> None:
        """
        Transcribes a file, updating its status in the report. Errors are shown in
        the report instead of being raised.

        :param should_overwrite: Whether to replace its existing transcription.

        :raises TranscriptionCancelledError: If the transcription is cancelled.
        """
        report.update(file_path, FileStatus.IN_PROGRESS)
        self._ui(self._view.display_text, report.render())
        self._ui(self._view.on_file_started, file_path)

        try:
            self._transcribe_file(file_path, on_progress, should_overwrite)
            report.update(file_path, FileStatus.DONE)
        except TranscriptionCancelledError:
            raise
        except Exception as e:
            logger.error("Could not transcribe %s", file_path, exc_info=e)
            report.update(file_path, FileStatus.FAILED, format_error(e))
            self._ui(self._view.on_file_failed, file_path, format_error(e))

    def _directory_progress(
        self,
        file_idx: int,
        total_files: int,
        file_path: Path,
        size: int = 0,
        remaining_bytes: int = 0,
    ) -> ProgressCallback:
        """
        Returns a progress callback that reports the progress of a file as part of
        the progress of the whole folder, and how long the rest will take, from
        how long the files done took.

        :param size: The size of the file, in bytes.
        :param remaining_bytes: The size of the files after it.
        """

        def on_progress(message: str, fraction: float | None) -> None:
            text = _("File {current} of {total} ({name}): {message}").format(
                current=file_idx + 1,
                total=total_files,
                name=file_path.name,
                message=message,
            )
            if self._done_bytes:
                left_bytes = remaining_bytes + size * (1 - (fraction or 0))
                seconds = self._done_seconds / self._done_bytes * left_bytes
                # Not before a minute is left, since it's only an estimate
                if seconds >= 60:
                    text += " · " + _("about {time} left").format(
                        time=format_elapsed_time(seconds)
                    )
            self._ui(
                self._view.on_transcription_progress,
                text,
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
