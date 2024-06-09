from dataclasses import dataclass
from enum import Enum
from typing import Optional


@dataclass
class ConfigSubtitles:
    highlight_words: bool
    max_line_count: int
    max_line_width: int
    output_file_types: str

    class Key(Enum):
        """
        Enum class for keys associated with the subtitles configuration.
        """

        SECTION = "subtitles"
        HIGHLIGHT_WORDS = "highlight_words"
        MAX_LINE_COUNT = "max_line_count"
        MAX_LINE_WIDTH = "max_line_width"
        OUTPUT_FILE_TYPES = "output_file_types"

        def value_type(self) -> Optional[str]:
            """Get the value type associated with the ConfigKey."""
            type_mapping = {
                self.HIGHLIGHT_WORDS: "bool",
                self.MAX_LINE_COUNT: "int",
                self.MAX_LINE_WIDTH: "int",
                self.OUTPUT_FILE_TYPES: "str",
            }

            return type_mapping.get(self, None)
