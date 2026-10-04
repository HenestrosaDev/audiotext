"""
The queue of transcriptions of the main window, and the interface that the
controller uses to report their progress.
"""

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, unquote, urlsplit

import utils.notifications as notifications
from models.config.config_whisperx import ConfigWhisperX
from models.history import EntryStatus, HistoryEntry
from models.transcript_segment import TranscriptSegment
from models.transcription_settings import TranscriptionSettings
from utils.config_manager import ConfigManager
from utils.enums import AudioSource
from utils.history_store import HistoryStore
from utils.i18n import _
from utils.validators import is_youtube_url
from views.history.formatting import format_full_date
from views.new_transcription.microphone_view import MicrophoneView, MicState

if TYPE_CHECKING:
    from controllers.main_controller import MainController
    from views.history.history_sidebar import HistorySidebar
    from views.new_transcription.new_transcription_view import NewTranscriptionView


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
    if source == AudioSource.MIC:
        return _("Recording · {date}").format(
            date=format_full_date(datetime.now().astimezone())
        )
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


class TranscriptionJobsMixin:
    """
    Keeps the queue of transcriptions waiting to be processed, starts them one
    after the other, and records their progress and results in the history.
    """

    # Provided by the main window
    _store: HistoryStore
    _controller: "MainController | None"
    sidebar: "HistorySidebar"
    _new_views: "dict[AudioSource, NewTranscriptionView]"
    _mic_view: MicrophoneView | None
    _entry_view: Any
    _entry_view_id: str | None
    select_entry: Callable[[str], None]
    show_status: Callable[..., None]
    _on_entry_changed: Callable[..., None]
    _refresh_entry_view: Callable[[str], None]

    def _init_jobs(self) -> None:
        self._job: Job | None = None
        self._queue: deque[str] = deque()
        # The entry created for the last recording, opened from the microphone view
        self._last_mic_entry_id: str | None = None

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

    def _start_transcription(
        self, source: AudioSource, value: str, settings: TranscriptionSettings
    ) -> None:
        """Adds a transcription from the steps of a new transcription."""
        entry = self._add_entry(source, value, settings)

        # The next transcription from this source starts from the first step
        if view := self._new_views.pop(source, None):
            view.destroy()

        self._queue.append(entry.id)
        self.sidebar.refresh()
        self.select_entry(entry.id)
        self._run_next()

    def _restart_entry(
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
            self.sidebar.refresh()
        else:
            self._store.update(
                entry,
                kind=self._entry_kind(source, settings).value,
                settings=settings.to_dict(),
                method=settings.method,
                status=EntryStatus.QUEUED,
                error="",
            )
            self._on_entry_changed(entry.id)

        self._queue.append(entry.id)
        self.select_entry(entry.id)
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
            self.show_status(_("The recording is no longer available."), is_error=True)
            return

        self._store.update(entry, status=EntryStatus.QUEUED, error="")
        self._queue.append(entry_id)
        self._on_entry_changed(entry_id)
        self.select_entry(entry_id)
        self._run_next()

    def cancel_entry(self, entry_id: str) -> None:
        entry = self._store.get(entry_id)
        if entry is None:
            return
        job = self._job

        if job and entry_id in (job.entry_id, *job.children.values()):
            if (
                job.is_mic
                and self._mic_view
                and self._mic_view.state == MicState.RECORDING
            ):
                self._stop_recording()
            job.is_cancel_requested = True
            if self._controller:
                self._controller.cancel_transcription()
        elif entry_id in self._queue:
            self._queue.remove(entry_id)
            self._store.update(entry, status=EntryStatus.CANCELLED)
            self._on_entry_changed(entry_id)
            self._refresh_queue_positions()

    def _run_next(self) -> None:
        if self._job is not None or not self._controller:
            return

        while self._queue:
            entry = self._store.get(self._queue.popleft())
            if entry is not None:
                break
        else:
            return

        settings = TranscriptionSettings.from_dict(entry.settings)
        ConfigManager.modify_value(
            ConfigWhisperX.Key.SECTION,
            ConfigWhisperX.Key.MODEL_SIZE,
            settings.model_size,
        )

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
        self._on_entry_changed(entry.id)
        self._refresh_queue_positions()
        self._controller.prepare_for_transcription(transcription)

    def _refresh_queue_positions(self) -> None:
        for entry_id in self._queue:
            self._refresh_progress(entry_id)

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
            self._on_entry_changed(entry.id)
            if entry.is_folder:
                self.sidebar.refresh()

            if job.is_mic and self._mic_view:
                if final_status == EntryStatus.DONE:
                    self._mic_view.set_state(MicState.DONE)
                else:
                    self._mic_view.set_state(
                        MicState.FAILED,
                        job.error or _("The transcription was cancelled."),
                    )

            if final_status == EntryStatus.FAILED:
                self.show_status(f"{entry.title}: {job.error}", is_error=True)
            elif status_message:
                self.show_status(f"{entry.title}: {status_message}")

            # A folder that stops being watched is done, but nothing new is ready
            if final_status == EntryStatus.DONE and not job.is_cancel_requested:
                self._notify_ready(entry)

        self._run_next()

    def _is_watch_job(self, job: Job) -> bool:
        entry = self._store.get(job.entry_id)
        return entry is not None and entry.kind == AudioSource.WATCH.value

    @staticmethod
    def _notify_ready(entry: HistoryEntry) -> None:
        if ConfigManager.get_config_system().notify_when_done:
            notifications.notify(_("Transcription ready"), entry.title)

    # MICROPHONE

    def _start_recording(
        self, settings: TranscriptionSettings, device_index: int | None
    ) -> None:
        if self.is_busy() or not self._controller or not self._mic_view:
            return

        title = default_title(AudioSource.MIC, "")
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
        self._last_mic_entry_id = entry.id

        self._job = Job(
            entry_id=entry.id,
            is_folder=False,
            is_mic=True,
            progress_message=_("Recording…"),
        )
        self.sidebar.refresh()
        self._mic_view.set_state(MicState.RECORDING)
        self._controller.prepare_for_transcription(
            settings.to_transcription(
                AudioSource.MIC,
                "",
                media_path=media_path,
                mic_device_index=device_index,
            )
        )

    def _open_last_recording(self) -> None:
        if self._last_mic_entry_id:
            self.select_entry(self._last_mic_entry_id)

    def _stop_recording(self) -> None:
        if self._controller:
            self._controller.stop_recording_from_mic()

    # CONTROLLER INTERFACE

    def on_processed_transcription(self, status: str | None = None) -> None:
        self._finish_job(status)

    def on_transcription_progress(self, message: str, fraction: float | None) -> None:
        job = self._job
        if job is None:
            return
        job.progress_message, job.progress_fraction = message, fraction
        self._refresh_progress(job.entry_id)
        if job.is_mic and self._mic_view:
            self._mic_view.show_progress(message)

    def _refresh_progress(self, entry_id: str) -> None:
        self.sidebar.update_progress(entry_id)
        if self._entry_view_id == entry_id and hasattr(
            self._entry_view, "update_progress"
        ):
            self._entry_view.update_progress()

    def on_recording_progress(self, elapsed_seconds: float, level: float) -> None:
        if self._mic_view:
            self._mic_view.on_recording_progress(elapsed_seconds, level)

    def on_live_text(self, text: str) -> None:
        if self._mic_view:
            self._mic_view.show_live_text(text)

    def on_live_status(self, message: str) -> None:
        if self._mic_view:
            self._mic_view.show_live_status(message)

    def on_stop_recording_from_mic(self) -> None:
        if self._mic_view and self._mic_view.state == MicState.RECORDING:
            self._mic_view.set_state(
                MicState.TRANSCRIBING, _("Processing the recording…")
            )

    def on_transcription_saved(self, folder: Path) -> None:
        if self._job and (entry := self._store.get(self._job.entry_id)):
            self._store.update(entry, output_dir=str(folder))
        else:
            self.show_status(_("Saved in {folder}.").format(folder=folder))

    def show_error(self, message: str) -> None:
        if self._job is not None:
            self._job.error = message
        else:
            self.show_status(message, is_error=True)

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
            self.sidebar.refresh()
            self._refresh_entry_view(self._job.entry_id)

    def on_file_started(self, file_path: Path) -> None:
        is_new = self._job is not None and str(file_path) not in self._job.children
        child = self._child_entry(file_path, EntryStatus.PROCESSING)
        if child is None or self._job is None:
            return
        self._job.current_child_id = child.id
        self._store.update(child, status=EntryStatus.PROCESSING, error="")
        if is_new:
            self.sidebar.refresh()
        self._on_entry_changed(child.id)

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
                self._on_entry_changed(child.id)
                # A watched folder is never done, so each of its files is notified
                if self._is_watch_job(job):
                    self._notify_ready(child)
        elif entry := self._store.get(job.entry_id):
            self._store.update(entry, media_path=str(file_path), **result)
            if job.is_mic and self._mic_view:
                self._mic_view.show_text(text or "")

    def on_file_failed(self, file_path: Path, error: str) -> None:
        if child := self._child_entry(file_path):
            self._store.update(child, status=EntryStatus.FAILED, error=error)
            self._on_entry_changed(child.id)
