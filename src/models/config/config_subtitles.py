from dataclasses import dataclass
from enum import Enum


@dataclass
class ConfigSubtitles:
    highlight_words: bool
    max_line_count: int
    max_line_width: int
    # Chinese, Japanese and Korean characters are about twice as wide as Latin
    # ones, and the lines of vertical videos (e.g. for phones) are narrower
    max_line_width_cjk: int = 16
    max_line_width_vertical: int = 24
    max_line_width_vertical_cjk: int = 10
    max_line_count_vertical: int = 2

    class Key(Enum):
        """
        Enum class for keys associated with the subtitles configuration.
        """

        SECTION = "subtitles"
        HIGHLIGHT_WORDS = "highlight_words"
        MAX_LINE_COUNT = "max_line_count"
        MAX_LINE_WIDTH = "max_line_width"
        MAX_LINE_WIDTH_CJK = "max_line_width_cjk"
        MAX_LINE_WIDTH_VERTICAL = "max_line_width_vertical"
        MAX_LINE_WIDTH_VERTICAL_CJK = "max_line_width_vertical_cjk"
        MAX_LINE_COUNT_VERTICAL = "max_line_count_vertical"

    def line_count(self, is_vertical: bool) -> int:
        """:param is_vertical: Whether the video is taller than it's wide."""
        return self.max_line_count_vertical if is_vertical else self.max_line_count

    def line_width(self, is_cjk: bool, is_vertical: bool) -> int:
        """
        :param is_cjk: Whether the text is in Chinese, Japanese or Korean.
        :param is_vertical: Whether the video is taller than it's wide.
        """
        if is_vertical:
            return (
                self.max_line_width_vertical_cjk
                if is_cjk
                else (self.max_line_width_vertical)
            )
        return self.max_line_width_cjk if is_cjk else self.max_line_width
