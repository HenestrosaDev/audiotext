"""
The review of the low confidence texts of a transcription: the words that may be
wrong (or the whole segments, for the engines that only score segments), which
the user goes through to correct them or accept them as they are.

Everything the interface shows of the review (the counter, the highlights, the
texts to go to) is derived from `build_review`, so it always agrees.
"""

import bisect
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from enum import Enum

from models.transcript_segment import TranscriptSegment, has_scores


class ReviewState(Enum):
    # The transcription has no scores (e.g. its engine doesn't score the words)
    NO_DATA = "no_data"
    # The low confidence texts are not highlighted
    OFF = "off"
    # No text scores below the threshold
    NOTHING_FLAGGED = "nothing_flagged"
    # Some flagged texts haven't been reviewed
    ACTIVE = "active"
    # All the flagged texts have been reviewed
    ALL_REVIEWED = "all_reviewed"


@dataclass(frozen=True)
class FlaggedText:
    """A word that may be wrong, or a whole segment if only segments are scored."""

    # Identifies the text while the transcription changes (see `review_key`)
    key: str
    segment_idx: int
    # `None` for a whole segment
    word_idx: int | None
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Review:
    state: ReviewState
    # The flagged texts at the threshold, sorted by when they're said
    flagged: tuple[FlaggedText, ...] = ()
    # The flagged texts that haven't been reviewed, in the same order
    unreviewed: tuple[FlaggedText, ...] = ()

    @property
    def remaining(self) -> int:
        return len(self.unreviewed)

    @property
    def total(self) -> int:
        return len(self.flagged)


def review_key(start: float, text: str) -> str:
    """
    Identifies a text by when it starts (to the millisecond) and what it says,
    which don't change when other segments are edited, split or deleted.
    """
    return f"{round(start * 1000)}:{text}"


def flagged_texts(
    segments: Sequence[TranscriptSegment], min_score: float
) -> list[FlaggedText]:
    """
    :param min_score: The score below which a text may be wrong.
    :return: The words whose score is below `min_score`, and the segments whose
        score is, if their words have no scores. Sorted by when they're said.
    """
    flagged: list[FlaggedText] = []

    for segment_idx, segment in enumerate(segments):
        has_word_scores = False
        for word_idx, word in enumerate(segment.words):
            if word.score is None:
                continue
            has_word_scores = True
            if word.score < min_score:
                flagged.append(
                    FlaggedText(
                        review_key(word.start, word.text),
                        segment_idx,
                        word_idx,
                        word.start,
                        word.end,
                        word.text,
                    )
                )

        if (
            not has_word_scores
            and segment.text
            and segment.score is not None
            and segment.score < min_score
        ):
            flagged.append(
                FlaggedText(
                    review_key(segment.start, segment.text),
                    segment_idx,
                    None,
                    segment.start,
                    segment.end,
                    segment.text,
                )
            )

    # Stable, so the words of a segment keep their order if they start together
    flagged.sort(key=lambda text: text.start)
    return flagged


def build_review(
    segments: Sequence[TranscriptSegment],
    is_highlighted: bool,
    min_score: float,
    reviewed: Collection[str],
) -> Review:
    """
    :param is_highlighted: Whether the low confidence texts are highlighted.
    :param min_score: The score below which a text may be wrong.
    :param reviewed: The keys of the texts that the user reviewed.
    """
    # Without scores there's nothing to count, whatever the other options
    if not has_scores(list(segments)):
        return Review(ReviewState.NO_DATA)
    if not is_highlighted:
        return Review(ReviewState.OFF)

    flagged = tuple(flagged_texts(segments, min_score))
    if not flagged:
        return Review(ReviewState.NOTHING_FLAGGED)

    unreviewed = tuple(text for text in flagged if text.key not in reviewed)
    state = ReviewState.ACTIVE if unreviewed else ReviewState.ALL_REVIEWED
    return Review(state, flagged, unreviewed)


def step_to(
    texts: Sequence[FlaggedText],
    current: FlaggedText | None,
    position: float,
    step: int,
) -> FlaggedText | None:
    """
    The text to go to from the current one, going around at the end (and at the
    start).

    :param texts: The texts to go through, sorted by when they're said.
    :param current: The text that was gone to, if any. If it's no longer in
        `texts` (e.g. it was reviewed), the step starts from where it was.
    :param position: Where the player is, in seconds, to start from there if no
        text was gone to.
    :param step: 1 to go to the next text, -1 to go to the previous one.
    :return: The text, or `None` if there are none.
    """
    if not texts:
        return None

    if current is not None and current in texts:
        return texts[(texts.index(current) + step) % len(texts)]

    # The first text from there on, or the last one before it
    anchor = current.start if current is not None else position
    idx = bisect.bisect_left([text.start for text in texts], anchor)
    return texts[idx % len(texts)] if step > 0 else texts[(idx - 1) % len(texts)]
