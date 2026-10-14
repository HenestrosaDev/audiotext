"""
Splits the segments of a transcription into subtitles short enough to be read
over a video, like the cues of an `.srt` file.
"""

import bisect
import re
import unicodedata
from dataclasses import dataclass
from itertools import pairwise

from models.config.config_subtitles import ConfigSubtitles
from models.transcript_segment import TranscriptSegment, TranscriptWord


@dataclass(frozen=True)
class Cue:
    """A subtitle with the time it's shown, in seconds."""

    start: float
    end: float
    text: str


def _word_positions(
    segment: TranscriptSegment,
) -> list[tuple[TranscriptWord, int, int]]:
    """
    :return: Each word and its position in the text. Words are looked up in the
             text, so its spacing and punctuation are kept.
    """
    positions = []
    cursor = 0
    for word in segment.words:
        position = segment.text.find(word.text, cursor) if word.text else -1
        if position < 0:
            continue
        cursor = position + len(word.text)
        positions.append((word, position, cursor))
    return positions


def _strip_range(text: str, first: int, last: int) -> tuple[int, int]:
    """:return: The range without the spaces at its ends."""
    while first < last and text[first].isspace():
        first += 1
    while last > first and text[last - 1].isspace():
        last -= 1
    return first, last


def _length(text: str, first: int, last: int) -> int:
    """The length of a line of the text, without the spaces at its ends."""
    first, last = _strip_range(text, first, last)
    return last - first


def _is_wide(char: str) -> bool:
    return unicodedata.east_asian_width(char) in ("W", "F")


# Punctuation that never starts a line, such as "。", "," or a closing quote
_TRAILING_PUNCTUATION = {"Po", "Pe", "Pf"}


def _break_points(text: str, first: int, last: int) -> list[int]:
    """
    :return: Where a line can start: at each word, or at each character of the
             languages written without spaces (e.g. Chinese), except before the
             punctuation that closes the text before it.
    """
    points = []
    for match in re.finditer(r"\S+", text[first:last]):
        start, end = first + match.start(), first + match.end()
        points.append(start)
        points.extend(
            idx
            for idx in range(start + 1, end)
            if (_is_wide(text[idx]) or _is_wide(text[idx - 1]))
            and unicodedata.category(text[idx]) not in _TRAILING_PUNCTUATION
        )
    return points


def _layout_lines(
    text: str, points: list[int], end: int, max_width: int, max_lines: int
) -> list[list[int]]:
    """
    Fills the lines with as much text as fits, to know how many lines each
    subtitle needs, and then evens out the lines of each subtitle.

    :param points: Where a line can start (see `_break_points`).
    :param end: Where the text ends.
    :return: The lines of each subtitle, as the index of the point where each of
             them starts.
    """

    def bound(idx: int) -> int:
        return points[idx] if idx < len(points) else end

    line_starts = [0]
    for idx in range(1, len(points)):
        if _length(text, points[line_starts[-1]], bound(idx + 1)) > max_width:
            line_starts.append(idx)

    subtitles = []
    for idx in range(0, len(line_starts), max_lines):
        next_idx = idx + max_lines
        last = line_starts[next_idx] if next_idx < len(line_starts) else len(points)
        subtitles.append(
            _balance_lines(
                text, points, end, line_starts[idx:next_idx], last, max_width
            )
        )
    return subtitles


def _balance_lines(
    text: str,
    points: list[int],
    end: int,
    line_starts: list[int],
    last: int,
    max_width: int,
) -> list[int]:
    """
    Evens out the lines of a subtitle, so they're as short as possible without
    taking more lines. If they can't be even, the bottom line is the longer one,
    as it's usual in subtitles.

    :param line_starts: The lines filled with as much text as fits.
    :param last: The index of the point after the subtitle.
    """
    if len(line_starts) == 1:
        return line_starts

    first = line_starts[0]

    def bound(idx: int) -> int:
        return points[idx] if idx < len(points) else end

    def fill_from_the_bottom(limit: int) -> list[int]:
        starts = []
        line_end = last
        while line_end > first:
            start = line_end - 1
            while (
                start > first
                and _length(text, points[start - 1], bound(line_end)) <= limit
            ):
                start -= 1
            starts.append(start)
            line_end = start
        return starts[::-1]

    total = _length(text, points[first], bound(last))
    for limit in range(-(-total // len(line_starts)), max_width + 1):
        starts = fill_from_the_bottom(limit)
        if len(starts) <= len(line_starts):
            return starts
    # A word longer than a line can't be evened out
    return line_starts


# When a subtitle starts and ends, and the range of the text of each of its lines
_Layout = tuple[float, float, list[tuple[int, int]]]


def _segment_layout(
    segment: TranscriptSegment, max_width: int, max_lines: int
) -> list[_Layout]:
    """:return: The subtitles of a segment, as ranges of its text."""
    text = segment.text
    first, last = _strip_range(text, 0, len(text))
    if first == last:
        return []
    if last - first <= max_width:
        return [(segment.start, segment.end, [(first, last)])]

    # With the timings of the words, each subtitle starts with its first word
    if words := _word_positions(segment):
        # The text before the first word (e.g. the speaker) is part of its line
        points = [first, *(position for _word, position, _end in words[1:])]
        times = [segment.start, *(word.start for word, _position, _end in words[1:])]
        layouts = _layouts(segment, points, times, last, max_width, max_lines)
        # Words added by an edit take no time, so a cue of them would never be shown
        if all(start < end for start, end, _lines in layouts):
            return layouts

    # Otherwise, the duration of the segment is shared by the length of the text
    points = _break_points(text, first, last)
    duration = segment.end - segment.start
    times = [
        segment.start + duration * (point - first) / (last - first) for point in points
    ]
    return _layouts(segment, points, times, last, max_width, max_lines)


def _layouts(
    segment: TranscriptSegment,
    points: list[int],
    times: list[float],
    end: int,
    max_width: int,
    max_lines: int,
) -> list[_Layout]:
    """
    :param points: Where a line can start (see `_break_points`).
    :param times: When the text of each point is said.
    :param end: Where the text ends.
    """
    text = segment.text
    subtitles = _layout_lines(text, points, end, max_width, max_lines)
    layouts: list[_Layout] = []
    for idx, line_starts in enumerate(subtitles):
        is_last = idx + 1 == len(subtitles)
        next_point = len(points) if is_last else subtitles[idx + 1][0]
        bounds = [points[point] for point in line_starts]
        bounds.append(end if is_last else points[next_point])
        lines = [_strip_range(text, first, last) for first, last in pairwise(bounds)]
        if lines := [(first, last) for first, last in lines if first < last]:
            layouts.append(
                (
                    times[line_starts[0]],
                    segment.end if is_last else times[next_point],
                    lines,
                )
            )
    return layouts


def build_cues(
    segments: list[TranscriptSegment], max_line_width: int, max_line_count: int = 1
) -> list[Cue]:
    """
    :param max_line_width: The maximum number of characters of a line (e.g. 42).
    :param max_line_count: The maximum number of lines of a cue (e.g. 2).
    """
    max_line_width = max(max_line_width, 1)
    max_line_count = max(max_line_count, 1)
    cues: list[Cue] = []
    for segment in segments:
        text = segment.text
        cues.extend(
            Cue(start, end, "\n".join(text[first:last] for first, last in lines))
            for start, end, lines in _segment_layout(
                segment, max_line_width, max_line_count
            )
        )
    return cues


def uses_wide_characters(segments: list[TranscriptSegment]) -> bool:
    """
    Whether most of the text is written in wide characters, which take the space
    of two Latin ones (e.g. Chinese, Japanese or Korean).
    """
    wide = total = 0
    for segment in segments:
        for char in segment.text:
            if not char.isspace():
                total += 1
                wide += _is_wide(char)
    return wide * 2 > total


def line_limits(
    config: ConfigSubtitles, segments: list[TranscriptSegment], is_vertical: bool
) -> tuple[int, int]:
    """
    :param is_vertical: Whether the video is taller than it's wide.
    :return: The maximum width and number of lines of the subtitles of the
             segments, as configured for their script and the video.
    """
    is_cjk = uses_wide_characters(segments)
    return config.line_width(is_cjk, is_vertical), config.line_count(is_vertical)


class CueTrack:
    """Finds the cue shown at a position of the playback."""

    def __init__(self, cues: list[Cue]) -> None:
        self.cues = cues
        self._starts = [cue.start for cue in cues]

    def at(self, position: float) -> Cue | None:
        idx = bisect.bisect_right(self._starts, position) - 1
        if idx < 0 or position >= self.cues[idx].end:
            return None
        return self.cues[idx]
