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
            """Get the value type associated with the ConfigKey."""
            type_mapping = {
                self.LANGUAGE: "str",
                self.AUDIO_SOURCE: "str",
                self.METHOD: "str",
                self.AUTOSAVE: "bool",
                self.OVERWRITE_FILES: "bool",
            }

            return type_mapping.get(self, None)
