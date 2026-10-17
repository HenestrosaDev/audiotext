from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
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
    # Whether it watches a folder, which never finishes on its own
    is_watch: bool = False
    # Whether the watch was asked to pause, so something else is transcribed
    is_pausing: bool = False
    # Whether a file of the folder is being transcribed, and the last one done
    is_transcribing_file: bool = False
    last_file_name: str | None = None
    last_file_at: datetime | None = None
    # The settings it transcribes with (see `TranscriptionSettings.to_dict`)
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunOptions:
    """
    How a folder is transcribed the next time it runs, which isn't kept in its
    settings, since it only applies to that run.
    """

    # Whether the files of the folder without a transcription are transcribed
    should_scan_folder: bool = True
    # Whether the files that already have a transcription are transcribed again
    should_overwrite: bool = False
    # Files of the folder transcribed again, replacing their transcriptions
    files: list[Path] = field(default_factory=list)
    # The files that a paused watch had seen, to go on from where it left off
    known_files: dict[Path, tuple[int, int]] | None = None

    @property
    def is_default(self) -> bool:
        return (
            self.should_scan_folder
            and not self.should_overwrite
            and not self.files
            and self.known_files is None
        )

    def merge(self, other: "RunOptions") -> "RunOptions":
        """The options of a run that does what both of them do."""
        return RunOptions(
            should_scan_folder=self.should_scan_folder or other.should_scan_folder,
            should_overwrite=self.should_overwrite or other.should_overwrite,
            files=[*self.files, *(f for f in other.files if f not in self.files)],
            known_files=self.known_files or other.known_files,
        )


@dataclass
class PendingRecording:
    """A recording that starts once the watched folder is paused."""

    entry_id: str
    transcription: Any


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
        # How the folders of the queue are transcribed, if not as usual
        self._run_options: dict[str, RunOptions] = {}
        self._pending_recording: PendingRecording | None = None
        # The entry created for the last recording, opened from the microphone view
        self.last_mic_entry_id: str | None = None
        self._runner = create_runner(self)

    def preload_model(self) -> None:
        if not self.is_busy():
            self._runner.preload_model()

    # QUEUE

    def is_busy(self) -> bool:
        """
        Whether something is being transcribed, so the next one waits. A watched
        folder isn't busy, since it's paused for the others.
        """
        job = self._job
        return job is not None and not job.is_watch

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

    def is_watch_idle(self, entry_id: str) -> bool:
        """Whether a watched folder is waiting for new files."""
        job = self._job
        return (
            job is not None
            and job.entry_id == entry_id
            and job.is_watch
            and not job.is_transcribing_file
        )

    def get_last_watched_file(self, entry_id: str) -> tuple[str, datetime] | None:
        """The name of the last file transcribed of a watched folder, and when."""
        job = self._job
        if job is None or job.entry_id != entry_id or not job.is_watch:
            return None
        if job.last_file_name and job.last_file_at:
            return job.last_file_name, job.last_file_at
        return None

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
        """
        Transcribes an entry again. A folder is scanned again: only its files
        without a transcription are transcribed (e.g. the ones added since).
        """
        entry = self._store.get(entry_id)
        if entry is None or entry.status.is_active or entry.parent_id:
            return
        if entry.kind == AudioSource.MIC.value and not (
            entry.media_path and Path(entry.media_path).is_file()
        ):
            self.view.on_recording_unavailable(entry)
            return

        self._enqueue(entry)

    def retranscribe_folder(self, entry_id: str) -> None:
        """Transcribes all the files of a folder again, replacing their files."""
        entry = self._store.get(entry_id)
        if entry is None or not entry.is_folder or entry.status.is_active:
            return
        self._enqueue(entry, RunOptions(should_overwrite=True))

    def retranscribe_files(self, entry_ids: list[str]) -> None:
        """
        Transcribes some files of a folder again, replacing their files, even
        while the folder is being transcribed or watched.

        :param entry_ids: The entries of the files, which belong to the same folder.
        """
        children = [
            child
            for entry_id in entry_ids
            if (child := self._store.get(entry_id)) and child.parent_id
        ]
        if not children:
            return
        parent = self._store.get(children[0].parent_id)
        if parent is None:
            return
        children = [child for child in children if child.parent_id == parent.id]
        files = [Path(child.source) for child in children]

        for child in children:
            self._store.update(child, status=EntryStatus.QUEUED, error="")

        job = self._job
        is_running = job is not None and job.entry_id == parent.id
        options = RunOptions(should_scan_folder=False, files=files)
        if is_running and self._runner.retranscribe_files(files):
            pass
        elif is_running or parent.id in self._queue:
            # Transcribed with the rest of the folder, if it's waiting, or once
            # it finishes. Only those files, unless it was going to be scanned
            base = (
                self._run_options.get(parent.id, RunOptions())
                if parent.id in self._queue
                else RunOptions(should_scan_folder=False)
            )
            self._run_options[parent.id] = base.merge(options)
            if parent.id not in self._queue:
                self._queue.append(parent.id)
        else:
            self._enqueue(parent, options)
            return

        self.view.refresh_sidebar()
        self.view.refresh_entry_view(parent.id)

    def resume_watches(self) -> None:
        """
        Watches again the folders that were being watched when the app was
        closed, since they weren't stopped. The files that were being transcribed
        then are transcribed first, as they're not new for the watcher anymore.
        """
        for entry_id in self._store.interrupted_watches:
            entry = self._store.get(entry_id)
            if entry is None or entry.status != EntryStatus.INTERRUPTED:
                continue
            interrupted = [
                child
                for child in self._store.children(entry_id)
                if child.status == EntryStatus.INTERRUPTED
            ]
            for child in interrupted:
                self._store.update(child, status=EntryStatus.QUEUED, error="")
            options = RunOptions(files=[Path(child.source) for child in interrupted])
            self._enqueue(entry, options, should_select=False)
        self._store.interrupted_watches.clear()

    def _enqueue(
        self,
        entry: HistoryEntry,
        options: RunOptions | None = None,
        should_select: bool = True,
    ) -> None:
        """:param should_select: Whether to show the entry."""
        if options is not None and not options.is_default:
            self._run_options[entry.id] = options
        else:
            self._run_options.pop(entry.id, None)
        self._store.update(entry, status=EntryStatus.QUEUED, error="")
        self._queue.append(entry.id)
        self.view.on_entry_changed(entry.id)
        if should_select:
            self.view.select_entry(entry.id)
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
            # Nor are the files to transcribe again once it finished
            if job.entry_id in self._queue:
                self._queue.remove(job.entry_id)
                self._run_options.pop(job.entry_id, None)
            self._runner.cancel_transcription()
        elif self._pending_recording and self._pending_recording.entry_id == entry_id:
            self.stop_recording()
        elif entry_id in self._queue:
            self._queue.remove(entry_id)
            self._run_options.pop(entry_id, None)
            # A watched folder waiting while it's paused is stopped, as usual
            is_watch = entry.kind == AudioSource.WATCH.value
            self._store.update(
                entry,
                status=EntryStatus.DONE if is_watch else EntryStatus.CANCELLED,
            )
            for child in self._store.children(entry_id):
                if child.status.is_active:
                    self._store.update(child, status=EntryStatus.CANCELLED)
            self.view.on_entry_changed(entry_id)
            self._refresh_queue_positions()

    def _run_next(self) -> None:
        if self._job is not None:
            self._pause_watch()
            return

        while self._queue:
            entry = self._store.get(self._queue.popleft())
            if entry is not None:
                break
        else:
            return

        settings = TranscriptionSettings.from_dict(entry.settings)
        options = self._run_options.pop(entry.id, RunOptions())

        kind = AudioSource(entry.kind)
        # A watched folder is only watched again if it's scanned as usual (with
        # the files transcribed again first, if any). Otherwise, the files
        # transcribed again are transcribed and it's done
        is_watch = (
            kind == AudioSource.WATCH
            and options.should_scan_folder
            and not options.should_overwrite
        )
        if kind == AudioSource.WATCH and not is_watch:
            kind = AudioSource.DIRECTORY
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
            transcription.should_overwrite = options.should_overwrite
            transcription.should_scan_folder = options.should_scan_folder
            transcription.retranscribed_files = list(options.files)
            transcription.watch_known_files = options.known_files
            transcription.should_wait_for_folder = True
            # They were transcribed before it was paused
            if options.known_files is not None:
                transcription.should_transcribe_existing = False

        self._job = Job(
            entry_id=entry.id,
            is_folder=entry.is_folder,
            is_mic=False,
            is_watch=is_watch,
            settings=settings.to_dict(),
        )
        status = EntryStatus.WATCHING if is_watch else EntryStatus.PROCESSING
        self._store.update(entry, status=status, error="", method=settings.method)
        self.view.on_entry_changed(entry.id)
        self._refresh_queue_positions()
        self._runner.prepare_for_transcription(transcription)

    def _pause_watch(self, is_urgent: bool = False) -> bool:
        """
        Pauses the folder being watched, if something else is waiting, so it's
        transcribed meanwhile. The folder is watched again after it.

        :return: Whether it's being paused.
        """
        job = self._job
        if job is None or not job.is_watch or job.is_cancel_requested:
            return False
        if job.is_pausing:
            return True
        has_others = any(entry_id != job.entry_id for entry_id in self._queue)
        if not (is_urgent or has_others) or not self._runner.pause_watch(is_urgent):
            return False
        job.is_pausing = True
        return True

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
                final_status = (
                    EntryStatus.DONE if job.is_watch else EntryStatus.CANCELLED
                )
            else:
                final_status = EntryStatus.DONE

            # Files that didn't finish (e.g. when cancelling) are marked as such,
            # unless they're transcribed again next
            is_queued_again = entry.id in self._queue
            for child in self._store.children(entry.id):
                if child.status.is_active and not (
                    is_queued_again and child.status == EntryStatus.QUEUED
                ):
                    self._store.update(child, status=EntryStatus.CANCELLED)

            if is_queued_again and final_status != EntryStatus.FAILED:
                final_status = EntryStatus.QUEUED
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

        if pending := self._pending_recording:
            self._pending_recording = None
            self._record(pending.entry_id, pending.transcription)
            return
        self._run_next()

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
        if self.is_busy() or self._pending_recording is not None:
            return False
        # A watched folder stops right away, and is watched again afterwards
        if self._job is not None and not self._pause_watch(is_urgent=True):
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
        transcription = settings.to_transcription(
            AudioSource.MIC,
            "",
            media_path=media_path,
            mic_device_index=device_index,
        )
        self.view.refresh_sidebar()

        if self._job is not None:
            self._pending_recording = PendingRecording(entry.id, transcription)
        else:
            self._record(entry.id, transcription)
        return True

    @property
    def is_recording_pending(self) -> bool:
        """Whether a recording waits for the watched folder to be paused."""
        return self._pending_recording is not None

    def _record(self, entry_id: str, transcription: Any) -> None:
        self._job = Job(entry_id=entry_id, is_folder=False, is_mic=True)
        self._runner.prepare_for_transcription(transcription)

    def stop_recording(self) -> None:
        if pending := self._pending_recording:
            # Stopped before it started, while the watched folder was paused
            self._pending_recording = None
            if entry := self._store.get(pending.entry_id):
                self._store.update(entry, status=EntryStatus.CANCELLED)
                self.view.on_entry_changed(entry.id)
                self.view.on_mic_finished(entry)
            return
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
        # If it couldn't be paused before (e.g. it hadn't started watching yet)
        if job.is_watch and not job.is_pausing:
            self._pause_watch()
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

    def on_files_skipped(self, files: list[Path]) -> None:
        """
        Counts the files of the folder that aren't in its history, since they
        already had a transcription, so the user knows why they aren't listed.
        """
        job = self._job
        entry = self._store.get(job.entry_id) if job else None
        if entry is None:
            return
        listed = {child.source for child in self._store.children(entry.id)}
        count = sum(str(file_path) not in listed for file_path in files)
        if count != entry.skipped_files:
            self._store.update(entry, skipped_files=count)
            self.view.refresh_entry_view(entry.id)

    def on_watch_paused(
        self,
        known_files: dict[Path, tuple[int, int]],
        unfinished: list[Path],
        retranscribed: list[Path],
    ) -> None:
        """Watches the folder again after what's waiting, from where it left off."""
        job = self._job
        if job is None or job.is_cancel_requested:
            return
        for file_path in [*unfinished, *retranscribed]:
            child = self._store.find_child(job.entry_id, str(file_path))
            if child is not None and child.status.is_active:
                self._store.update(child, status=EntryStatus.QUEUED, error="")
        self._run_options[job.entry_id] = self._run_options.get(
            job.entry_id, RunOptions()
        ).merge(RunOptions(files=list(retranscribed), known_files=known_files))
        if job.entry_id not in self._queue:
            self._queue.append(job.entry_id)

    def on_file_started(self, file_path: Path) -> None:
        is_new = self._job is not None and str(file_path) not in self._job.children
        child = self._child_entry(file_path, EntryStatus.PROCESSING)
        if child is None or self._job is None:
            return
        self._job.current_child_id = child.id
        self._job.is_transcribing_file = True
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
            # A summary or the translations of a previous transcription don't
            # apply to the new one
            "summary": {},
            "translations": {},
        }

        if job.is_folder:
            job.is_transcribing_file = False
            job.last_file_name = file_path.name
            job.last_file_at = datetime.now().astimezone()
            if child := self._child_entry(file_path):
                self._store.update(
                    child,
                    status=EntryStatus.DONE,
                    error="",
                    media_path=str(file_path),
                    # The settings it was transcribed with, which can differ from
                    # the ones of its folder once they're changed
                    settings=job.settings,
                    method=job.settings.get("method", child.method),
                    **result,
                )
                self.view.on_entry_changed(child.id)
                # A watched folder is never done, so each of its files is notified
                if job.is_watch:
                    self.view.on_transcription_ready(child)
        elif entry := self._store.get(job.entry_id):
            self._store.update(entry, media_path=str(file_path), **result)
            if job.is_mic:
                self.view.on_mic_text(text or "")

    def on_file_failed(self, file_path: Path, error: str) -> None:
        if self._job:
            self._job.is_transcribing_file = False
        if child := self._child_entry(file_path):
            self._store.update(child, status=EntryStatus.FAILED, error=error)
            self.view.on_entry_changed(child.id)
