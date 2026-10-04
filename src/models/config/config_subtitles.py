from dataclasses import dataclass
from enum import Enum


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
