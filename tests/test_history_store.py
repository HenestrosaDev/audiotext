import json
from pathlib import Path

import pytest

from models.history import EntryStatus, HistoryEntry
from models.transcript_segment import TranscriptSegment, TranscriptWord
from utils.history_store import HistoryStore, sanitize_file_name


@pytest.fixture
def store(tmp_path: Path) -> HistoryStore:
    return HistoryStore(tmp_path / "history.json", tmp_path / "media")


def make_entry(**kwargs: object) -> HistoryEntry:
    defaults: dict[str, object] = {"kind": "File", "source": "/a.mp3", "title": "a"}
    return HistoryEntry(**(defaults | kwargs))  # type: ignore[arg-type]


def reload(store: HistoryStore) -> HistoryStore:
    return HistoryStore(store.file_path, store.media_dir)


def test_entries_survive_a_reload(store: HistoryStore) -> None:
    segments = [
        TranscriptSegment(
            0.0, 1.5, "Hello there", "SPEAKER_00", (TranscriptWord(0.0, 0.5, "Hello"),)
        )
    ]
    entry = store.add(
        make_entry(
            status=EntryStatus.DONE,
            text="Hello there",
            segments=segments,
            note="Call notes",
            tag="Work",
            is_pinned=True,
        )
    )

    loaded = reload(store).get(entry.id)

    assert loaded == entry


def test_active_entries_are_interrupted_on_reload(store: HistoryStore) -> None:
    processing = store.add(make_entry(status=EntryStatus.PROCESSING))
    watching = store.add(make_entry(status=EntryStatus.WATCHING))
    done = store.add(make_entry(status=EntryStatus.DONE))

    loaded = reload(store)

    assert loaded.get(processing.id).status == EntryStatus.INTERRUPTED  # type: ignore[union-attr]
    assert loaded.get(watching.id).status == EntryStatus.INTERRUPTED  # type: ignore[union-attr]
    assert loaded.get(done.id).status == EntryStatus.DONE  # type: ignore[union-attr]


def test_top_level_entries_are_sorted_newest_first(store: HistoryStore) -> None:
    old = store.add(make_entry(created_at="2026-01-01T10:00:00+00:00"))
    new = store.add(make_entry(created_at="2026-05-01T10:00:00+00:00"))
    folder = store.add(make_entry(kind="Directory", source="/music"))
    store.add(make_entry(parent_id=folder.id, created_at="2027-01-01T10:00:00+00:00"))

    assert [e.id for e in store.top_level()] == [folder.id, new.id, old.id]


def test_children_are_sorted_by_path(store: HistoryStore) -> None:
    folder = store.add(make_entry(kind="Directory", source="/music"))
    b = store.add(make_entry(parent_id=folder.id, source="/music/b.mp3"))
    a = store.add(make_entry(parent_id=folder.id, source="/music/A.mp3"))

    assert store.children(folder.id) == [a, b]
    assert store.find_child(folder.id, "/music/b.mp3") == b


def test_deleting_a_folder_deletes_its_children_and_media(
    store: HistoryStore, tmp_path: Path
) -> None:
    folder = store.add(make_entry(kind="Directory", source=str(tmp_path)))
    child = store.add(make_entry(parent_id=folder.id))
    recording = store.add(make_entry(kind="Microphone", source=""))
    media_path = store.new_media_path(recording.id, "Recording.wav")
    media_path.parent.mkdir(parents=True)
    media_path.touch()
    user_file = tmp_path / "user.mp3"
    user_file.touch()
    store.update(recording, media_path=str(media_path))
    store.update(child, media_path=str(user_file))

    assert set(store.delete(folder.id)) == {folder.id, child.id}
    store.delete(recording.id)

    assert store.entries == []
    assert not media_path.parent.exists()
    assert user_file.exists()  # Files of the user are never removed


def test_deleting_a_group_keeps_its_entries(store: HistoryStore) -> None:
    group = store.add_group("  Interviews ")
    entry = store.add(make_entry(group_id=group.id))

    assert group.name == "Interviews"

    store.rename_group(group.id, "Calls")
    assert reload(store).get_group(group.id).name == "Calls"  # type: ignore[union-attr]

    store.delete_group(group.id)

    loaded = reload(store)
    assert loaded.groups == []
    assert loaded.get(entry.id).group_id is None  # type: ignore[union-attr]


def test_update_rejects_unknown_attributes(store: HistoryStore) -> None:
    entry = store.add(make_entry())

    with pytest.raises(AttributeError):
        store.update(entry, unknown=1)


def test_corrupted_file_is_kept_aside(store: HistoryStore) -> None:
    store.file_path.write_text("{not json", encoding="utf-8")

    loaded = reload(store)

    assert loaded.entries == []
    assert store.file_path.with_suffix(".corrupted.json").exists()


def test_invalid_entries_are_skipped(store: HistoryStore) -> None:
    valid = make_entry().to_dict()
    data = {"version": 1, "groups": [], "entries": [{"title": "no kind"}, valid]}
    store.file_path.write_text(json.dumps(data), encoding="utf-8")

    assert [e.id for e in reload(store).entries] == [valid["id"]]


def test_tags_are_unique_and_sorted(store: HistoryStore) -> None:
    for tag in ("work", "Home", "", "work"):
        store.add(make_entry(tag=tag))

    assert store.tags() == ["Home", "work"]


@pytest.mark.parametrize(
    ("query", "expected"),
    [("interview", True), ("BUDGET", True), ("notes", True), ("missing", False)],
)
def test_entries_match_the_title_text_and_note(query: str, expected: bool) -> None:
    entry = make_entry(title="Interview", text="The budget", note="My notes")

    assert entry.matches(query) is expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Recording 03/10/2026 14:05", "Recording 03-10-2026 14-05"),
        ("https://youtu.be/abc?x=1", "https-youtu.be-abc-x=1"),
        ("...", "media"),
    ],
)
def test_sanitize_file_name(name: str, expected: str) -> None:
    assert sanitize_file_name(name) == expected


def test_model_name_of_each_method() -> None:
    def entry(method: str, settings: dict[str, str]) -> HistoryEntry:
        return HistoryEntry(
            kind="File", source="a.mp3", title="a", method=method, settings=settings
        )

    assert entry("WhisperX", {"model_size": "tiny"}).model_name == "tiny"
    assert entry("Whisper API", {"openai_model": "gpt-transcribe"}).model_name == (
        "gpt-transcribe"
    )
    # Older entries didn't store the model of the OpenAI API
    assert entry("Whisper API", {}).model_name == "whisper-1"
    assert entry("Google API", {"model_size": "tiny"}).model_name is None


def test_the_summary_survives_a_reload(store: HistoryStore) -> None:
    summary = {"summary": "A talk.", "key_points": ["One"], "chapters": [[0, "Intro"]]}
    entry = store.add(HistoryEntry(kind="File", source="a.mp3", title="a"))
    store.update(entry, summary=summary)

    reloaded = HistoryStore(store.file_path, store.media_dir).get(entry.id)

    assert reloaded is not None
    assert reloaded.summary == summary
