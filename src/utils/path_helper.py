import sys
from pathlib import Path


def get_path(relative_path: str = "") -> Path:
    """
    Gets absolute path of the project.

    :param relative_path: The relative path to the application's base path.
    Default is an empty string.
    :type relative_path: str
    :return: The absolute path to the file or directory specified by the relative path.
    :rtype: Path
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = Path(sys._MEIPASS)
    except (Exception,):
        base_path = Path(__file__).parent.parent.parent

    return base_path / relative_path


ROOT_PATH = get_path("")
