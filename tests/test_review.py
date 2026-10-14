import pytest

from models.review import (
    FlaggedText,
    ReviewState,
    build_review,
    flagged_texts,
    review_key,
    step_to,
)
from models.transcript_segment import TranscriptSegment, TranscriptWord

SEGMENTS = [
    TranscriptSegment(
        0.0,
        1.0,
        "Hello wisper",
        words=(
            TranscriptWord(0.0, 0.5, "Hello", 0.9),
            TranscriptWord(0.5, 1.0, "wisper", 0.3),
        ),
    ),
    # Only its segment is scored (e.g. by the OpenAI API)
    TranscriptSegment(1.5, 3.0, "Nice to meet you.", score=0.2),
    TranscriptSegment(
        3.5,
        5.0,
        "Bye now.",
        words=(
            TranscriptWord(3.5, 4.0, "Bye", 0.35),
            # Not aligned, so it has no score
            TranscriptWord(4.0, 4.0, "now."),
        ),
    ),
]


def texts(review_texts: tuple[FlaggedText, ...] | list[FlaggedText]) -> list[str]:
    return [text.text for text in review_texts]


def test_the_words_and_the_segments_below_the_score_are_flagged() -> None:
    flagged = flagged_texts(SEGMENTS, 0.4)

    assert texts(flagged) == ["wisper", "Nice to meet you.", "Bye"]
    assert [(text.segment_idx, text.word_idx) for text in flagged] == [
        (0, 1),
        (1, None),
        (2, 0),
    ]
    assert flagged[0].key == review_key(0.5, "wisper") == "500:wisper"


def test_a_segment_isnt_flagged_if_its_words_are_scored() -> None:
    segment = TranscriptSegment(
        0, 1, "Hello", words=(TranscriptWord(0, 1, "Hello", 0.9),), score=0.1
    )

    assert flagged_texts([segment], 0.4) == []


def test_the_threshold_changes_the_flagged_texts() -> None:
    assert texts(flagged_texts(SEGMENTS, 0.25)) == ["Nice to meet you."]
    assert texts(flagged_texts(SEGMENTS, 0.95)) == [
        "Hello",
        "wisper",
        "Nice to meet you.",
        "Bye",
    ]


def test_the_counter_leaves_out_the_reviewed_texts() -> None:
    review = build_review(SEGMENTS, True, 0.4, {review_key(0.5, "wisper")})

    assert review.state == ReviewState.ACTIVE
    assert (review.remaining, review.total) == (2, 3)
    assert texts(review.unreviewed) == ["Nice to meet you.", "Bye"]


def test_the_reviewed_texts_dont_count_at_another_threshold() -> None:
    reviewed = {review_key(0.5, "wisper")}

    review = build_review(SEGMENTS, True, 0.25, reviewed)

    assert (review.remaining, review.total) == (1, 1)


@pytest.mark.parametrize(
    ("segments", "is_highlighted", "min_score", "reviewed", "state"),
    [
        ([TranscriptSegment(0, 1, "Hello")], True, 0.4, set(), ReviewState.NO_DATA),
        # Without scores, there's nothing to turn on
        ([TranscriptSegment(0, 1, "Hello")], False, 0.4, set(), ReviewState.NO_DATA),
        (SEGMENTS, False, 0.4, set(), ReviewState.OFF),
        (SEGMENTS, True, 0.1, set(), ReviewState.NOTHING_FLAGGED),
        (SEGMENTS, True, 0.4, set(), ReviewState.ACTIVE),
        (
            SEGMENTS,
            True,
            0.4,
            {"500:wisper", "1500:Nice to meet you.", "3500:Bye"},
            ReviewState.ALL_REVIEWED,
        ),
    ],
)
def test_the_state_of_the_review(
    segments: list[TranscriptSegment],
    is_highlighted: bool,
    min_score: float,
    reviewed: set[str],
    state: ReviewState,
) -> None:
    review = build_review(segments, is_highlighted, min_score, reviewed)

    assert review.state == state
    # Only a review with flagged texts counts them
    if state not in (ReviewState.ACTIVE, ReviewState.ALL_REVIEWED):
        assert (review.remaining, review.total) == (0, 0)


def test_step_to_goes_around() -> None:
    flagged = flagged_texts(SEGMENTS, 0.4)
    first, second, last = flagged

    assert step_to(flagged, first, 0, 1) == second
    assert step_to(flagged, last, 0, 1) == first
    assert step_to(flagged, first, 0, -1) == last
    assert step_to([], None, 0, 1) is None


def test_step_to_starts_from_the_position_of_the_player() -> None:
    flagged = flagged_texts(SEGMENTS, 0.4)

    def text_from(position: float, step: int) -> str | None:
        text = step_to(flagged, None, position, step)
        return text.text if text else None

    assert text_from(0.0, 1) == "wisper"
    assert text_from(2.0, 1) == "Bye"
    assert text_from(2.0, -1) == "Nice to meet you."
    # After the last one, it goes around
    assert text_from(9.0, 1) == "wisper"


def test_step_to_starts_from_a_text_no_longer_flagged() -> None:
    flagged = flagged_texts(SEGMENTS, 0.4)
    reviewed = flagged[1]
    unreviewed = [flagged[0], flagged[2]]

    assert step_to(unreviewed, reviewed, 0, 1) == flagged[2]
    assert step_to(unreviewed, reviewed, 0, -1) == flagged[0]
