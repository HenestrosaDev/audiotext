import functools
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def hide_console_windows() -> None:
    """
    Keeps the programs the app runs (e.g. FFmpeg, also when WhisperX or pydub run
    it) from opening a console window on Windows, since the app has no console of
    its own to share with them.
    """
    if sys.platform != "win32":
        return

    popen_init = subprocess.Popen.__init__

    @functools.wraps(popen_init)
    def init(self: subprocess.Popen[Any], *args: Any, **kwargs: Any) -> None:
        kwargs["creationflags"] = (
            kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
        )
        popen_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = init  # type: ignore[method-assign]


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
