import os
import subprocess
import sys
from pathlib import Path


def open_in_file_manager(path: Path) -> None:
    """
    Opens a directory in the file manager of the operating system.

    :param path: The directory to open.
    :raises OSError: If the file manager could not be opened.
    :raises subprocess.CalledProcessError: If the file manager returned an error.
    """
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]  # Only exists on Windows
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=True)
    else:
        subprocess.run(["xdg-open", str(path)], check=True)


def reveal_in_file_manager(path: Path) -> None:
    """
    Shows a file selected in the file manager of the operating system (the Finder
    on macOS, the Explorer on Windows). On Linux, its folder is opened instead,
    since there is no standard way to select the file.

    :param path: The file or folder to show.
    :raises FileNotFoundError: If the path doesn't exist.
    :raises OSError: If the file manager could not be opened.
    :raises subprocess.CalledProcessError: If the file manager returned an error.
    """
    if not path.exists():
        raise FileNotFoundError(path)

    if sys.platform == "darwin":
        subprocess.run(["open", "-R", str(path)], check=True)
    elif sys.platform == "win32":
        # Explorer returns 1 even when it succeeds
        subprocess.run(["explorer", f"/select,{path}"], check=False)
    else:
        open_in_file_manager(path if path.is_dir() else path.parent)
