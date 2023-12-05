import gettext
import locale

import utils.constants as c
import utils.path_helper as ph

_ = None


def load_translation(language_code: str):
    """
    Loads the translation for the provided language code.

    This function uses the gettext library to load the translation file
    for the provided language code from the localedir. If the translation
    file is not found, the fallback is set to True so that a default language
    will be used if available. The function then installs the loaded translation
    and sets the global _ variable to the gettext function for later use.

    :param language_code: The code for the language to be used for translation.
    :type language_code: str
    """
    try:
        lang_code_without_territory = language_code.split("_")[0]
        if lang_code_without_territory not in c.APP_LANGUAGES:
            lang_code_without_territory = "en"
    except Exception:
        lang_code_without_territory = "en"
        locale.setlocale(locale.LC_ALL, "en_US")

    translation = gettext.translation(
        "app",
        localedir=ph.ROOT_PATH / "res/locales",
        languages=[lang_code_without_territory],
        fallback=True,
    )
    translation.install()

    global _
    _ = translation.gettext


load_translation(locale.getdefaultlocale()[0][:2])
