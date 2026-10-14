"""
Regroups the segments of a transcription by sentence. Whisper often ends its
segments in the middle of a sentence, which can't be translated well on its own.
"""

import re
from dataclasses import dataclass
from itertools import pairwise

from models.transcript_segment import TranscriptSegment, TranscriptWord

# A sentence that never ends (e.g. a transcription without punctuation) is cut
# once it exceeds this length or duration: at the next pause between its words
# (see `MIN_PAUSE_SECONDS`), or else where a segment ends
MAX_SENTENCE_CHARS = 400
MAX_SENTENCE_SECONDS = 15.0
# A silence between two words this long is a pause where a long sentence can be
# cut. Shorter sentences aren't, since speakers often pause in the middle of one
MIN_PAUSE_SECONDS = 0.7
# A silence this long always ends a sentence, so that it isn't shown as a
# subtitle while nothing is said
MAX_PAUSE_SECONDS = 1.5

# Words written with a period that doesn't end the sentence (e.g. "Dr. Smith"),
# in lowercase. Single uppercase letters (e.g. "J. Smith" or "U.S.") are too
ABBREVIATIONS = frozenset(
    {
        # English
        "mr",
        "mrs",
        "ms",
        "dr",
        "prof",
        "jr",
        "sr",
        "st",
        "mt",
        "vs",
        "rev",
        "gen",
        "col",
        "capt",
        "lt",
        "sgt",
        "gov",
        "sen",
        "rep",
        "fig",
        "approx",
        # Spanish, Portuguese, French, Italian and German. Not "sta" or "sto",
        # which are also verbs in Italian
        "sra",
        "srta",
        "dra",
        "dña",
        "ud",
        "uds",
        "mme",
        "mlle",
        "sig",
        "dott",
        "hr",
        "fr",
        "nr",
    }
)

# The punctuation that ends a sentence, with the quotes and brackets that close
# it. Latin punctuation must be followed by a space or the end of the text (not
# "3.5" or "example.com"), but the full-width one of Chinese and Japanese is not
_SENTENCE_END = re.compile(
    r"(?:[.!?…؟।]+[\"'”’»)\]]*(?=\s|$))|(?:[。！？]+[”’」』）]*)"
)


@dataclass
class _Fragment:
    start: float
    end: float
    text: str
    speaker: str | None
    words: tuple[TranscriptWord, ...]
    ends_sentence: bool


def _sentence_ends(text: str) -> list[int]:
    """:return: The positions where each sentence of the text ends."""
    ends = []
    for match in _SENTENCE_END.finditer(text):
        rest = text[match.end() :].lstrip()
        # A lowercase letter follows abbreviations (e.g. "the U.S. economy")
        if rest and rest[0].islower():
            continue
        word = re.search(r"\w+$", text[: match.start()])
        if (
            match.group().startswith(".")
            and word
            and (
                word.group().lower() in ABBREVIATIONS
                or (len(word.group()) == 1 and word.group().isupper())
            )
        ):
            continue
        ends.append(match.end())
    return ends


def _fragments(segment: TranscriptSegment) -> list[_Fragment]:
    """
    Splits the segment where its sentences end and where its words pause. The
    fragments take the timings of their words, or a share of the segment as long
    as their text if it has no words.
    """
    text = segment.text
    ends = _sentence_ends(text)

    # The position of each word in the text, which keeps its spacing
    positions: list[tuple[TranscriptWord, int]] = []
    cursor = 0
    for word in segment.words:
        position = text.find(word.text, cursor) if word.text else -1
        if position >= 0:
            cursor = position + len(word.text)
            positions.append((word, position))

    pauses = [
        position
        for (previous, _), (word, position) in pairwise(positions)
        if word.start - previous.end >= MIN_PAUSE_SECONDS
    ]
    bounds = sorted({0, *ends, *pauses, len(text)})

    duration = segment.end - segment.start
    fragments = []
    for first, last in pairwise(bounds):
        fragment_text = text[first:last].strip()
        if not fragment_text:
            continue
        words = tuple(word for word, position in positions if first <= position < last)
        if words:
            start, end = words[0].start, words[-1].end
        else:
            start = segment.start + duration * first / len(text)
            end = segment.start + duration * last / len(text)
        fragments.append(
            _Fragment(
                start,
                end,
                fragment_text,
                segment.speaker,
                words,
                ends_sentence=last in ends,
            )
        )

    # The first and the last fragments keep the timings of the segment
    if fragments:
        fragments[0].start = segment.start
        fragments[-1].end = segment.end
    return fragments


def group_by_sentence(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    """
    Regroups the segments so that each one holds a sentence, with the timings of
    the parts it's made of. Segments of different speakers are never merged, a
    silence of `MAX_PAUSE_SECONDS` always ends a sentence, and one longer than
    `MAX_SENTENCE_CHARS` or `MAX_SENTENCE_SECONDS` is cut at a pause or where a
    segment ends.

    :return: The segments of the sentences, sorted by their start.
    """
    groups: list[list[_Fragment]] = []
    is_open = False
    for segment in segments:
        for fragment in _fragments(segment):
            current = groups[-1] if is_open else None
            if (
                current is None
                or current[-1].speaker != fragment.speaker
                or fragment.start - current[-1].end >= MAX_PAUSE_SECONDS
                or sum(len(f.text) + 1 for f in current) >= MAX_SENTENCE_CHARS
                or current[-1].end - current[0].start >= MAX_SENTENCE_SECONDS
            ):
                groups.append([fragment])
            else:
                current.append(fragment)
            is_open = not fragment.ends_sentence

    return [
        TranscriptSegment(
            start=group[0].start,
            end=group[-1].end,
            text=" ".join(fragment.text for fragment in group),
            speaker=group[0].speaker,
            words=tuple(word for fragment in group for word in fragment.words),
        )
        for group in groups
    ]
