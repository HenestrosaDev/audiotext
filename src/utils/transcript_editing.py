"""
Corrections of a transcription: replacing a text, renaming a speaker and editing
the text of a segment.

The segments keep the timings of their words, which highlight each word while
playing and are needed by the subtitles. When the text of a segment changes, the
words that didn't change keep their timings, and the new ones take the timings of
the words they replace.
"""

import difflib
import re

from models.transcript_segment import TranscriptSegment, TranscriptWord


def _pattern(find: str, match_case: bool) -> re.Pattern[str]:
    return re.compile(re.escape(find), 0 if match_case else re.IGNORECASE)


def count_matches(text: str, find: str, match_case: bool = False) -> int:
    if not find:
        return 0

    return len(_pattern(find, match_case).findall(text))


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
    :return: The words of the new text, with their timings.
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
            result.extend(
                TranscriptWord(word.start, word.end, token)
                for word, token in zip(words[i1:i2], new_tokens[j1:j2], strict=True)
            )
        elif tag == "replace":
            # The new words share the time of the words they replace
            start, end = words[i1].start, words[i2 - 1].end
            step = (end - start) / (j2 - j1)
            result.extend(
                TranscriptWord(start + step * idx, start + step * (idx + 1), token)
                for idx, token in enumerate(new_tokens[j1:j2])
            )
        elif tag == "insert":
            # Inserted words take no time, at the end of the previous word
            position = result[-1].end if result else words[0].start
            result.extend(
                TranscriptWord(position, position, token) for token in new_tokens[j1:j2]
            )

    return tuple(result)


def _with_text(segment: TranscriptSegment, text: str) -> TranscriptSegment:
    text = text.strip()
    if text == segment.text:
        return segment

    return TranscriptSegment(
        segment.start,
        segment.end,
        text,
        segment.speaker,
        realign_words(segment.words, text),
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
        TranscriptSegment(s.start, s.end, s.text, names[s.speaker], s.words)
        if s.speaker in names
        else s
        for s in segments
    ]


def rename_speakers_in_text(text: str, names: dict[str, str]) -> str:
    """Renames the speakers in the labels of a text (e.g. "[SPEAKER_00]: Hello")."""
    if not names:
        return text

    pattern = re.compile(r"\[(" + "|".join(re.escape(name) for name in names) + r")\]:")
    return pattern.sub(lambda match: f"[{names[match[1]].strip()}]:", text)
