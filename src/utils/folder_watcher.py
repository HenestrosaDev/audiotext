import fnmatch
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from utils import constants as c

logger = logging.getLogger(__name__)

# Size and modification time of a file, to detect whether it's still being written
FileSignature = tuple[int, int]


@dataclass(frozen=True)
class FileFilter:
    """Which of the supported files of a folder are transcribed."""

    include_subfolders: bool = True
    # Patterns of the names or the paths (relative to the folder) of the files to
    # skip, e.g. "*.wav" or "drafts/*", ignoring the case
    exclude_patterns: tuple[str, ...] = ()

    def is_included(self, dir_path: Path, file_path: Path) -> bool:
        relative = file_path.relative_to(dir_path)
        # Hidden files and folders, e.g. the "._" files that macOS creates next
        # to each file on the drives that don't support its metadata
        if any(part.startswith(".") for part in relative.parts):
            return False
        if not self.include_subfolders and len(relative.parts) > 1:
            return False

        name = file_path.name.casefold()
        path = relative.as_posix().casefold()
        return not any(
            fnmatch.fnmatchcase(name, pattern) or fnmatch.fnmatchcase(path, pattern)
            for pattern in (pattern.casefold() for pattern in self.exclude_patterns)
        )


def split_patterns(patterns: str) -> tuple[str, ...]:
    """The patterns of a text, separated by commas (e.g. "*.wav, drafts/*")."""
    return tuple(pattern.strip() for pattern in patterns.split(",") if pattern.strip())


def list_supported_files(
    dir_path: Path, file_filter: FileFilter | None = None
) -> list[Path]:
    """
    Lists the supported audio and video files of a directory and, unless the
    filter leaves them out, of its subdirectories. Hidden files are left out.

    :param dir_path: The directory to search.
    :param file_filter: Which files to list. By default, all of them.
    :return: A sorted list of the paths of the supported files.
    """
    file_filter = file_filter or FileFilter()
    files = (
        dir_path.rglob("*") if file_filter.include_subfolders else dir_path.glob("*")
    )
    return [
        file_path
        for file_path in sorted(files)
        if file_path.suffix.lower() in c.SUPPORTED_FILE_EXTENSIONS
        and file_filter.is_included(dir_path, file_path)
        and file_path.is_file()
    ]


class FolderWatcher:
    """
    Detects the supported files added to a directory (and its subdirectories)
    since the watcher was created, and the ones changed since (e.g. a recording
    replaced by another one with the same name), by scanning it each time `poll`
    is called.

    A file is only reported once its size and modification time are the same in
    two consecutive scans, so files that are still being copied or recorded are
    not transcribed until they're complete. Each file is reported once, and again
    each time it changes.

    Scanning is used instead of file system events because it works the same on
    every platform and on network drives.
    """

    def __init__(
        self,
        dir_path: Path,
        known_files: dict[Path, FileSignature] | None = None,
        file_filter: FileFilter | None = None,
    ) -> None:
        """
        :param dir_path: The directory to watch. The files it already contains are
                         ignored.
        :param known_files: The files already seen, with their signatures, e.g.
                            by a watcher that was paused. If None, the ones the
                            directory contains.
        :param file_filter: Which files to watch. By default, all of them.
        """
        self.dir_path = dir_path
        self._file_filter = file_filter
        if known_files is None:
            known_files = {
                file_path: signature
                for file_path in list_supported_files(dir_path, file_filter)
                if (signature := self._get_signature(file_path))
            }
        self._known_files = dict(known_files)
        # New or changed files waiting for their size to stop changing
        self._pending_files: dict[Path, FileSignature] = {}
        # The files of the last scan that were already known, and have changed
        self.changed_files: set[Path] = set()

    @property
    def known_files(self) -> dict[Path, FileSignature]:
        """The files seen, with their signatures, to watch the folder later."""
        return dict(self._known_files)

    def forget(self, files: Iterable[Path]) -> None:
        """Reports the files again, as if they were new (e.g. if they weren't done)."""
        for file_path in files:
            self._known_files.pop(file_path, None)

    def poll(self) -> list[Path]:
        """
        Scans the directory.

        :return: The new and the changed files that are ready to be transcribed,
                 sorted. The changed ones are in `changed_files`.
        """
        ready_files = []
        self.changed_files = set()
        current_files = list_supported_files(self.dir_path, self._file_filter)

        for file_path in current_files:
            signature = self._get_signature(file_path)
            if signature is None:  # Removed while scanning
                continue
            known_signature = self._known_files.get(file_path)
            if known_signature == signature:
                continue

            is_stable = self._pending_files.get(file_path) == signature
            # Empty files are usually being created
            if is_stable and signature[0] > 0:
                del self._pending_files[file_path]
                self._known_files[file_path] = signature
                ready_files.append(file_path)
                if known_signature is not None:
                    self.changed_files.add(file_path)
            else:
                self._pending_files[file_path] = signature

        # Forget the files removed before they were ready
        current_files_set = set(current_files)
        for file_path in list(self._pending_files):
            if file_path not in current_files_set:
                del self._pending_files[file_path]

        return ready_files

    @staticmethod
    def _get_signature(file_path: Path) -> FileSignature | None:
        try:
            stat = file_path.stat()
        except OSError:
            return None

        return stat.st_size, stat.st_mtime_ns
