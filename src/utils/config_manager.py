from configparser import ConfigParser
from pathlib import Path
from typing import Optional, Union

from models.config.config_subtitles import ConfigSubtitles
from models.config.config_system import ConfigSystem
from models.config.config_transcription import ConfigTranscription
from models.config.config_whisper_api import ConfigWhisperAPI
from models.config.config_whisperx import ConfigWhisperX
from utils.path_helper import ROOT_PATH


class ConfigManager:
    _CONFIG_FILE_PATH = ROOT_PATH / "config.ini"
    KeyType = Union[ConfigWhisperX.Key, ConfigSubtitles.Key]

    @staticmethod
    def read_config(file_path: Path = _CONFIG_FILE_PATH) -> Optional[ConfigParser]:
        config = ConfigParser()
        config.read(file_path)
        return config

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
    def get_config_whisper_api() -> ConfigWhisperAPI:
        section = ConfigWhisperAPI.Key.SECTION

        return ConfigWhisperAPI(
            response_format=ConfigManager.get_value(
                section, ConfigWhisperAPI.Key.RESPONSE_FORMAT
            ),
            temperature=ConfigManager.get_value(
                section, ConfigWhisperAPI.Key.TEMPERATURE
            ),
            timestamp_granularities=ConfigManager.get_value(
                section, ConfigWhisperAPI.Key.TIMESTAMP_GRANULARITIES
            ),
        )

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
    def get_value(
        section: KeyType,
        key: KeyType,
        file_path: Path = _CONFIG_FILE_PATH,
    ) -> Optional[Union[str, bool, int, float]]:
        config = ConfigManager.read_config(file_path)

        section_name = section.value
        key_name = key.value
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
        else:
            print(
                f"Section [{section_name}] or Key [{key_name}] not found in the config"
            )
            return None

    @staticmethod
    def modify_value(
        section: KeyType,
        key: KeyType,
        new_value: str,
        file_path: Path = _CONFIG_FILE_PATH,
    ):
        config = ConfigManager.read_config(file_path)

        section_name = section.value
        key_name = key.value

        # Check if the section and option exist before modifying
        if section_name in config and key_name in config[section_name]:
            config.set(section_name, key_name, new_value)

            with open(file_path, "w") as config_file:
                config.write(config_file)

            print(f"Value for [{section}][{key_name}] modified to {new_value}")
        else:
            print(f"Section [{section}] or Key [{key_name}] not found in the config")
