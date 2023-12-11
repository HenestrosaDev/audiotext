from dataclasses import dataclass
from enum import Enum
from typing import Optional


@dataclass
class ConfigSubtitles:
    max_line_count: int
    max_line_width: int

    class Key(Enum):
        """
        Enum class for keys associated with the subtitles configuration.
        """

        SECTION = "subtitles"
        MAX_LINE_COUNT = "max_line_count"
        MAX_LINE_WIDTH = "max_line_width"

        def value_type(self) -> Optional[str]:
            """Get the value type associated with the ConfigKey."""
            type_mapping = {
                self.MAX_LINE_COUNT: "int",
                self.MAX_LINE_WIDTH: "int",
            }

            return type_mapping.get(self, None)
