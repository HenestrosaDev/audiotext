from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from interfaces.history_view import TranscriptionQueueView
from interfaces.transcription_runner import TranscriptionRunner
from interfaces.transcription_view import TranscriptionView
from models.history import EntryStatus, HistoryEntry
from models.transcript_segment import TranscriptSegment
from models.transcription_settings import TranscriptionSettings
from utils.enums import AudioSource
from utils.history_store import HistoryStore
from utils.validators import is_youtube_url


@dataclass
class Job:
    """The transcription being processed by the controller."""

    entry_id: str
    is_folder: bool
    is_mic: bool
    error: str | None = None
    is_cancel_requested: bool = False
    progress_message: str = ""
    progress_fraction: float | None = None
    current_child_id: str | None = None
    # Entries of the files of a folder, by path
    children: dict[str, str] = field(default_factory=dict)


def default_title(source: AudioSource, value: str) -> str:
    """The title of a new entry: the name of the file or folder, or the URL."""
    if source == AudioSource.YOUTUBE:
        return value
    return Path(value).name or value


def media_name_for_url(url: str) -> str:
    """A readable name for the file downloaded from a URL."""
    parts = urlsplit(url)
    if is_youtube_url(url):
        video_id = (
            parse_qs(parts.query).get("v", [""])[0] or PurePosixPath(parts.path).name
        )
        return f"YouTube {video_id}".strip()
    name = PurePosixPath(unquote(parts.path)).stem
    return name or parts.hostname or "download"


class TranscriptionQueue:
    """
    Keeps the queue of transcriptions waiting to be processed, starts them one
    after the other, and records their progress and results in the history.

    It implements the interface that the controller uses to report the progress
    (see `TranscriptionView`).
    """

    def __init__(
        self,
        store: HistoryStore,
        view: TranscriptionQueueView,
        create_runner: Callable[[TranscriptionView], TranscriptionRunner],
    ) -> None:
        """
        :param create_runner: Creates what runs the transcriptions, which reports
                              their progress to the queue.
        """
        self._store = store
        self.view = view
        self._job: Job | None = None
        self._queue: deque[str] = deque()
        # The entry created for the last recording, opened from the microphone view
        self.last_mic_entry_id: str | None = None
        self._runner = create_runner(self)

    def preload_model(self) -> None:
        if not self.is_busy():
            self._runner.preload_model()

    # QUEUE

    def is_busy(self) -> bool:
        return self._job is not None

    def get_progress(self, entry_id: str) -> float | None:
        job = self._job
        if job and job.entry_id == entry_id:
            return job.progress_fraction
        return None

    def get_progress_message(self, entry_id: str) -> tuple[str, float | None]:
        job = self._job
        if job and job.entry_id == entry_id:
            return job.progress_message, job.progress_fraction
        return "", None

    def get_queue_position(self, entry_id: str) -> int | None:
        if entry_id not in self._queue:
            return None
        return list(self._queue).index(entry_id) + (1 if self._job else 0)

    def start(
        self, source: AudioSource, value: str, settings: TranscriptionSettings
    ) -> None:
        """Adds a transcription from the steps of a new transcription."""
        entry = self._add_entry(source, value, settings)
        self._queue.append(entry.id)
        self.view.refresh_sidebar()
        self.view.select_entry(entry.id)
        self._run_next()

    def restart(
        self,
        entry_id: str,
        source: AudioSource,
        value: str,
        settings: TranscriptionSettings,
    ) -> None:
        """
        Transcribes again an entry that didn't finish, from the steps of a new
        transcription opened from it. If its source was changed, a new entry is
        added instead.
        """
        entry = self._store.get(entry_id)
        if entry is None or entry.status.is_active or entry.source != value:
            entry = self._add_entry(source, value, settings)
            self.view.refresh_sidebar()
        else:
            self._store.update(
                entry,
                kind=self._entry_kind(source, settings).value,
                settings=settings.to_dict(),
                method=settings.method,
                status=EntryStatus.QUEUED,
                error="",
            )
            self.view.on_entry_changed(entry.id)

        self._queue.append(entry.id)
        self.view.select_entry(entry.id)
        self._run_next()

    def _add_entry(
        self, source: AudioSource, value: str, settings: TranscriptionSettings
    ) -> HistoryEntry:
        entry = HistoryEntry(
            kind=self._entry_kind(source, settings).value,
            source=value,
            title=default_title(source, value),
            settings=settings.to_dict(),
            method=settings.method,
            media_path=value if source == AudioSource.FILE else None,
        )
        self._store.add(entry)
        return entry

    @staticmethod
    def _entry_kind(
        source: AudioSource, settings: TranscriptionSettings
    ) -> AudioSource:
        if source == AudioSource.DIRECTORY and settings.watch:
            return AudioSource.WATCH
        return source

    def retry_entry(self, entry_id: str) -> None:
        entry = self._store.get(entry_id)
        if entry is None or entry.status.is_active or entry.parent_id:
            return
        if entry.kind == AudioSource.MIC.value and not (
            entry.media_path and Path(entry.media_path).is_file()
        ):
            self.view.on_recording_unavailable(entry)
            return

        self._store.update(entry, status=EntryStatus.QUEUED, error="")
        self._queue.append(entry_id)
        self.view.on_entry_changed(entry_id)
        self.view.select_entry(entry_id)
        self._run_next()

    def cancel_entry(self, entry_id: str) -> None:
        entry = self._store.get(entry_id)
        if entry is None:
            return
        job = self._job

        if job and entry_id in (job.entry_id, *job.children.values()):
            if job.is_mic and self.view.is_recording():
                self.stop_recording()
            job.is_cancel_requested = True
            self._runner.cancel_transcription()
        elif entry_id in self._queue:
            self._queue.remove(entry_id)
            self._store.update(entry, status=EntryStatus.CANCELLED)
            self.view.on_entry_changed(entry_id)
            self._refresh_queue_positions()

    def _run_next(self) -> None:
        if self._job is not None:
            return

        while self._queue:
            entry = self._store.get(self._queue.popleft())
            if entry is not None:
                break
        else:
            return

        settings = TranscriptionSettings.from_dict(entry.settings)

        kind = AudioSource(entry.kind)
        media_path: Path | None = None
        if kind == AudioSource.YOUTUBE:
            media_path = self._store.new_media_path(
                entry.id, media_name_for_url(entry.source)
            )
            transcription = settings.to_transcription(
                kind, entry.source, media_path=media_path
            )
        elif kind == AudioSource.MIC:
            # A recording is transcribed again from the kept file
            transcription = settings.to_transcription(
                AudioSource.FILE, entry.media_path or ""
            )
        else:
            transcription = settings.to_transcription(kind, entry.source)

        self._job = Job(entry_id=entry.id, is_folder=entry.is_folder, is_mic=False)
        status = (
            EntryStatus.WATCHING
            if kind == AudioSource.WATCH
            else EntryStatus.PROCESSING
        )
        self._store.update(entry, status=status, error="", method=settings.method)
        self.view.on_entry_changed(entry.id)
        self._refresh_queue_positions()
        self._runner.prepare_for_transcription(transcription)

    def _refresh_queue_positions(self) -> None:
        for entry_id in self._queue:
            self.view.refresh_progress(entry_id)

    def _child_entry(
        self, file_path: Path, status: EntryStatus | None = None
    ) -> HistoryEntry | None:
        """Returns (creating it if needed) the entry of a file of the folder job."""
        job = self._job
        parent = self._store.get(job.entry_id) if job else None
        if job is None or parent is None:
            return None

        key = str(file_path)
        child = self._store.get(job.children.get(key)) or self._store.find_child(
            parent.id, key
        )
        if child is None:
            child = HistoryEntry(
                kind=AudioSource.FILE.value,
                source=key,
                title=file_path.name,
                parent_id=parent.id,
                settings=parent.settings,
                method=parent.method,
                media_path=key,
                status=status or EntryStatus.QUEUED,
            )
            self._store.add(child)
        job.children[key] = child.id
        return child

    def _finish_job(self, status_message: str | None) -> None:
        job = self._job
        self._job = None
        if job is None:
            return

        entry = self._store.get(job.entry_id)
        if entry is not None:
            if job.error:
                final_status = EntryStatus.FAILED
            elif job.is_cancel_requested:
                is_watch_stopped = entry.kind == AudioSource.WATCH.value
                final_status = (
                    EntryStatus.DONE if is_watch_stopped else EntryStatus.CANCELLED
                )
            else:
                final_status = EntryStatus.DONE

            # Files that didn't finish (e.g. when cancelling) are marked as such
            for child in self._store.children(entry.id):
                if child.status.is_active:
                    self._store.update(child, status=EntryStatus.CANCELLED)

            self._store.update(entry, status=final_status, error=job.error or "")
            self.view.on_entry_changed(entry.id)
            if entry.is_folder:
                self.view.refresh_sidebar()

            if job.is_mic:
                self.view.on_mic_finished(entry)
            self.view.on_transcription_finished(entry, status_message)

            # A folder that stops being watched is done, but nothing new is ready
            if final_status == EntryStatus.DONE and not job.is_cancel_requested:
                self.view.on_transcription_ready(entry)

        self._run_next()

    def _is_watch_job(self, job: Job) -> bool:
        entry = self._store.get(job.entry_id)
        return entry is not None and entry.kind == AudioSource.WATCH.value

    # MICROPHONE

    def start_recording(
        self, title: str, settings: TranscriptionSettings, device_index: int | None
    ) -> bool:
        """
        Records from the microphone and transcribes the recording when it stops.

        :param title: The title of its entry.
        :return: Whether the recording started, since only one transcription is
                 processed at a time.
        """
        if self.is_busy():
            return False

        entry = HistoryEntry(
            kind=AudioSource.MIC.value,
            source="",
            title=title,
            settings=settings.to_dict(),
            method=settings.method,
            status=EntryStatus.PROCESSING,
        )
        media_path = self._store.new_media_path(entry.id, f"{title}.wav")
        entry.media_path = str(media_path)
        self._store.add(entry)
        self.last_mic_entry_id = entry.id

        self._job = Job(entry_id=entry.id, is_folder=False, is_mic=True)
        self.view.refresh_sidebar()
        self._runner.prepare_for_transcription(
            settings.to_transcription(
                AudioSource.MIC,
                "",
                media_path=media_path,
                mic_device_index=device_index,
            )
        )
        return True

    def stop_recording(self) -> None:
        self._runner.stop_recording_from_mic()

    # CONTROLLER INTERFACE

    def run_on_ui_thread(self, callback: Callable[..., Any], *args: Any) -> None:
        self.view.run_on_ui_thread(callback, *args)

    def on_processed_transcription(self, status: str | None = None) -> None:
        self._finish_job(status)

    def on_transcription_progress(self, message: str, fraction: float | None) -> None:
        job = self._job
        if job is None:
            return
        job.progress_message, job.progress_fraction = message, fraction
        self.view.refresh_progress(job.entry_id)
        if job.is_mic:
            self.view.on_mic_progress(message)

    def on_transcription_saved(self, folder: Path) -> None:
        if self._job and (entry := self._store.get(self._job.entry_id)):
            self._store.update(entry, output_dir=str(folder))
        else:
            self.view.on_transcription_saved(folder)

    def show_status(self, message: str) -> None:
        self.view.show_status(message)

    def show_error(self, message: str) -> None:
        if self._job is not None:
            self._job.error = message
        else:
            self.view.show_status(message, is_error=True)

    def display_text(self, text: str) -> None:
        """The results are received per file (see `on_file_transcribed`)."""

    def on_media_downloaded(self, file_path: Path) -> None:
        if self._job and (entry := self._store.get(self._job.entry_id)):
            self._store.update(entry, media_path=str(file_path))

    def on_files_queued(self, files: list[Path]) -> None:
        for file_path in files:
            child = self._child_entry(file_path)
            if child and child.status != EntryStatus.QUEUED:
                self._store.update(child, status=EntryStatus.QUEUED, error="")
        if self._job:
            self.view.refresh_sidebar()
            self.view.refresh_entry_view(self._job.entry_id)

    def on_file_started(self, file_path: Path) -> None:
        is_new = self._job is not None and str(file_path) not in self._job.children
        child = self._child_entry(file_path, EntryStatus.PROCESSING)
        if child is None or self._job is None:
            return
        self._job.current_child_id = child.id
        self._store.update(child, status=EntryStatus.PROCESSING, error="")
        if is_new:
            self.view.refresh_sidebar()
        self.view.on_entry_changed(child.id)

    def on_file_transcribed(
        self,
        file_path: Path,
        text: str,
        segments: list[TranscriptSegment],
        language: str | None,
    ) -> None:
        job = self._job
        if job is None:
            return
        result: dict[str, Any] = {
            "text": text or "",
            "segments": segments,
            "language": language,
            "is_text_edited": False,
            # A summary or a translation of a previous transcription doesn't
            # apply to the new one
            "summary": {},
            "translation": {},
        }

        if job.is_folder:
            if child := self._child_entry(file_path):
                self._store.update(
                    child,
                    status=EntryStatus.DONE,
                    error="",
                    media_path=str(file_path),
                    **result,
                )
                self.view.on_entry_changed(child.id)
                # A watched folder is never done, so each of its files is notified
                if self._is_watch_job(job):
                    self.view.on_transcription_ready(child)
        elif entry := self._store.get(job.entry_id):
            self._store.update(entry, media_path=str(file_path), **result)
            if job.is_mic:
                self.view.on_mic_text(text or "")

    def on_file_failed(self, file_path: Path, error: str) -> None:
        if child := self._child_entry(file_path):
            self._store.update(child, status=EntryStatus.FAILED, error=error)
            self.view.on_entry_changed(child.id)
