from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from models.history import EntryStatus, HistoryEntry
from views.main_window.status_messages import StatusMessages


@pytest.fixture
def display() -> MagicMock:
    return MagicMock()


@pytest.fixture
def messages(display: MagicMock) -> StatusMessages:
    return StatusMessages(display)


def make_entry(**kwargs: object) -> HistoryEntry:
    defaults: dict[str, object] = {"kind": "File", "source": "/a.mp3", "title": "Talk"}
    return HistoryEntry(**(defaults | kwargs))  # type: ignore[arg-type]


def test_a_failed_transcription_shows_its_error(
    messages: StatusMessages, display: MagicMock
) -> None:
    messages.on_transcription_finished(
        make_entry(status=EntryStatus.FAILED, error="Boom"), "Ignored"
    )
    messages.on_transcription_finished(make_entry(status=EntryStatus.DONE), "3 files")
    messages.on_transcription_finished(make_entry(status=EntryStatus.DONE), None)

    assert display.show_status.call_args_list == [
        call("Talk: Boom", is_error=True),
        call("Talk: 3 files"),
    ]


def test_a_moved_file_is_told_apart_from_a_failing_file_manager(
    messages: StatusMessages, display: MagicMock
) -> None:
    path = Path("/a.mp3")
    messages.on_reveal_failed(path, FileNotFoundError())
    messages.on_reveal_failed(path, OSError("No file manager"))

    assert display.show_status.call_args_list == [
        call(f"The file was moved or deleted: {path}", is_error=True),
        call("Could not open the file manager: No file manager", is_error=True),
    ]


def test_the_entry_is_refreshed_once_its_summary_or_translation_finishes(
    messages: StatusMessages, display: MagicMock
) -> None:
    entry = make_entry()

    messages.on_summary_finished(entry, None)
    messages.on_translation_finished(entry, "No key")

    assert display.show_status.call_args_list == [
        call("The summary of “Talk” is ready."),
        call("Could not translate “Talk”: No key", is_error=True),
    ]
    assert display.refresh_entry_view.call_args_list == [call(entry.id), call(entry.id)]
