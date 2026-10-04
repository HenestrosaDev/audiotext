"""
Splits the segments of a transcription into subtitles short enough to be read
over a video, like the cues of an `.srt` file.
"""

import bisect
from dataclasses import dataclass

from models.transcript_segment import TranscriptSegment


@dataclass(frozen=True)
class Cue:
    """A subtitle with the time it's shown, in seconds."""

    start: float
    end: float
    text: str


def _split_text(text: str, max_chars: int) -> list[tuple[int, int]]:
    """
    :return: The ranges of the text of at most `max_chars` characters, broken at
             the spaces when possible (some languages, like Chinese, have none).
    """
    ranges = []
    start = 0
    length = len(text)

    while start < length:
        while start < length and text[start].isspace():
            start += 1
        if start >= length:
            break
        end = start + max_chars
        if end >= length:
            ranges.append((start, length))
            break
        cut = text.rfind(" ", start + 1, end + 1)
        if cut <= start:
            cut = end
        ranges.append((start, cut))
        start = cut

    return ranges


def _word_positions(segment: TranscriptSegment) -> list[tuple[float, int, int]]:
    """
    :return: The start time and the position in the text of each word. Words are
             looked up in the text, so its spacing and punctuation are kept.
    """
    positions = []
    cursor = 0
    for word in segment.words:
        position = segment.text.find(word.text, cursor) if word.text else -1
        if position < 0:
            continue
        cursor = position + len(word.text)
        positions.append((word.start, position, cursor))
    return positions


def _segment_cues(segment: TranscriptSegment, max_chars: int) -> list[Cue]:
    text = segment.text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [Cue(segment.start, segment.end, text)]

    # With the timings of the words, each cue starts with its first word
    words = _word_positions(segment)
    if words:
        breaks: list[tuple[float, int]] = []
        chunk_start = -1
        for start, position, end in words:
            if chunk_start < 0 or end - chunk_start > max_chars:
                chunk_start = position
                breaks.append((start, position))
        cues = []
        for idx, (start, position) in enumerate(breaks):
            is_last = idx + 1 == len(breaks)
            next_start, next_position = (
                (segment.end, len(segment.text)) if is_last else breaks[idx + 1]
            )
            chunk = segment.text[0 if idx == 0 else position : next_position].strip()
            if chunk:
                cues.append(
                    Cue(segment.start if idx == 0 else start, next_start, chunk)
                )
        return cues

    # Otherwise, the duration of the segment is shared by the length of each cue,
    # which is shown until the next one starts
    ranges = _split_text(text, max_chars)
    duration = segment.end - segment.start
    starts = [segment.start + duration * start / len(text) for start, _end in ranges]
    ends = [*starts[1:], segment.end]
    return [
        Cue(start, end, text[first:last].strip())
        for start, end, (first, last) in zip(starts, ends, ranges, strict=True)
    ]


def build_cues(segments: list[TranscriptSegment], max_chars: int) -> list[Cue]:
    """
    :param max_chars: The maximum length of a cue (e.g. two lines of 42
                      characters).
    """
    max_chars = max(max_chars, 1)
    cues = []
    for segment in segments:
        cues.extend(_segment_cues(segment, max_chars))
    return cues


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
