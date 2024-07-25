import sys
from pathlib import Path


def get_root_path() -> Path:
    """
    Gets absolute path of the project.

    Taken from the [PyInstaller docs](https://pyinstaller.org/en/stable/runtime-information.html)

    :return: The absolute path to the file or directory specified by the relative path.
    :rtype: Path
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    else:
        return Path(__file__).parent.parent.parent


IMG_RELATIVE_PATH = "res/img"

ROOT_PATH = get_root_path()
