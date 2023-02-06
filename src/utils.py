import gettext
import locale
import sys
import constants as c
from pathlib import Path


def get_path(relative_path: str = "") -> Path:
    """
    Gets absolute path of the project.

    :param str relative_path: The relative path to the application's base path.
    Default is an empty string.
    :return: The absolute path to the file or directory specified by the relative path.
    :rtype: Path
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = Path(sys._MEIPASS)
    except (Exception,):
        base_path = Path(__file__).parent.parent.resolve()

    return (base_path / relative_path).resolve()


ROOT_PATH = get_path("")

_ = None


def load_translation(language_code: str):
    """
    Loads the translation for the provided language code.

    This function uses the gettext library to load the translation file
    for the provided language code from the localedir. If the translation
    file is not found, the fallback is set to True so that a default language
    will be used if available. The function then installs the loaded translation
    and sets the global _ variable to the gettext function for later use.

    :param str language_code: The code for the language to be used for translation.
    """
    try:
        lang_code_without_territory = language_code.split("_")[0]
        if lang_code_without_territory not in c.APP_LANGUAGES:
            lang_code_without_territory = "en"
    except Exception:
        lang_code_without_territory = "en"
        locale.setlocale(locale.LC_ALL, "en_US")


    translation = gettext.translation(
        "all",
        localedir=ROOT_PATH / "res/locales",
        languages=[lang_code_without_territory],
        fallback=True,
    )
    translation.install()
    global _
    _ = translation.gettext


load_translation(locale.getlocale()[0])
