from enum import Enum
from pathlib import Path


class FileStatus(Enum):
    """Status of each file when transcribing a directory, shown as a symbol."""

    PENDING = "•"
    IN_PROGRESS = "▶"
    DONE = "✓"
    FAILED = "✗"


class DirectoryReport:
    """
    Keeps the status of each file of a directory transcription and renders it as
    text, so the user can follow the progress of every file.
    """

    def __init__(self, dir_path: Path, files: list[Path]) -> None:
        self._dir_path = dir_path
        self._entries: dict[Path, tuple[FileStatus, str]] = {
            file: (FileStatus.PENDING, "") for file in files
        }

    def update(self, file: Path, status: FileStatus, detail: str = "") -> None:
        """Updates the status of a file, adding it to the report if it's new."""
        self._entries[file] = (status, detail)

    @property
    def total(self) -> int:
        return len(self._entries)

    @property
    def done(self) -> int:
        return sum(status == FileStatus.DONE for status, _ in self._entries.values())

    @property
    def failed(self) -> int:
        return sum(status == FileStatus.FAILED for status, _ in self._entries.values())

    def render(self, summary: str = "") -> str:
        lines = [summary, ""] if summary else []

        for file, (status, detail) in self._entries.items():
            line = f"{status.value} {file.relative_to(self._dir_path)}"
            lines.append(f"{line} — {detail}" if detail else line)

        return "\n".join(lines)
