import utils.constants as c
from utils.config_manager import ConfigManager
from utils.i18n import get_language_name, sort_key


class OptionLabels:
    """
    Maps the values stored in the configuration to the (translated) labels shown in
    an option menu, and vice versa.
    """

    def __init__(self, labels_by_value: dict[str, str]) -> None:
        self._labels_by_value = labels_by_value
        self._values_by_label = {
            label: value for value, label in labels_by_value.items()
        }

    @property
    def labels(self) -> list[str]:
        return list(self._labels_by_value.values())

    def label(self, value: str) -> str:
        return self._labels_by_value.get(value, value)

    def value(self, label: str) -> str:
        return self._values_by_label.get(label, label)


def get_language_labels() -> dict[str, str]:
    """The names of the audio languages in the interface language, sorted."""
    labels = {
        code: get_language_name(code, fallback=name)
        for code, name in c.AUDIO_LANGUAGES.items()
    }
    return dict(sorted(labels.items(), key=lambda item: sort_key(item[1])))


def save_config(key: ConfigManager.KeyType, value: str) -> None:
    ConfigManager.modify_value(type(key).SECTION, key, value)
