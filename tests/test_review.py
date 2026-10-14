import pytest

from models.review import (
    FlaggedText,
    ReviewState,
    build_review,
    differ_only_in_reviews,
    edited_count,
    flagged_texts,
    review_key,
    set_review,
    step_to,
)
from models.transcript_segment import ReviewMark, TranscriptSegment, TranscriptWord
from utils.transcript_editing import edit_segment

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
    flagged = build_review(SEGMENTS, True, 0.4).flagged
    segments = set_review(SEGMENTS, flagged[:2], ReviewMark.ACCEPTED)

    review = build_review(segments, True, 0.4)

    assert review.state == ReviewState.ACTIVE
    assert (review.remaining, review.total) == (1, 3)
    assert texts(review.unreviewed) == ["Bye"]
    assert texts(review.accepted) == ["wisper", "Nice to meet you."]


def test_set_review_marks_words_and_segments() -> None:
    flagged = build_review(SEGMENTS, True, 0.4).flagged

    segments = set_review(SEGMENTS, flagged, ReviewMark.ACCEPTED)

    assert segments[0].words[1].reviewed == ReviewMark.ACCEPTED
    assert segments[0].words[0].reviewed is None
    assert segments[1].reviewed == ReviewMark.ACCEPTED
    assert segments[2].words[0].reviewed == ReviewMark.ACCEPTED
    # And the marks can be cleared
    assert set_review(segments, flagged, None) == SEGMENTS


def test_the_reviews_are_kept_when_the_threshold_changes() -> None:
    flagged = build_review(SEGMENTS, True, 0.4).flagged
    segments = set_review(SEGMENTS, flagged[:1], ReviewMark.ACCEPTED)

    assert (build_review(segments, True, 0.25).remaining) == 1
    review = build_review(segments, True, 0.95)
    assert (review.remaining, review.total) == (3, 4)


def test_an_edited_word_never_needs_review_again() -> None:
    segments = edit_segment(SEGMENTS, 0, "Hello Whisper")

    review = build_review(segments, True, 0.4)

    assert texts(review.flagged)[0] == "Whisper"
    assert texts(review.unreviewed) == ["Nice to meet you.", "Bye"]
    # Only the accepted ones can be reviewed again
    assert review.accepted == ()


def test_unaligned_words_are_never_flagged() -> None:
    # WhisperX can't align some words (e.g. numbers), which have no score
    words = (TranscriptWord(0, 1, "In", 0.9), TranscriptWord(1, 1, "1984"))
    segment = TranscriptSegment(0, 1, "In 1984", words=words)

    # Not even below the highest threshold
    assert texts(build_review([segment], True, 1.0).flagged) == ["In"]


@pytest.mark.parametrize(
    ("segments", "is_highlighted", "min_score", "state"),
    [
        ([TranscriptSegment(0, 1, "Hello")], True, 0.4, ReviewState.NO_DATA),
        # Without scores, there's nothing to turn on
        ([TranscriptSegment(0, 1, "Hello")], False, 0.4, ReviewState.NO_DATA),
        (SEGMENTS, False, 0.4, ReviewState.OFF),
        (SEGMENTS, True, 0.1, ReviewState.NOTHING_FLAGGED),
        (SEGMENTS, True, 0.4, ReviewState.ACTIVE),
        (
            set_review(SEGMENTS, flagged_texts(SEGMENTS, 0.4), ReviewMark.ACCEPTED),
            True,
            0.4,
            ReviewState.ALL_REVIEWED,
        ),
    ],
)
def test_the_state_of_the_review(
    segments: list[TranscriptSegment],
    is_highlighted: bool,
    min_score: float,
    state: ReviewState,
) -> None:
    review = build_review(segments, is_highlighted, min_score)

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


def test_differ_only_in_reviews() -> None:
    reviewed = set_review(SEGMENTS, flagged_texts(SEGMENTS, 0.4), ReviewMark.ACCEPTED)

    assert differ_only_in_reviews(SEGMENTS, reviewed)
    assert not differ_only_in_reviews(SEGMENTS, edit_segment(SEGMENTS, 0, "Hi wisper"))
    assert not differ_only_in_reviews(SEGMENTS, SEGMENTS[:2])


def test_edited_count() -> None:
    assert edited_count(SEGMENTS) == 0
    # A word, and a segment scored whole
    segments = edit_segment(edit_segment(SEGMENTS, 0, "Hi wisper"), 1, "Nice.")
    assert edited_count(segments) == 2
