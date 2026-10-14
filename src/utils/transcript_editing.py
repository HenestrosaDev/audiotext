"""
Corrections of a transcription: replacing a text, renaming a speaker and editing
the text of a segment. The timing of the segments of a translation can also
change, and segments can be added to it or deleted from it.

The segments keep the timings of their words, which highlight each word while
playing and are needed by the subtitles. When the text of a segment changes, the
words that didn't change are kept as they are, and the new ones take the timings
of the words they replace.

The corrected words keep the score of the words they replace, marked as edited
(see `models.review`), so a review counts them as reviewed instead of dropping
them. A word split in several (or several merged into one) is counted once: only
the first new word keeps the (lowest) score. Inserted words have no score.
"""

import difflib
import re
from dataclasses import replace

from models.transcript_segment import ReviewMark, TranscriptSegment, TranscriptWord


def _pattern(find: str, match_case: bool) -> re.Pattern[str]:
    return re.compile(re.escape(find), 0 if match_case else re.IGNORECASE)


def replace_text(
    text: str, find: str, replacement: str, match_case: bool = False
) -> str:
    if not find:
        return text

    # A function, so the replacement is inserted as it is (e.g. with backslashes)
    return _pattern(find, match_case).sub(lambda _match: replacement, text)


def realign_words(
    words: tuple[TranscriptWord, ...], new_text: str
) -> tuple[TranscriptWord, ...]:
    """
    Keeps the timings of the words of a segment whose text has changed.

    :param words: The words of the segment before the change.
    :param new_text: The new text of the segment.
    :return: The words of the new text, with their timings and their scores.
    """
    if not words:
        return ()

    new_tokens = new_text.split()
    matcher = difflib.SequenceMatcher(
        a=[word.text for word in words], b=new_tokens, autojunk=False
    )
    result: list[TranscriptWord] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            result.extend(words[i1:i2])
        elif tag == "replace" and i2 - i1 == j2 - j1:
            # Each word corrected on its own keeps its timing and its score
            result.extend(
                _edited(token, word.start, word.end, word.score)
                for word, token in zip(words[i1:i2], new_tokens[j1:j2], strict=True)
            )
        elif tag == "replace":
            # Split or merged: the new words share the time of the words they
            # replace, and the first one keeps their lowest score
            start, end = words[i1].start, words[i2 - 1].end
            step = (end - start) / (j2 - j1)
            scores = [word.score for word in words[i1:i2] if word.score is not None]
            result.extend(
                _edited(
                    token,
                    start + step * idx,
                    start + step * (idx + 1),
                    min(scores) if scores and idx == 0 else None,
                    is_scored=bool(scores),
                )
                for idx, token in enumerate(new_tokens[j1:j2])
            )
        elif tag == "insert":
            # Inserted words take no time, at the end of the previous word
            position = result[-1].end if result else words[0].start
            result.extend(
                TranscriptWord(position, position, token) for token in new_tokens[j1:j2]
            )

    return tuple(result)


def _edited(
    text: str,
    start: float,
    end: float,
    score: float | None,
    is_scored: bool | None = None,
) -> TranscriptWord:
    """
    A word corrected by the user. It's marked as edited if it replaces a scored
    word, so it's reviewed, and no longer highlighted.

    :param is_scored: Whether the words it replaces have a score, if it doesn't
        keep it (e.g. the second half of a split word).
    """
    is_scored = score is not None if is_scored is None else is_scored
    return TranscriptWord(
        start, end, text, score, ReviewMark.EDITED if is_scored else None
    )


def _with_text(segment: TranscriptSegment, text: str) -> TranscriptSegment:
    text = text.strip()
    if text == segment.text:
        return segment

    # A scored segment keeps its score, reviewed, as the user corrected it
    return replace(
        segment,
        text=text,
        words=realign_words(segment.words, text),
        reviewed=ReviewMark.EDITED if segment.score is not None else segment.reviewed,
    )


def replace_in_segments(
    segments: list[TranscriptSegment],
    find: str,
    replacement: str,
    match_case: bool = False,
) -> list[TranscriptSegment]:
    return [
        _with_text(segment, replace_text(segment.text, find, replacement, match_case))
        for segment in segments
    ]


def edit_segment(
    segments: list[TranscriptSegment], idx: int, text: str
) -> list[TranscriptSegment]:
    """
    Changes the text of a segment.

    :raises ValueError: If the text is empty.
    """
    if not text.strip():
        raise ValueError("The text of a segment can't be empty")

    return [
        _with_text(segment, text) if segment_idx == idx else segment
        for segment_idx, segment in enumerate(segments)
    ]


def word_range(segment: TranscriptSegment, word_idx: int) -> tuple[int, int] | None:
    """
    Where a word is in the text of its segment. Words are looked up in order, like
    when they're shown, so the same word said twice is told apart.

    :return: Its start and its end in the text, or `None` if it isn't there.
    """
    text = segment.text
    cursor = 0
    for idx, word in enumerate(segment.words):
        position = text.find(word.text, cursor) if word.text else -1
        if position < 0:
            continue
        if idx == word_idx:
            return position, position + len(word.text)
        cursor = position + len(word.text)
    return None


def edit_word(
    segments: list[TranscriptSegment], idx: int, word_idx: int, text: str
) -> list[TranscriptSegment]:
    """
    Changes a word of a segment.

    :raises ValueError: If the word isn't in the text, or `text` is empty: a word
        is removed by editing its segment.
    """
    found = word_range(segments[idx], word_idx)
    if found is None:
        raise ValueError("The word isn't in the text of its segment")
    if not text.strip():
        raise ValueError("The text of a word can't be empty")

    first, last = found
    segment_text = segments[idx].text
    return edit_segment(
        segments, idx, segment_text[:first] + text.strip() + segment_text[last:]
    )


def edit_segment_part(
    segments: list[TranscriptSegment], idx: int, first: int, last: int, text: str
) -> list[TranscriptSegment]:
    """
    Changes a part of the text of a segment (e.g. the one shown as a subtitle),
    keeping the rest of it.

    :param first: The start of the part in the text of the segment.
    :param last: The end of the part in the text of the segment.
    :raises ValueError: If the text is empty.
    """
    if not text.strip():
        raise ValueError("The text of a segment can't be empty")

    segment_text = segments[idx].text
    return edit_segment(
        segments, idx, segment_text[:first] + text.strip() + segment_text[last:]
    )


def replace_range(
    segments: list[TranscriptSegment],
    idx: int,
    first: int,
    last: int,
    replacement: str,
    allow_empty: bool = False,
) -> list[TranscriptSegment]:
    """
    Replaces a range of the text of a segment, e.g. a match of a search.

    :param allow_empty: Whether the segment can be left without text, e.g. one of
                        a translation, which can be translated later.
    :raises ValueError: If the segment is left without text, and it can't be.
    """
    text = segments[idx].text
    new_text = text[:first] + replacement + text[last:]
    if not new_text.strip() and not allow_empty:
        raise ValueError("The text of a segment can't be empty")

    return [
        _with_text(segment, new_text) if segment_idx == idx else segment
        for segment_idx, segment in enumerate(segments)
    ]


def split_segment(
    segments: list[TranscriptSegment], idx: int, pieces: list[TranscriptSegment]
) -> list[TranscriptSegment]:
    """
    Replaces a segment with its pieces (e.g. the parts shown as subtitles), so
    each of them can be changed on its own.
    """
    return [*segments[:idx], *pieces, *segments[idx + 1 :]]


def set_segment_timing(
    segments: list[TranscriptSegment], idx: int, start: float, end: float
) -> list[TranscriptSegment]:
    """
    Changes when a segment starts and ends, keeping the segments sorted by their
    start. The timings of its words no longer apply, so they're dropped.

    :raises ValueError: If it doesn't end after it starts.
    """
    if start < 0 or end <= start:
        raise ValueError("A segment must end after it starts")

    changed = replace(segments[idx], start=start, end=end, words=())
    return sorted_segments(
        [changed if segment_idx == idx else s for segment_idx, s in enumerate(segments)]
    )


def insert_segment(
    segments: list[TranscriptSegment], segment: TranscriptSegment
) -> list[TranscriptSegment]:
    """
    Adds a segment, keeping the segments sorted by their start.

    :raises ValueError: If it doesn't end after it starts.
    """
    if segment.start < 0 or segment.end <= segment.start:
        raise ValueError("A segment must end after it starts")

    return sorted_segments([*segments, segment])


def delete_segment(
    segments: list[TranscriptSegment], idx: int
) -> list[TranscriptSegment]:
    """Removes a segment, keeping the order of the others."""
    return [
        segment for segment_idx, segment in enumerate(segments) if segment_idx != idx
    ]


def sorted_segments(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    """Sorts the segments by their start, keeping the order of the ones that tie."""
    return sorted(segments, key=lambda segment: segment.start)


def overlapping_segments(
    segments: list[TranscriptSegment], start: float, end: float
) -> list[TranscriptSegment]:
    """
    The segments said between two positions, e.g. the ones of the transcription
    that a segment of its translation translates.
    """
    return [s for s in segments if s.start < end and s.end > start]


def speakers(segments: list[TranscriptSegment]) -> list[str]:
    """The speakers of the transcription, in the order they first speak."""
    return list(dict.fromkeys(s.speaker for s in segments if s.speaker))


def rename_speakers(
    segments: list[TranscriptSegment], names: dict[str, str]
) -> list[TranscriptSegment]:
    """
    Gives the speakers other names, all at once, so two speakers can swap their
    names. Giving two speakers the same name merges them.

    :param names: The new name of each renamed speaker.
    """
    names = {old: new.strip() for old, new in names.items()}
    if not all(names.values()):
        raise ValueError("The name of a speaker can't be empty")

    return [
        replace(s, speaker=names[s.speaker]) if s.speaker in names else s
        for s in segments
    ]


def rename_speakers_in_text(text: str, names: dict[str, str]) -> str:
    """Renames the speakers in the labels of a text (e.g. "[SPEAKER_00]: Hello")."""
    if not names:
        return text

    pattern = re.compile(r"\[(" + "|".join(re.escape(name) for name in names) + r")\]:")
    return pattern.sub(lambda match: f"[{names[match[1]].strip()}]:", text)
