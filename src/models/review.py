"""
The review of the low confidence texts of a transcription: the words that may be
wrong (or the whole segments, for the engines that only score segments), which
the user goes through to correct them or accept them as they are.

Whether a text was reviewed is kept in the transcription, on the word (or the
segment), so it's saved with it and follows the text when it's corrected (see
`ReviewMark` and `utils.transcript_editing`). Everything the interface shows of
the review (the counter, the highlights, the texts to go to) is derived from
`build_review`, so it always agrees.
"""

import bisect
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from enum import Enum

from models.transcript_segment import ReviewMark, TranscriptSegment, has_scores


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

    # Finds the text where the transcription is shown (see `review_key`)
    key: str
    segment_idx: int
    # `None` for a whole segment
    word_idx: int | None
    start: float
    end: float
    text: str
    # How the user reviewed it, if they did
    review: ReviewMark | None = None


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

    @property
    def accepted(self) -> tuple[FlaggedText, ...]:
        """The texts accepted as they are, which can be reviewed again."""
        return tuple(
            text for text in self.flagged if text.review == ReviewMark.ACCEPTED
        )


def review_key(start: float, text: str) -> str:
    """
    Identifies a text by when it starts (to the millisecond) and what it says, to
    find it among the parts of the segments shown (e.g. their subtitles).
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
                        word.reviewed,
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
                    segment.reviewed,
                )
            )

    # Stable, so the words of a segment keep their order if they start together
    flagged.sort(key=lambda text: text.start)
    return flagged


def build_review(
    segments: Sequence[TranscriptSegment], is_highlighted: bool, min_score: float
) -> Review:
    """
    :param is_highlighted: Whether the low confidence texts are highlighted.
    :param min_score: The score below which a text may be wrong.
    """
    # Without scores there's nothing to count, whatever the other options
    if not has_scores(list(segments)):
        return Review(ReviewState.NO_DATA)
    if not is_highlighted:
        return Review(ReviewState.OFF)

    flagged = tuple(flagged_texts(segments, min_score))
    if not flagged:
        return Review(ReviewState.NOTHING_FLAGGED)

    unreviewed = tuple(text for text in flagged if text.review is None)
    state = ReviewState.ACTIVE if unreviewed else ReviewState.ALL_REVIEWED
    return Review(state, flagged, unreviewed)


def set_review(
    segments: Sequence[TranscriptSegment],
    texts: Iterable[FlaggedText],
    mark: ReviewMark | None,
) -> list[TranscriptSegment]:
    """
    Marks how texts were reviewed, or that they weren't (`None`).

    :param texts: Flagged texts of these `segments`.
    :return: The segments with the texts marked.
    """
    marks: dict[int, dict[int | None, ReviewMark | None]] = {}
    for text in texts:
        marks.setdefault(text.segment_idx, {})[text.word_idx] = mark

    result = list(segments)
    for segment_idx, segment_marks in marks.items():
        segment = result[segment_idx]
        words = tuple(
            replace(word, reviewed=segment_marks[word_idx])
            if word_idx in segment_marks
            else word
            for word_idx, word in enumerate(segment.words)
        )
        result[segment_idx] = replace(
            segment,
            words=words,
            reviewed=segment_marks.get(None, segment.reviewed),
        )
    return result


def edited_count(segments: Sequence[TranscriptSegment]) -> int:
    """The texts that the user corrected, to tell if a correction reviewed one."""
    return sum(
        (segment.reviewed == ReviewMark.EDITED)
        + sum(word.reviewed == ReviewMark.EDITED for word in segment.words)
        for segment in segments
    )


def _without_reviews(segment: TranscriptSegment) -> TranscriptSegment:
    return replace(
        segment,
        words=tuple(replace(word, reviewed=None) for word in segment.words),
        reviewed=None,
    )


def differ_only_in_reviews(
    old: Sequence[TranscriptSegment], new: Sequence[TranscriptSegment]
) -> bool:
    """
    Whether two versions of a transcription only differ in their reviews, so its
    text doesn't need to be shown again. The segments that didn't change are
    usually the same objects, which is quick to compare.
    """
    return len(old) == len(new) and all(
        old_segment is new_segment
        or old_segment == new_segment
        or _without_reviews(old_segment) == _without_reviews(new_segment)
        for old_segment, new_segment in zip(old, new, strict=True)
    )


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
