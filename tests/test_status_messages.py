from pathlib import Path
from typing import Any
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


def test_the_files_of_a_watched_folder_are_notified_together(
    messages: StatusMessages, display: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    import utils.notifications as notifications
    from utils.config_manager import ConfigManager

    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(notifications, "notify", lambda *args: sent.append(args))
    monkeypatch.setattr(
        ConfigManager,
        "get_config_system",
        lambda: MagicMock(notify_when_done=True),
    )
    scheduled: list[Any] = []
    display.after.side_effect = lambda _ms, callback: scheduled.append(callback) or "id"

    messages.on_transcription_ready(make_entry(title="a.mp3"), "inbox")
    messages.on_transcription_ready(make_entry(title="b.mp3"), "inbox")
    # The previous wait is replaced, so they're notified once
    display.after_cancel.assert_called_once_with("id")
    scheduled[-1]()
    messages.on_transcription_ready(make_entry(title="c.mp3"), "inbox")
    scheduled[-1]()
    messages.on_transcription_ready(make_entry(title="Talk"))

    assert sent == [
        ("Transcription ready", "2 files transcribed in inbox"),
        ("Transcription ready", "c.mp3"),
        ("Transcription ready", "Talk"),
    ]
