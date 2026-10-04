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


def get_user_config_dir() -> Path:
    """
    Gets the directory where the settings of the user are stored, following the
    conventions of each operating system. It can be overridden with the
    `AUDIOTEXT_CONFIG_DIR` environment variable (e.g. for a portable setup).

    :return: The directory. It may not exist yet.
    :rtype: Path
    """
    if config_dir := os.environ.get("AUDIOTEXT_CONFIG_DIR"):
        return Path(config_dir)

    if sys.platform == "win32":
        base_dir = Path(os.environ.get("APPDATA") or Path.home() / "AppData/Roaming")
        return base_dir / "Audiotext"

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Audiotext"

    base_dir = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base_dir / "audiotext"


IMG_RELATIVE_PATH = "res/img"

ROOT_PATH = get_root_path()
