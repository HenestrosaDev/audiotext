import os
from pathlib import Path

from utils.folder_watcher import FolderWatcher, list_supported_files


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
