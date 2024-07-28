from dataclasses import dataclass
from enum import Enum
from typing import Optional


@dataclass
class ConfigSubtitles:
    highlight_words: bool
    max_line_count: int
    max_line_width: int

    class Key(Enum):
        """
        Enum class for keys associated with the subtitles configuration.
        """

        SECTION = "subtitles"
        HIGHLIGHT_WORDS = "highlight_words"
        MAX_LINE_COUNT = "max_line_count"
        MAX_LINE_WIDTH = "max_line_width"

        def value_type(self) -> Optional[str]:
            """
            Get the value type associated with the ConfigKey.

            :return: The type of the value as a string, or None if the key is not found.
            :rtype: str
            """
            type_mapping = {
                ConfigSubtitles.Key.HIGHLIGHT_WORDS: "bool",
                ConfigSubtitles.Key.MAX_LINE_COUNT: "int",
                ConfigSubtitles.Key.MAX_LINE_WIDTH: "int",
            }

            return str(type_mapping.get(self, None))
