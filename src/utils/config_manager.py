import dataclasses
import logging
from configparser import ConfigParser
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar, get_origin, get_type_hints

from models.config.config_ai import ConfigAi
from models.config.config_subtitles import ConfigSubtitles
from models.config.config_system import ConfigSystem
from models.config.config_transcription import ConfigTranscription
from models.config.config_whisper_api import ConfigWhisperApi
from models.config.config_whisperx import ConfigWhisperX
from utils.path_helper import ROOT_PATH, get_user_config_dir

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

    ConfigT = TypeVar("ConfigT", bound=DataclassInstance)

logger = logging.getLogger(__name__)


def _parse_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",")] if value else []


class ConfigManager:
    """
    Reads and writes the settings of the app.

    The default values are read from the `config.ini` file of the app, which is
    never modified. The values changed by the user are stored in a `config.ini`
    file in the user's configuration directory, and take precedence over the
    defaults. This way, the settings survive updates of the app, and the
    defaults can change without overwriting the choices of the user.
    """

    defaults_file_path: Path = ROOT_PATH / "config.ini"
    user_file_path: Path = get_user_config_dir() / "config.ini"

    KeyType = (
        ConfigAi.Key
        | ConfigSubtitles.Key
        | ConfigSystem.Key
        | ConfigTranscription.Key
        | ConfigWhisperApi.Key
        | ConfigWhisperX.Key
    )

    @classmethod
    def read_config(cls) -> ConfigParser:
        """
        :return: The default settings, overridden by the ones of the user.
        """
        # Without interpolation, values can contain "%" (e.g. a prompt or a path)
        config = ConfigParser(interpolation=None, converters={"list": _parse_list})
        # Files that don't exist (e.g. the user's one before any change) are skipped
        config.read([cls.defaults_file_path, cls.user_file_path], encoding="utf-8")
        return config

    @classmethod
    def get_config_ai(cls) -> ConfigAi:
        return cls._load_section(ConfigAi, ConfigAi.Key.SECTION)

    @classmethod
    def get_config_subtitles(cls) -> ConfigSubtitles:
        return cls._load_section(ConfigSubtitles, ConfigSubtitles.Key.SECTION)

    @classmethod
    def get_config_system(cls) -> ConfigSystem:
        return cls._load_section(ConfigSystem, ConfigSystem.Key.SECTION)

    @classmethod
    def get_config_transcription(cls) -> ConfigTranscription:
        return cls._load_section(ConfigTranscription, ConfigTranscription.Key.SECTION)

    @classmethod
    def get_config_whisper_api(cls) -> ConfigWhisperApi:
        return cls._load_section(ConfigWhisperApi, ConfigWhisperApi.Key.SECTION)

    @classmethod
    def get_config_whisperx(cls) -> ConfigWhisperX:
        return cls._load_section(ConfigWhisperX, ConfigWhisperX.Key.SECTION)

    @classmethod
    def modify_value(cls, section: KeyType, key: KeyType, new_value: str) -> None:
        """
        Stores the value of a setting in the user's configuration file, which only
        contains the settings changed by the user. The file, the section and the
        key are created if they don't exist.

        :param section: The section of the setting.
        :param key: The key of the setting within the section.
        :param new_value: The new value of the setting.
        """
        file_path = cls.user_file_path
        config = ConfigParser(interpolation=None)
        config.read(file_path, encoding="utf-8")

        section_name = str(section.value)
        key_name = str(key.value)

        if not config.has_section(section_name):
            config.add_section(section_name)

        config.set(section_name, key_name, new_value)

        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as config_file:
            config.write(config_file)

        logger.info(
            "Value for [%s][%s] modified to %s", section_name, key_name, new_value
        )

    @classmethod
    def _load_section(
        cls,
        config_class: "type[ConfigT]",
        section: Enum,
    ) -> "ConfigT":
        """
        Builds a config dataclass from a section of the settings. Each value is
        parsed according to the type annotation of the matching dataclass field.
        Missing keys take the default value of the field, if it has one.

        :param config_class: The dataclass to instantiate.
        :param section: The key of the section that holds the values.
        :raises ValueError: If the section or any of the keys is not found.
        :return: An instance of `config_class` filled with the configured values.
        """
        config = cls.read_config()
        section_name = str(section.value)
        type_hints = get_type_hints(config_class)

        values = {
            field.name: cls._get_typed_value(
                config, section_name, field.name, type_hints[field.name]
            )
            for field in dataclasses.fields(config_class)
            if field.default is dataclasses.MISSING
            or config.has_option(section_name, field.name)
        }

        return config_class(**values)

    @staticmethod
    def _get_typed_value(
        config: ConfigParser, section_name: str, key_name: str, value_type: Any
    ) -> Any:
        if not config.has_option(section_name, key_name):
            raise ValueError(
                f"Section [{section_name}] or Key [{key_name}] not found in the config"
            )

        if value_type is bool:
            return config.getboolean(section_name, key_name)
        if value_type is int:
            return config.getint(section_name, key_name)
        if value_type is float:
            return config.getfloat(section_name, key_name)
        if get_origin(value_type) is list:
            return config.getlist(section_name, key_name)  # type: ignore[attr-defined]

        return config.get(section_name, key_name)
