from pathlib import Path
from unittest.mock import MagicMock

import pytest

from controllers.transcription_queue import (
    TranscriptionQueue,
    default_title,
    media_name_for_url,
)
from models.history import EntryStatus, HistoryEntry
from models.transcription_settings import TranscriptionSettings
from utils.enums import AudioSource
from utils.history_store import HistoryStore


@pytest.fixture
def store(tmp_path: Path) -> HistoryStore:
    return HistoryStore(tmp_path / "history.json", tmp_path / "media")


@pytest.fixture
def view() -> MagicMock:
    view = MagicMock()
    view.is_recording.return_value = False
    return view


@pytest.fixture
def controller() -> MagicMock:
    return MagicMock()


@pytest.fixture
def jobs(
    store: HistoryStore, view: MagicMock, controller: MagicMock
) -> TranscriptionQueue:
    jobs = TranscriptionQueue(store, view)
    jobs.set_controller(controller)
    return jobs


def start(jobs: TranscriptionQueue, view: MagicMock, value: str) -> str:
    jobs.start(AudioSource.FILE, value, TranscriptionSettings())
    entry_id: str = view.select_entry.call_args.args[0]
    return entry_id


def get(store: HistoryStore, entry_id: str | None) -> HistoryEntry:
    assert entry_id is not None
    entry = store.get(entry_id)
    assert entry is not None
    return entry


def test_the_titles_of_new_entries() -> None:
    assert default_title(AudioSource.FILE, "/talks/intro.mp3") == "intro.mp3"
    assert default_title(AudioSource.DIRECTORY, "/talks") == "talks"
    url = "https://www.youtube.com/watch?v=abc"
    assert default_title(AudioSource.YOUTUBE, url) == url
    assert media_name_for_url(url) == "YouTube abc"
    assert media_name_for_url("https://example.com/a/My%20talk.mp3") == "My talk"


def test_transcriptions_are_run_one_after_the_other(
    jobs: TranscriptionQueue,
    store: HistoryStore,
    view: MagicMock,
    controller: MagicMock,
) -> None:
    first = start(jobs, view, "/a.mp3")
    second = start(jobs, view, "/b.mp3")

    assert controller.prepare_for_transcription.call_count == 1
    assert get(store, first).status == EntryStatus.PROCESSING
    assert get(store, second).status == EntryStatus.QUEUED
    assert jobs.is_busy()
    assert jobs.get_queue_position(second) == 1

    jobs.on_transcription_progress("Transcribing…", 0.5)
    assert jobs.get_progress_message(first) == ("Transcribing…", 0.5)
    assert jobs.get_progress(second) is None

    jobs.on_file_transcribed(Path("/a.mp3"), "Hello", [], "en")
    jobs.on_processed_transcription("Done")

    entry = get(store, first)
    assert entry.status == EntryStatus.DONE
    assert entry.text == "Hello"
    assert get(store, second).status == EntryStatus.PROCESSING
    assert controller.prepare_for_transcription.call_count == 2


def test_a_failed_transcription_shows_its_error(
    jobs: TranscriptionQueue, store: HistoryStore, view: MagicMock
) -> None:
    entry_id = start(jobs, view, "/a.mp3")

    jobs.show_error("The file is empty.")
    jobs.on_processed_transcription(None)

    entry = get(store, entry_id)
    assert entry.status == EntryStatus.FAILED
    assert entry.error == "The file is empty."
    view.show_status.assert_called_with("a.mp3: The file is empty.", is_error=True)
    assert not jobs.is_busy()


def test_a_queued_transcription_is_cancelled_right_away(
    jobs: TranscriptionQueue,
    store: HistoryStore,
    view: MagicMock,
    controller: MagicMock,
) -> None:
    start(jobs, view, "/a.mp3")
    queued = start(jobs, view, "/b.mp3")

    jobs.cancel_entry(queued)

    assert get(store, queued).status == EntryStatus.CANCELLED
    assert jobs.get_queue_position(queued) is None
    controller.cancel_transcription.assert_not_called()


def test_the_unfinished_files_of_a_cancelled_folder_are_cancelled(
    jobs: TranscriptionQueue, store: HistoryStore, controller: MagicMock
) -> None:
    jobs.start(AudioSource.DIRECTORY, "/talks", TranscriptionSettings())
    folder = store.top_level()[0]
    files = [Path("/talks/a.mp3"), Path("/talks/b.mp3")]

    jobs.on_files_queued(files)
    jobs.on_file_started(files[0])
    jobs.on_file_transcribed(files[0], "Hello", [], "en")
    jobs.on_file_started(files[1])
    jobs.cancel_entry(folder.id)
    jobs.on_processed_transcription(None)

    controller.cancel_transcription.assert_called_once()
    children = {child.title: child.status for child in store.children(folder.id)}
    assert children == {"a.mp3": EntryStatus.DONE, "b.mp3": EntryStatus.CANCELLED}
    assert get(store, folder.id).status == EntryStatus.CANCELLED


def test_a_recording_is_only_started_when_nothing_is_transcribed(
    jobs: TranscriptionQueue, store: HistoryStore, view: MagicMock
) -> None:
    assert jobs.start_recording("Recording", TranscriptionSettings(), None)
    assert not jobs.start_recording("Another", TranscriptionSettings(), None)

    entry = get(store, jobs.last_mic_entry_id)
    assert entry.title == "Recording"
    assert entry.media_path and entry.media_path.endswith(".wav")

    jobs.on_file_transcribed(Path(entry.media_path), "Hi", [], "en")
    jobs.on_processed_transcription("Done")
    view.on_mic_text.assert_called_once_with("Hi")
    view.on_mic_finished.assert_called_once_with(None)


def test_a_recording_that_is_no_longer_kept_is_not_retried(
    jobs: TranscriptionQueue, store: HistoryStore, view: MagicMock
) -> None:
    entry = store.add(
        HistoryEntry(
            kind=AudioSource.MIC.value,
            source="",
            title="Recording",
            status=EntryStatus.FAILED,
            media_path="/missing.wav",
        )
    )

    jobs.retry_entry(entry.id)

    assert get(store, entry.id).status == EntryStatus.FAILED
    view.show_status.assert_called_once_with(
        "The recording is no longer available.", is_error=True
    )
