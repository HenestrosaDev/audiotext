from dataclasses import dataclass
from enum import Enum
from typing import Optional


@dataclass
class ConfigTranscription:
    language: str
    audio_source: str
    method: str
    autosave: bool
    overwrite_files: bool

    class Key(Enum):
        """
        Enum class for keys associated with the system configuration.
        """

        SECTION = "transcription"
        LANGUAGE = "language"
        AUDIO_SOURCE = "audio_source"
        METHOD = "method"
        AUTOSAVE = "autosave"
        OVERWRITE_FILES = "overwrite_files"

        def value_type(self) -> Optional[str]:
            """
            Get the value type associated with the ConfigKey.

            :return: The type of the value as a string, or None if the key is not found.
            :rtype: str
            """
            type_mapping = {
                ConfigTranscription.Key.LANGUAGE: "str",
                ConfigTranscription.Key.AUDIO_SOURCE: "str",
                ConfigTranscription.Key.METHOD: "str",
                ConfigTranscription.Key.AUTOSAVE: "bool",
                ConfigTranscription.Key.OVERWRITE_FILES: "bool",
            }

            return str(type_mapping.get(self, None))
