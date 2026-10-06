"""
Translation of the user interface.

Strings are marked with `_()` to be translated when they are shown, or with `N_()`
when they are defined before the interface language is set (e.g. module constants),
so they are extracted for translation but translated later with `_()`. `L_()`
gives a text of the interface that is translated again when the language changes
(see `views.localization`), e.g. `localize(label, text=L_("Settings"))`.

The catalogs live in `res/locales/<language>/LC_MESSAGES/audiotext.po` (see the
"Translations" section of the README to add or update them).
"""

import gettext
import locale
import logging
import os
import subprocess
import sys
import unicodedata
from collections.abc import Callable

from babel import Locale, UnknownLocaleError

from utils.path_helper import ROOT_PATH

logger = logging.getLogger(__name__)

LOCALES_PATH = ROOT_PATH / "res" / "locales"
DOMAIN = "audiotext"
DEFAULT_LANGUAGE = "en"
SYSTEM_LANGUAGE = "system"

# Languages of the interface, with their native names
UI_LANGUAGES = {
    "ca": "Català",
    "cs": "Čeština",
    "de": "Deutsch",
    "en": "English",
    "es": "Español",
    "fr": "Français",
    "gl": "Galego",
    "hi": "हिन्दी",
    "id": "Bahasa Indonesia",
    "it": "Italiano",
    "ja": "日本語",
    "ko": "한국어",
    "nl": "Nederlands",
    "pl": "Polski",
    "pt": "Português",
    "ro": "Română",
    "ru": "Русский",
    "sv": "Svenska",
    "tr": "Türkçe",
    "uk": "Українська",
    "vi": "Tiếng Việt",
    "zh_CN": "简体中文",
}

# Whisper uses some codes that differ from the ISO 639 codes known by Babel
_WHISPER_TO_ISO_LANGUAGE_CODES = {"jw": "jv"}


class _InterfaceLanguage:
    """The language of the interface and the translations of its messages."""

    def __init__(self) -> None:
        self.code = DEFAULT_LANGUAGE
        self.translation: gettext.NullTranslations = gettext.NullTranslations()


_interface_language = _InterfaceLanguage()


def _(message: str) -> str:
    """Translates the message into the current interface language."""
    return _interface_language.translation.gettext(message)


def N_(message: str) -> str:
    """Marks a message for translation without translating it."""
    return message


def L_(message: str) -> Callable[[], str]:
    """
    Marks a message for translation, which is translated each time the returned
    function is called, i.e. into the current interface language.
    """
    return lambda: _(message)


def get_language() -> str:
    """Returns the code of the current interface language."""
    return _interface_language.code


def set_language(setting: str) -> str:
    """
    Sets the language of the interface.

    :param setting: A code of `UI_LANGUAGES`, or `SYSTEM_LANGUAGE` to use the
                    language of the operating system.
    :return: The code of the language that has been set.
    """
    language = resolve_language(setting)
    _interface_language.code = language
    _interface_language.translation = gettext.translation(
        DOMAIN, LOCALES_PATH, languages=[language], fallback=True
    )
    logger.info("Interface language: %s", language)

    return language


def resolve_language(setting: str) -> str:
    """
    Returns the interface language for the given setting, falling back to English
    if the language is not supported.
    """
    is_system = setting == SYSTEM_LANGUAGE
    candidates = _get_system_languages() if is_system else [setting]

    for candidate in candidates:
        if language := match_ui_language(candidate):
            return language

    return DEFAULT_LANGUAGE


def match_ui_language(locale_name: str) -> str | None:
    """
    Finds the supported interface language that best matches a locale name such as
    "es_ES.UTF-8", "pt-BR" or "zh-Hans-CN".

    :return: The code of the language, or None if it's not supported.
    """
    normalized = locale_name.split(".")[0].replace("-", "_")
    parts = normalized.split("_")
    language = parts[0].lower()

    if language == "zh":
        # Only Simplified Chinese is available
        is_traditional = any(part in {"Hant", "TW", "HK", "MO"} for part in parts)
        return None if is_traditional else "zh_CN"

    return language if language in UI_LANGUAGES else None


def _get_system_languages() -> list[str]:
    """Returns the preferred languages of the operating system, in order."""
    languages = []

    for variable in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        if value := os.environ.get(variable):
            languages.extend(value.split(":"))

    # Apps opened from the macOS Finder don't get the `LANG` variable
    if sys.platform == "darwin":
        languages.extend(_get_macos_languages())

    if system_locale := locale.getlocale()[0]:
        languages.append(system_locale)

    return [language for language in languages if language not in {"C", "POSIX"}]


def _get_macos_languages() -> list[str]:
    try:
        output = subprocess.run(
            ["defaults", "read", "-g", "AppleLanguages"],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []

    # The output looks like: (\n    "es-ES",\n    "en-US"\n)
    return [line.strip(' ",') for line in output.splitlines()[1:-1]]


def get_docs_url(docs_url: str, language: str) -> str:
    """
    Returns the URL of the documentation in an interface language. Each language
    is in a folder of the website named after its code in lowercase, with a hyphen
    (e.g. "/en/", "/es/" or "/zh-cn/").

    :param docs_url: The URL of the website, without a trailing slash.
    :param language: A code of `UI_LANGUAGES`. Unknown codes get the English one.
    """
    if language not in UI_LANGUAGES:
        language = DEFAULT_LANGUAGE

    return f"{docs_url}/{language.lower().replace('_', '-')}/"


def get_language_name(language_code: str, fallback: str) -> str:
    """
    Returns the name of a language (e.g. of the audio to transcribe) in the current
    interface language.

    :param language_code: The ISO 639 code used by Whisper.
    :param fallback: The name used if the name is not known.
    """
    iso_code = _WHISPER_TO_ISO_LANGUAGE_CODES.get(language_code, language_code)

    try:
        locale_names = Locale.parse(_interface_language.code).languages
        name: str | None = locale_names.get(iso_code)
    except (UnknownLocaleError, ValueError):
        name = None

    if not name:
        return fallback

    # Some languages write the names of languages in lowercase (e.g. "inglés")
    return name[0].upper() + name[1:]


def sort_key(text: str) -> str:
    """
    :return: A key to sort texts alphabetically, ignoring case and accents, so
        e.g. "Čeština" goes before "Deutsch" instead of after "Türkçe".
    """
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))
