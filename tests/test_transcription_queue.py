from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from controllers.transcription_queue import (
    TranscriptionQueue,
    default_title,
    media_name_for_url,
)
from models.history import EntryStatus, HistoryEntry
from models.transcription_settings import TranscriptionSettings
from utils.config_manager import ConfigManager
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
    return TranscriptionQueue(store, view, create_runner=lambda _jobs: controller)


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


def test_an_entry_is_transcribed_again_with_its_own_model(
    jobs: TranscriptionQueue,
    store: HistoryStore,
    view: MagicMock,
    controller: MagicMock,
) -> None:
    jobs.start(AudioSource.FILE, "/a.mp3", TranscriptionSettings(model_size="tiny"))
    entry_id: str = view.select_entry.call_args.args[0]
    jobs.show_error("The file is empty.")
    jobs.on_processed_transcription(None)

    jobs.retry_entry(entry_id)

    transcription = controller.prepare_for_transcription.call_args.args[0]
    assert transcription.model_size == "tiny"
    # The model chosen for the next transcription doesn't change
    assert ConfigManager.get_config_whisperx().model_size == "large-v2"


def test_a_failed_transcription_shows_its_error(
    jobs: TranscriptionQueue, store: HistoryStore, view: MagicMock
) -> None:
    entry_id = start(jobs, view, "/a.mp3")

    jobs.show_error("The file is empty.")
    jobs.on_processed_transcription(None)

    entry = get(store, entry_id)
    assert entry.status == EntryStatus.FAILED
    assert entry.error == "The file is empty."
    view.on_transcription_finished.assert_called_once_with(entry, None)
    view.on_transcription_ready.assert_not_called()
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
    view.on_mic_finished.assert_called_once_with(entry)
    assert entry.status == EntryStatus.DONE
    view.on_transcription_ready.assert_called_once_with(entry)


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
    view.on_recording_unavailable.assert_called_once_with(entry)


def transcribe_folder(
    jobs: TranscriptionQueue,
    store: HistoryStore,
    settings: TranscriptionSettings | None = None,
    kind: AudioSource = AudioSource.DIRECTORY,
) -> tuple[HistoryEntry, list[HistoryEntry]]:
    """Transcribes a folder with two files, the second of which fails."""
    settings = settings or TranscriptionSettings()
    settings.watch = kind == AudioSource.WATCH
    jobs.start(AudioSource.DIRECTORY, "/talks", settings)
    folder = store.top_level()[0]
    files = [Path("/talks/a.mp3"), Path("/talks/b.mp3")]
    jobs.on_files_queued(files)
    jobs.on_file_started(files[0])
    jobs.on_file_transcribed(files[0], "Hello", [], "en")
    jobs.on_file_started(files[1])
    jobs.on_file_failed(files[1], "Broken")
    if kind == AudioSource.WATCH:
        jobs.cancel_entry(folder.id)
    jobs.on_processed_transcription(None)
    return folder, store.children(folder.id)


def last_transcription(controller: MagicMock) -> Any:
    return controller.prepare_for_transcription.call_args.args[0]


def test_a_folder_is_scanned_again_without_replacing_its_files(
    jobs: TranscriptionQueue, store: HistoryStore, controller: MagicMock
) -> None:
    folder, _children = transcribe_folder(jobs, store)

    jobs.retry_entry(folder.id)

    transcription = last_transcription(controller)
    assert transcription.should_scan_folder
    assert not transcription.should_overwrite
    assert transcription.retranscribed_files == []


def test_all_the_files_of_a_folder_are_transcribed_again(
    jobs: TranscriptionQueue, store: HistoryStore, controller: MagicMock
) -> None:
    folder, _children = transcribe_folder(jobs, store)

    jobs.retranscribe_folder(folder.id)

    assert last_transcription(controller).should_overwrite
    # Only for that run
    assert not get(store, folder.id).settings["overwrite"]
    jobs.on_processed_transcription(None)
    jobs.retry_entry(folder.id)
    assert not last_transcription(controller).should_overwrite


def test_the_failed_files_of_a_folder_are_transcribed_again(
    jobs: TranscriptionQueue, store: HistoryStore, controller: MagicMock
) -> None:
    folder, (done, failed) = transcribe_folder(jobs, store)

    jobs.retranscribe_files([failed.id])

    transcription = last_transcription(controller)
    assert not transcription.should_scan_folder
    assert transcription.retranscribed_files == [Path(failed.source)]
    assert get(store, folder.id).status == EntryStatus.PROCESSING
    assert get(store, failed.id).status == EntryStatus.QUEUED
    assert get(store, done.id).status == EntryStatus.DONE


def test_files_are_transcribed_again_while_their_folder_is(
    jobs: TranscriptionQueue, store: HistoryStore, controller: MagicMock
) -> None:
    jobs.start(AudioSource.DIRECTORY, "/talks", TranscriptionSettings())
    folder = store.top_level()[0]
    file_path = Path("/talks/a.mp3")
    jobs.on_files_queued([file_path])
    jobs.on_file_transcribed(file_path, "Hello", [], "en")
    child = store.children(folder.id)[0]

    # The controller takes it while it transcribes the folder
    controller.retranscribe_files.return_value = True
    jobs.retranscribe_files([child.id])

    controller.retranscribe_files.assert_called_once_with([file_path])
    assert get(store, child.id).status == EntryStatus.QUEUED
    assert controller.prepare_for_transcription.call_count == 1

    # Or the folder is transcribed again once it's done, with only that file
    controller.retranscribe_files.return_value = False
    jobs.retranscribe_files([child.id])
    jobs.on_processed_transcription(None)

    assert controller.prepare_for_transcription.call_count == 2
    transcription = last_transcription(controller)
    assert not transcription.should_scan_folder
    assert transcription.retranscribed_files == [file_path]
    assert get(store, child.id).status == EntryStatus.QUEUED
    assert get(store, folder.id).status == EntryStatus.PROCESSING


def test_cancelling_a_folder_cancels_the_files_to_transcribe_again(
    jobs: TranscriptionQueue, store: HistoryStore, controller: MagicMock
) -> None:
    jobs.start(AudioSource.DIRECTORY, "/talks", TranscriptionSettings())
    folder = store.top_level()[0]
    file_path = Path("/talks/a.mp3")
    jobs.on_files_queued([file_path])
    jobs.on_file_transcribed(file_path, "Hello", [], "en")
    controller.retranscribe_files.return_value = False
    jobs.retranscribe_files([store.children(folder.id)[0].id])

    jobs.cancel_entry(folder.id)
    jobs.on_processed_transcription(None)

    assert controller.prepare_for_transcription.call_count == 1
    assert get(store, folder.id).status == EntryStatus.CANCELLED
    assert store.children(folder.id)[0].status == EntryStatus.CANCELLED


def test_a_file_of_a_watched_folder_is_transcribed_without_watching_it(
    jobs: TranscriptionQueue, store: HistoryStore, controller: MagicMock
) -> None:
    folder, (done, _failed) = transcribe_folder(jobs, store, kind=AudioSource.WATCH)
    assert get(store, folder.id).status == EntryStatus.DONE

    jobs.retranscribe_files([done.id])

    assert last_transcription(controller).audio_source == AudioSource.DIRECTORY
    assert get(store, folder.id).status == EntryStatus.PROCESSING
    # Cancelling it doesn't stop a watch, so it's cancelled
    jobs.cancel_entry(folder.id)
    jobs.on_processed_transcription(None)
    assert get(store, folder.id).status == EntryStatus.CANCELLED

    jobs.retry_entry(folder.id)
    assert last_transcription(controller).audio_source == AudioSource.WATCH
    assert get(store, folder.id).status == EntryStatus.WATCHING


def test_the_files_keep_the_settings_they_were_transcribed_with(
    jobs: TranscriptionQueue, store: HistoryStore
) -> None:
    folder, (done, _failed) = transcribe_folder(
        jobs, store, TranscriptionSettings(model_size="small")
    )
    store.update(folder, settings=TranscriptionSettings(model_size="tiny").to_dict())

    assert get(store, done.id).settings["model_size"] == "small"


def test_the_folders_being_watched_when_closing_are_watched_again(
    store: HistoryStore, view: MagicMock, controller: MagicMock
) -> None:
    folder = store.add(
        HistoryEntry(
            kind=AudioSource.WATCH.value,
            source="/inbox",
            title="inbox",
            status=EntryStatus.WATCHING,
            settings=TranscriptionSettings(watch=True).to_dict(),
        )
    )
    files = {"a.mp3": EntryStatus.DONE, "b.mp3": EntryStatus.PROCESSING}
    for name, status in files.items():
        store.add(
            HistoryEntry(
                kind=AudioSource.FILE.value,
                source=f"/inbox/{name}",
                title=name,
                parent_id=folder.id,
                status=status,
            )
        )
    stopped = store.add(
        HistoryEntry(
            kind=AudioSource.WATCH.value,
            source="/stopped",
            title="stopped",
            status=EntryStatus.DONE,
        )
    )
    # The app is opened again
    store = HistoryStore(store.file_path, store.media_dir)
    jobs = TranscriptionQueue(store, view, create_runner=lambda _jobs: controller)

    jobs.resume_watches()

    transcription = last_transcription(controller)
    assert transcription.audio_source == AudioSource.WATCH
    # The file that was being transcribed is transcribed first
    assert transcription.retranscribed_files == [Path("/inbox/b.mp3")]
    assert get(store, folder.id).status == EntryStatus.WATCHING
    statuses = {child.title: child.status for child in store.children(folder.id)}
    assert statuses == {"a.mp3": EntryStatus.DONE, "b.mp3": EntryStatus.QUEUED}
    assert get(store, stopped.id).status == EntryStatus.DONE
    # Without leaving the page shown
    view.select_entry.assert_not_called()
    assert controller.prepare_for_transcription.call_count == 1


def watch_folder(jobs: TranscriptionQueue, store: HistoryStore) -> HistoryEntry:
    jobs.start(AudioSource.DIRECTORY, "/inbox", TranscriptionSettings(watch=True))
    folder = store.top_level()[0]
    assert folder.status == EntryStatus.WATCHING
    return folder


def test_a_watched_folder_is_paused_for_the_next_transcription(
    jobs: TranscriptionQueue, store: HistoryStore, controller: MagicMock
) -> None:
    folder = watch_folder(jobs, store)
    controller.pause_watch.return_value = True
    # It doesn't keep the others waiting
    assert not jobs.is_busy()

    other = start(jobs, MagicMock(select_entry=jobs.view.select_entry), "/talk.mp3")
    controller.pause_watch.assert_called_once_with(False)
    assert get(store, other).status == EntryStatus.QUEUED

    # It stops once the file it was transcribing is done
    known = {Path("/inbox/a.mp3"): (1, 1)}
    jobs.on_watch_paused(known, [], [])
    jobs.on_processed_transcription("")

    assert last_transcription(controller).path == Path("/talk.mp3")
    assert get(store, folder.id).status == EntryStatus.QUEUED
    jobs.on_processed_transcription(None)

    # Then it's watched again, from where it left off
    transcription = last_transcription(controller)
    assert transcription.audio_source == AudioSource.WATCH
    assert transcription.watch_known_files == known
    assert get(store, folder.id).status == EntryStatus.WATCHING


def test_a_watched_folder_is_paused_right_away_to_record(
    jobs: TranscriptionQueue,
    store: HistoryStore,
    controller: MagicMock,
    view: MagicMock,
) -> None:
    folder = watch_folder(jobs, store)
    file_path = Path("/inbox/a.mp3")
    jobs.on_file_started(file_path)
    controller.pause_watch.return_value = True

    assert jobs.start_recording("Recording", TranscriptionSettings(), None)
    controller.pause_watch.assert_called_once_with(True)
    # Not until the folder is paused
    assert controller.prepare_for_transcription.call_count == 1
    assert not jobs.start_recording("Another", TranscriptionSettings(), None)

    # The file being transcribed is transcribed again later
    jobs.on_watch_paused({}, [file_path], [])
    jobs.on_processed_transcription("")
    assert last_transcription(controller).audio_source == AudioSource.MIC
    assert store.children(folder.id)[0].status == EntryStatus.QUEUED

    jobs.on_processed_transcription(None)
    assert last_transcription(controller).audio_source == AudioSource.WATCH


def test_a_recording_stopped_before_it_starts_is_cancelled(
    jobs: TranscriptionQueue,
    store: HistoryStore,
    controller: MagicMock,
    view: MagicMock,
) -> None:
    watch_folder(jobs, store)
    controller.pause_watch.return_value = True
    jobs.start_recording("Recording", TranscriptionSettings(), None)

    jobs.stop_recording()

    recording = get(store, jobs.last_mic_entry_id)
    assert recording.status == EntryStatus.CANCELLED
    view.on_mic_finished.assert_called_once_with(recording)
    controller.stop_recording_from_mic.assert_not_called()
    # The folder goes on being watched once it's paused
    jobs.on_watch_paused({}, [], [])
    jobs.on_processed_transcription("")
    assert last_transcription(controller).audio_source == AudioSource.WATCH


def test_stopping_a_paused_watched_folder_is_done(
    jobs: TranscriptionQueue, store: HistoryStore, controller: MagicMock
) -> None:
    folder = watch_folder(jobs, store)
    controller.pause_watch.return_value = True
    start(jobs, jobs.view, "/talk.mp3")
    jobs.on_watch_paused({}, [], [])
    jobs.on_processed_transcription("")

    jobs.cancel_entry(folder.id)

    assert get(store, folder.id).status == EntryStatus.DONE


def test_the_files_skipped_without_an_entry_are_counted(
    jobs: TranscriptionQueue, store: HistoryStore
) -> None:
    jobs.start(AudioSource.DIRECTORY, "/talks", TranscriptionSettings())
    folder = store.top_level()[0]
    listed = Path("/talks/listed.mp3")
    jobs.on_files_queued([listed])

    jobs.on_files_skipped([listed, Path("/talks/old.mp3"), Path("/talks/other.mp3")])

    assert get(store, folder.id).skipped_files == 2


def test_a_watched_folder_waiting_for_files_is_idle(
    jobs: TranscriptionQueue, store: HistoryStore, controller: MagicMock
) -> None:
    folder = watch_folder(jobs, store)
    assert last_transcription(controller).should_wait_for_folder
    assert jobs.is_watch_idle(folder.id)
    assert jobs.get_last_watched_file(folder.id) is None

    file_path = Path("/inbox/a.mp3")
    jobs.on_file_started(file_path)
    assert not jobs.is_watch_idle(folder.id)
    jobs.on_file_transcribed(file_path, "Hello", [], "en")

    assert jobs.is_watch_idle(folder.id)
    last_file = jobs.get_last_watched_file(folder.id)
    assert last_file is not None and last_file[0] == "a.mp3"
