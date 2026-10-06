import utils.constants as c
from utils.config_manager import ConfigManager
from utils.i18n import get_language_name, sort_key


def get_language_labels() -> dict[str, str]:
    """The names of the audio languages in the interface language, sorted."""
    labels = {
        code: get_language_name(code, fallback=name)
        for code, name in c.AUDIO_LANGUAGES.items()
    }
    return dict(sorted(labels.items(), key=lambda item: sort_key(item[1])))


def save_config(key: ConfigManager.KeyType, value: str) -> None:
    ConfigManager.modify_value(type(key).SECTION, key, value)
