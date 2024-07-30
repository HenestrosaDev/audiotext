from configparser import ConfigParser
from pathlib import Path
from typing import Any, Union

from models.config.config_subtitles import ConfigSubtitles
from models.config.config_system import ConfigSystem
from models.config.config_transcription import ConfigTranscription
from models.config.config_whisper_api import ConfigWhisperApi
from models.config.config_whisperx import ConfigWhisperX
from utils.path_helper import ROOT_PATH


class ConfigManager:
    _CONFIG_FILE_PATH = ROOT_PATH / "config.ini"
    KeyType = Union[
        ConfigSubtitles.Key,
        ConfigSystem.Key,
        ConfigTranscription.Key,
        ConfigWhisperApi.Key,
        ConfigWhisperX.Key,
    ]

    @staticmethod
    def read_config(file_path: Path = _CONFIG_FILE_PATH) -> ConfigParser:
        config = ConfigParser(
            converters={
                "list": lambda x: [i.strip() for i in x.split(",")]
                if len(x) > 0
                else []
            }
        )
        config.read(file_path)
        return config

    @staticmethod
    def get_config_subtitles() -> ConfigSubtitles:
        section = ConfigSubtitles.Key.SECTION

        return ConfigSubtitles(
            highlight_words=ConfigManager.get_value(
                section, ConfigSubtitles.Key.HIGHLIGHT_WORDS
            ),
            max_line_count=ConfigManager.get_value(
                section, ConfigSubtitles.Key.MAX_LINE_COUNT
            ),
            max_line_width=ConfigManager.get_value(
                section, ConfigSubtitles.Key.MAX_LINE_WIDTH
            ),
        )

    @staticmethod
    def get_config_system() -> ConfigSystem:
        section = ConfigSystem.Key.SECTION

        return ConfigSystem(
            appearance_mode=ConfigManager.get_value(
                section, ConfigSystem.Key.APPEARANCE_MODE
            ),
        )

    @staticmethod
    def get_config_transcription() -> ConfigTranscription:
        section = ConfigTranscription.Key.SECTION

        return ConfigTranscription(
            language=ConfigManager.get_value(section, ConfigTranscription.Key.LANGUAGE),
            audio_source=ConfigManager.get_value(
                section, ConfigTranscription.Key.AUDIO_SOURCE
            ),
            method=ConfigManager.get_value(section, ConfigTranscription.Key.METHOD),
            autosave=ConfigManager.get_value(section, ConfigTranscription.Key.AUTOSAVE),
            overwrite_files=ConfigManager.get_value(
                section, ConfigTranscription.Key.OVERWRITE_FILES
            ),
        )

    @staticmethod
    def get_config_whisper_api() -> ConfigWhisperApi:
        section = ConfigWhisperApi.Key.SECTION

        return ConfigWhisperApi(
            response_format=ConfigManager.get_value(
                section, ConfigWhisperApi.Key.RESPONSE_FORMAT
            ),
            temperature=ConfigManager.get_value(
                section, ConfigWhisperApi.Key.TEMPERATURE
            ),
            timestamp_granularities=ConfigManager.get_value(
                section, ConfigWhisperApi.Key.TIMESTAMP_GRANULARITIES
            ),
        )

    @staticmethod
    def get_config_whisperx() -> ConfigWhisperX:
        section = ConfigWhisperX.Key.SECTION

        return ConfigWhisperX(
            model_size=ConfigManager.get_value(section, ConfigWhisperX.Key.MODEL_SIZE),
            batch_size=ConfigManager.get_value(section, ConfigWhisperX.Key.BATCH_SIZE),
            compute_type=ConfigManager.get_value(
                section, ConfigWhisperX.Key.COMPUTE_TYPE
            ),
            use_cpu=ConfigManager.get_value(section, ConfigWhisperX.Key.USE_CPU),
            can_use_gpu=ConfigManager.get_value(
                section, ConfigWhisperX.Key.CAN_USE_GPU
            ),
            output_file_types=ConfigManager.get_value(
                section, ConfigWhisperX.Key.OUTPUT_FILE_TYPES
            ),
        )

    @staticmethod
    def get_value(
        section: KeyType,
        key: KeyType,
        file_path: Path = _CONFIG_FILE_PATH,
    ) -> Union[str, bool, int, float, list[Any]]:
        """
        Retrieve the value of a specified key within a section of a configuration file.

        This method reads a configuration file, checks if the given section and key exist,
        and if they do, returns the value of the key in its appropriate type. If the
        section or key does not exist, it raises a ValueError.

        :param section: The section in the configuration file where the key is located.
        :type section: KeyType
        :param key: The key within the section whose value is to be retrieved.
        :type key: KeyType
        :param file_path: The path to the configuration file. Defaults to
            _CONFIG_FILE_PATH.
        :type file_path: Path
        :raises FileNotFoundError: If the specified configuration file does not exist.
        :raises ValueError: If the section or key is not found in the config. file.
        :return: The value of the specified key in its appropriate type (str, bool, int,
            float, or list).
        :rtype: Union[str, bool, int, float, list[Any]]
        """
        config = ConfigManager.read_config(file_path)

        section_name = str(section.value)
        key_name = str(key.value)
        key_value_type = key.value_type()

        # Check if the section and key exist before getting the value
        if section_name in config and key_name in config[section_name]:
            if key_value_type == "str":
                return config.get(section_name, key_name)
            elif key_value_type == "bool":
                return config.getboolean(section_name, key_name)
            elif key_value_type == "int":
                return config.getint(section_name, key_name)
            elif key_value_type == "float":
                return config.getfloat(section_name, key_name)
            elif key_value_type == "list":
                return config.getlist(section_name, key_name)  # type: ignore

        raise ValueError(
            f"Section [{section}] or Key [{key_name}] not found in the config"
        )

    @staticmethod
    def modify_value(
        section: KeyType,
        key: KeyType,
        new_value: str,
        file_path: Path = _CONFIG_FILE_PATH,
    ) -> None:
        """
        Modify the value of a specified key within a section of a configuration file.

        This method reads a configuration file, checks if the given section and key
        exist, and if they do, updates the value of the key to the new value provided.
        If the section or key does not exist, it prints an error message.

        :param section: The section in the configuration file where the key is located.
        :type section: KeyType
        :param key: The key within the section whose value is to be modified.
        :type key: KeyType
        :param new_value: The new value to be set for the specified key.
        :type new_value: str
        :param file_path: The path to the configuration file. Defaults to
            _CONFIG_FILE_PATH.
        :type file_path: Path
        :raises FileNotFoundError: If the specified configuration file does not exist.
        :raises ValueError: If the section or key is not found in the config. file.
        :return: None
        """
        config = ConfigManager.read_config(file_path)

        section_name = str(section.value)
        key_name = str(key.value)

        # Check if the section and option exist before modifying
        if section_name in config and key_name in config[section_name]:
            config.set(section_name, key_name, new_value)

            with open(file_path, "w") as config_file:
                config.write(config_file)

            print(f"Value for [{section_name}][{key_name}] modified to {new_value}")
        else:
            print(
                f"Section [{section_name}] or Key [{key_name}] not found in the config"
            )
