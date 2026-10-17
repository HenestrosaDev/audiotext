import os
from pathlib import Path

from utils.folder_watcher import (
    FileFilter,
    FolderWatcher,
    list_supported_files,
    split_patterns,
)


def write(path: Path, content: bytes = b"audio") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_lists_supported_files_recursively(tmp_path: Path) -> None:
    write(tmp_path / "b.mp3")
    write(tmp_path / "sub" / "a.MP4")
    write(tmp_path / "notes.txt")

    assert list_supported_files(tmp_path) == [
        tmp_path / "b.mp3",
        tmp_path / "sub" / "a.MP4",
    ]


def test_ignores_the_files_that_already_exist(tmp_path: Path) -> None:
    write(tmp_path / "old.mp3")
    watcher = FolderWatcher(tmp_path)

    assert watcher.poll() == []
    assert watcher.poll() == []


def test_reports_a_new_file_once_its_size_is_stable(tmp_path: Path) -> None:
    watcher = FolderWatcher(tmp_path)
    new_file = write(tmp_path / "sub" / "new.wav")

    # The first scan sees the file, the second one confirms it's complete
    assert watcher.poll() == []
    assert watcher.poll() == [new_file]
    # Each file is reported only once
    assert watcher.poll() == []


def test_waits_while_the_file_is_being_written(tmp_path: Path) -> None:
    watcher = FolderWatcher(tmp_path)
    new_file = write(tmp_path / "new.wav", b"a")
    assert watcher.poll() == []

    write(new_file, b"a longer content")
    assert watcher.poll() == []

    assert watcher.poll() == [new_file]


def test_waits_while_the_file_is_empty(tmp_path: Path) -> None:
    watcher = FolderWatcher(tmp_path)
    new_file = write(tmp_path / "new.wav", b"")

    assert watcher.poll() == []
    assert watcher.poll() == []

    write(new_file)
    os.utime(new_file, ns=(1, 1))
    assert watcher.poll() == []
    assert watcher.poll() == [new_file]


def test_ignores_unsupported_and_removed_files(tmp_path: Path) -> None:
    watcher = FolderWatcher(tmp_path)
    write(tmp_path / "transcription.txt")
    removed_file = write(tmp_path / "removed.mp3")

    assert watcher.poll() == []
    removed_file.unlink()
    assert watcher.poll() == []


def test_hidden_files_are_left_out(tmp_path: Path) -> None:
    write(tmp_path / "talk.mp3")
    # Created by macOS on the drives that don't keep its metadata
    write(tmp_path / "._talk.mp3")
    write(tmp_path / ".cache" / "clip.mp3")

    assert list_supported_files(tmp_path) == [tmp_path / "talk.mp3"]


def test_the_files_are_filtered(tmp_path: Path) -> None:
    write(tmp_path / "talk.mp3")
    write(tmp_path / "raw.WAV")
    write(tmp_path / "drafts" / "take.mp3")
    write(tmp_path / "sub" / "clip.mp3")

    assert list_supported_files(tmp_path, FileFilter(include_subfolders=False)) == [
        tmp_path / "raw.WAV",
        tmp_path / "talk.mp3",
    ]
    patterns = split_patterns(" *.wav, drafts/* ,")
    assert patterns == ("*.wav", "drafts/*")
    assert list_supported_files(tmp_path, FileFilter(exclude_patterns=patterns)) == [
        tmp_path / "sub" / "clip.mp3",
        tmp_path / "talk.mp3",
    ]


def test_reports_a_file_again_once_it_changes(tmp_path: Path) -> None:
    old = write(tmp_path / "old.mp3")
    watcher = FolderWatcher(tmp_path)

    write(old, b"another recording")
    assert watcher.poll() == []
    assert watcher.poll() == [old]
    assert watcher.changed_files == {old}
    assert watcher.poll() == []


def test_goes_on_from_the_files_another_watcher_saw(tmp_path: Path) -> None:
    seen = write(tmp_path / "seen.mp3")
    watcher = FolderWatcher(tmp_path)
    added = write(tmp_path / "added.mp3")
    unfinished = write(tmp_path / "unfinished.mp3")
    watcher.poll()
    watcher.poll()
    # It wasn't transcribed before pausing, so it's reported again
    watcher.forget([unfinished])

    resumed = FolderWatcher(tmp_path, watcher.known_files)
    assert set(resumed.known_files) == {seen, added}
    assert resumed.poll() == []
    assert resumed.poll() == [unfinished]
    assert resumed.changed_files == set()
