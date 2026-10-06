from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from controllers.history_controller import HistoryController
from handlers.translation_handler import MANUAL
from models.history import EntryStatus, HistoryEntry
from models.transcript_segment import TranscriptSegment
from models.translation import TranscriptTranslation
from tests.conftest import FakeSummarizer, FakeTranslator
from utils.history_store import HistoryStore

SEGMENTS = [
    TranscriptSegment(0.0, 1.0, "Hello", "SPEAKER_00"),
    TranscriptSegment(1.5, 3.0, "Bye", "SPEAKER_01"),
]


@pytest.fixture
def store(tmp_path: Path) -> HistoryStore:
    return HistoryStore(tmp_path / "history.json", tmp_path / "media")


@pytest.fixture
def view() -> MagicMock:
    view = MagicMock()
    view.run_on_ui_thread.side_effect = lambda callback, *args: callback(*args)
    return view


@pytest.fixture
def summarizer() -> FakeSummarizer:
    return FakeSummarizer()


@pytest.fixture
def translator() -> FakeTranslator:
    return FakeTranslator()


@pytest.fixture
def tasks() -> list[Callable[[], None]]:
    """The tasks started in the background, run by `run_tasks`."""
    return []


@pytest.fixture
def history(
    store: HistoryStore,
    view: MagicMock,
    summarizer: FakeSummarizer,
    translator: FakeTranslator,
    tasks: list[Callable[[], None]],
) -> HistoryController:
    return HistoryController(store, view, summarizer, translator, tasks.append)


def run_tasks(tasks: list[Callable[[], None]]) -> None:
    while tasks:
        tasks.pop(0)()


def add(store: HistoryStore, **kwargs: Any) -> HistoryEntry:
    values: dict[str, Any] = {
        "kind": "File",
        "source": "/a.mp3",
        "title": "Talk",
        "status": EntryStatus.DONE,
        "text": "Hello\n\nBye",
        "segments": SEGMENTS,
    }
    return store.add(HistoryEntry(**(values | kwargs)))


def get(store: HistoryStore, entry_id: str | None) -> HistoryEntry:
    assert entry_id is not None
    entry = store.get(entry_id)
    assert entry is not None
    return entry


def test_a_note_is_only_saved_if_it_changes(
    history: HistoryController, store: HistoryStore, view: MagicMock
) -> None:
    entry = add(store, note="Old")

    history.set_note(entry.id, "Old")
    view.on_entry_changed.assert_not_called()

    history.set_note(entry.id, "New")
    assert get(store, entry.id).note == "New"
    view.on_entry_changed.assert_called_once_with(entry.id)


def test_a_summary_is_saved_and_announced(
    history: HistoryController,
    store: HistoryStore,
    view: MagicMock,
    summarizer: FakeSummarizer,
    tasks: list[Callable[[], None]],
) -> None:
    entry = add(store)

    history.summarize_entry(entry.id)
    # Only one summary of each entry is made at a time
    history.summarize_entry(entry.id)
    assert history.is_summarizing(entry.id)
    run_tasks(tasks)

    assert summarizer.texts == ["Hello\n\nBye"]
    assert get(store, entry.id).summary == summarizer.summary.to_dict()
    assert not history.is_summarizing(entry.id)
    view.on_summary_finished.assert_called_once_with(get(store, entry.id), None)


def test_a_failed_summary_keeps_its_error_until_retried(
    history: HistoryController,
    store: HistoryStore,
    view: MagicMock,
    summarizer: FakeSummarizer,
    tasks: list[Callable[[], None]],
) -> None:
    summarizer.error = RuntimeError("No credit")
    entry = add(store)

    history.summarize_entry(entry.id)
    run_tasks(tasks)

    assert "No credit" in history.get_summary_error(entry.id)
    view.on_summary_finished.assert_called_once_with(
        get(store, entry.id), history.get_summary_error(entry.id)
    )
    assert get(store, entry.id).summary == {}

    # The error is cleared when summarizing again, while the summary is made
    history.summarize_entry(entry.id)
    assert history.get_summary_error(entry.id) == ""
    assert history.is_summarizing(entry.id)


def test_a_translation_is_saved_and_announced(
    history: HistoryController,
    store: HistoryStore,
    view: MagicMock,
    translator: FakeTranslator,
    tasks: list[Callable[[], None]],
) -> None:
    entry = add(store)

    history.translate_entry(entry.id, "es", "deepl")
    assert history.is_translating(entry.id)
    run_tasks(tasks)

    assert translator.requests == [("es", "deepl")]
    assert get(store, entry.id).translation == translator.translation.to_dict()
    assert not history.is_translating(entry.id)
    view.on_translation_finished.assert_called_once_with(get(store, entry.id), None)


def test_a_failed_translation_keeps_its_error(
    history: HistoryController,
    store: HistoryStore,
    view: MagicMock,
    translator: FakeTranslator,
    tasks: list[Callable[[], None]],
) -> None:
    translator.error = OSError("No API key")
    entry = add(store)

    history.translate_entry(entry.id, "es", "deepl")
    run_tasks(tasks)

    assert "No API key" in history.get_translation_error(entry.id)
    assert get(store, entry.id).translation == {}
    view.on_translation_finished.assert_called_once_with(
        get(store, entry.id), history.get_translation_error(entry.id)
    )


def test_a_manual_translation_keeps_the_timestamps(
    history: HistoryController, store: HistoryStore
) -> None:
    entry = add(store)

    history.start_manual_translation(entry.id, "es")

    translation = TranscriptTranslation.from_dict(get(store, entry.id).translation)
    assert translation is not None
    assert translation.provider == MANUAL
    assert [(s.start, s.end, s.text) for s in translation.segments] == [
        (0.0, 1.0, ""),
        (1.5, 3.0, ""),
    ]

    history.remove_translation(entry.id)
    assert get(store, entry.id).translation == {}


def test_deleting_a_file_of_a_folder_refreshes_the_folder(
    history: HistoryController, store: HistoryStore, view: MagicMock
) -> None:
    folder = add(store, kind="Directory", source="/talks")
    child = add(store, parent_id=folder.id)

    history.delete_entry(child.id)

    assert store.get(child.id) is None
    view.refresh_entry_view.assert_called_once_with(folder.id)
    view.refresh_sidebar.assert_called_once()


def test_entries_are_moved_to_a_new_group(
    history: HistoryController, store: HistoryStore
) -> None:
    entry = add(store)

    group_id = history.create_group("Work")
    history.move_to_group(entry.id, group_id)
    history.rename_group(group_id, "Clients")

    group = store.get_group(group_id)
    assert get(store, entry.id).group_id == group_id
    assert group is not None and group.name == "Clients"

    history.delete_group(group_id)
    assert store.get_group(group_id) is None
    assert store.get(entry.id) is not None
