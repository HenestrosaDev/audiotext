from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

import views.main_window.entry_dialogs as entry_dialogs
from models.history import EntryStatus, HistoryEntry
from utils.history_store import HistoryStore
from views.main_window.entry_dialogs import EntryDialogs


class Answers:
    """What the user types in the dialogs and answers to the confirmations."""

    def __init__(self) -> None:
        self.text: str | None = None
        self.is_confirmed = False
        self.dialog_args: tuple[Any, ...] = ()


@pytest.fixture
def answers(monkeypatch: pytest.MonkeyPatch) -> Answers:
    answers = Answers()

    class FakeTextDialog:
        def __init__(self, *args: Any, **_kwargs: Any) -> None:
            answers.dialog_args = args

        def get_input(self) -> str | None:
            return answers.text

    monkeypatch.setattr(entry_dialogs, "TextDialog", FakeTextDialog)
    monkeypatch.setattr(
        entry_dialogs.messagebox,
        "askyesno",
        lambda *_args, **_kwargs: answers.is_confirmed,
    )
    return answers


@pytest.fixture
def store(tmp_path: Path) -> HistoryStore:
    return HistoryStore(tmp_path / "history.json", tmp_path / "media")


@pytest.fixture
def history() -> MagicMock:
    return MagicMock()


@pytest.fixture
def jobs() -> MagicMock:
    return MagicMock()


@pytest.fixture
def dialogs(
    store: HistoryStore, history: MagicMock, jobs: MagicMock, answers: Answers
) -> EntryDialogs:
    return EntryDialogs(MagicMock(), store, history, jobs)


def add(store: HistoryStore, **kwargs: Any) -> HistoryEntry:
    values: dict[str, Any] = {
        "kind": "File",
        "source": "/a.mp3",
        "title": "Talk",
        "status": EntryStatus.DONE,
    }
    return store.add(HistoryEntry(**(values | kwargs)))


def test_an_entry_is_renamed_with_the_typed_name(
    dialogs: EntryDialogs, store: HistoryStore, history: MagicMock, answers: Answers
) -> None:
    entry = add(store)

    # Cancelled
    dialogs.rename_entry(entry.id)
    history.rename_entry.assert_not_called()

    answers.text = "Meeting"
    dialogs.rename_entry(entry.id)
    history.rename_entry.assert_called_once_with(entry.id, "Meeting")
    # The dialog starts from the current name
    assert answers.dialog_args[3] == "Talk"


def test_an_empty_note_or_tag_is_saved(
    dialogs: EntryDialogs, store: HistoryStore, history: MagicMock, answers: Answers
) -> None:
    entry = add(store, note="Old", tag="Work")
    answers.text = ""

    dialogs.edit_note(entry.id)
    dialogs.edit_tag(entry.id)

    history.set_note.assert_called_once_with(entry.id, "")
    history.set_tag.assert_called_once_with(entry.id, "")


def test_a_note_is_only_deleted_if_confirmed(
    dialogs: EntryDialogs, store: HistoryStore, history: MagicMock, answers: Answers
) -> None:
    entry = add(store, note="Old")

    dialogs.delete_note(entry.id)
    history.set_note.assert_not_called()

    answers.is_confirmed = True
    dialogs.delete_note(entry.id)
    history.set_note.assert_called_once_with(entry.id, "")


def test_an_entry_in_progress_is_cancelled_before_deleting_it(
    dialogs: EntryDialogs,
    store: HistoryStore,
    history: MagicMock,
    jobs: MagicMock,
    answers: Answers,
) -> None:
    done = add(store)
    queued = add(store, status=EntryStatus.QUEUED)

    dialogs.delete_entry(queued.id)
    history.delete_entry.assert_not_called()

    answers.is_confirmed = True
    dialogs.delete_entry(done.id)
    dialogs.delete_entry(queued.id)

    jobs.cancel_entry.assert_called_once_with(queued.id)
    assert [call.args for call in history.delete_entry.call_args_list] == [
        (done.id,),
        (queued.id,),
    ]


def test_an_entry_is_moved_to_a_new_group(
    dialogs: EntryDialogs, store: HistoryStore, history: MagicMock, answers: Answers
) -> None:
    entry = add(store)

    # Cancelled
    dialogs.move_to_new_group(entry.id)
    history.create_group.assert_not_called()
    history.move_to_group.assert_not_called()

    answers.text = "Work"
    history.create_group.return_value = "group-id"
    dialogs.move_to_new_group(entry.id)
    history.create_group.assert_called_once_with("Work")
    history.move_to_group.assert_called_once_with(entry.id, "group-id")


def test_a_group_is_renamed_and_deleted(
    dialogs: EntryDialogs, store: HistoryStore, history: MagicMock, answers: Answers
) -> None:
    group = store.add_group("Work")

    answers.text = "Home"
    dialogs.rename_group(group.id)
    history.rename_group.assert_called_once_with(group.id, "Home")

    dialogs.delete_group(group.id)
    history.delete_group.assert_not_called()
    answers.is_confirmed = True
    dialogs.delete_group(group.id)
    history.delete_group.assert_called_once_with(group.id)


def test_nothing_is_asked_for_a_missing_entry(
    dialogs: EntryDialogs, history: MagicMock, answers: Answers
) -> None:
    answers.text = "Meeting"
    answers.is_confirmed = True

    dialogs.rename_entry("missing")
    dialogs.delete_entry("missing")
    dialogs.rename_group("missing")

    assert answers.dialog_args == ()
    assert not history.method_calls
