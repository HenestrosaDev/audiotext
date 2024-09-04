import os
import sys
from pathlib import Path


def get_root_path() -> Path:
    """
    Gets absolute path of the project.

    Taken from the [PyInstaller docs](https://pyinstaller.org/en/stable/runtime-information.html)

    :return: The absolute path to the program directory.
    :rtype: Path
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        root_path = Path(sys._MEIPASS)
    else:
        root_path = Path(__file__).parent.parent.parent

    # Add the root path to the PATH in order to allow macOS to pick up the binaries,
    # since `.app` bundles launched from Finder get a very limited shell environment.
    # https://github.com/orgs/pyinstaller/discussions/8773
    os.environ["PATH"] += os.pathsep + str(root_path)

    return root_path


IMG_RELATIVE_PATH = "res/img"

ROOT_PATH = get_root_path()
