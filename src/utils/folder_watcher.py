import logging
from pathlib import Path

from utils import constants as c

logger = logging.getLogger(__name__)

# Size and modification time of a file, to detect whether it's still being written
FileSignature = tuple[int, int]


def list_supported_files(dir_path: Path) -> list[Path]:
    """
    Lists the supported audio and video files of a directory and its
    subdirectories.

    :param dir_path: The directory to search.
    :return: A sorted list of the paths of the supported files.
    """
    return [
        file_path
        for file_path in sorted(dir_path.rglob("*"))
        if file_path.is_file()
        and file_path.suffix.lower() in c.SUPPORTED_FILE_EXTENSIONS
    ]


class FolderWatcher:
    """
    Detects the supported files added to a directory (and its subdirectories)
    since the watcher was created, by scanning it each time `poll` is called.

    A new file is only reported once its size and modification time are the same
    in two consecutive scans, so files that are still being copied or recorded are
    not transcribed until they're complete. Each file is reported only once.

    Scanning is used instead of file system events because it works the same on
    every platform and on network drives.
    """

    def __init__(self, dir_path: Path) -> None:
        """
        :param dir_path: The directory to watch. The files it already contains are
                         ignored.
        """
        self.dir_path = dir_path
        self._known_files = set(list_supported_files(dir_path))
        # New files waiting for their size to stop changing
        self._pending_files: dict[Path, FileSignature] = {}

    def poll(self) -> list[Path]:
        """
        Scans the directory.

        :return: The new files that are ready to be transcribed, sorted.
        """
        ready_files = []
        current_files = list_supported_files(self.dir_path)

        for file_path in current_files:
            if file_path in self._known_files:
                continue

            signature = self._get_signature(file_path)
            if signature is None:  # Removed while scanning
                continue

            is_stable = self._pending_files.get(file_path) == signature
            # Empty files are usually being created
            if is_stable and signature[0] > 0:
                del self._pending_files[file_path]
                self._known_files.add(file_path)
                ready_files.append(file_path)
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
