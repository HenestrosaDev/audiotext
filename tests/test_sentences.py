import pytest

from models.transcript_segment import TranscriptSegment, TranscriptWord
from utils.sentences import (
    MAX_PAUSE_SECONDS,
    MAX_SENTENCE_CHARS,
    MAX_SENTENCE_SECONDS,
    group_by_sentence,
)


def words(*items: tuple[float, float, str]) -> tuple[TranscriptWord, ...]:
    return tuple(TranscriptWord(*item) for item in items)


def test_a_sentence_split_across_segments_is_merged() -> None:
    segments = [
        TranscriptSegment(0.0, 2.0, "This is a significant advance in the"),
        TranscriptSegment(2.0, 4.0, "field of medicine."),
        TranscriptSegment(4.5, 6.0, "Next one."),
    ]

    assert group_by_sentence(segments) == [
        TranscriptSegment(
            0.0, 4.0, "This is a significant advance in the field of medicine."
        ),
        TranscriptSegment(4.5, 6.0, "Next one."),
    ]


def test_a_segment_is_split_where_its_words_end_a_sentence() -> None:
    segments = [
        TranscriptSegment(
            0.0,
            3.0,
            "It works. And then",
            words=words(
                (0.0, 0.5, "It"),
                (0.6, 1.0, "works."),
                (1.8, 2.0, "And"),
                (2.1, 2.8, "then"),
            ),
        ),
        TranscriptSegment(
            3.0, 4.0, "it stops!", words=words((3.0, 3.4, "it"), (3.5, 4.0, "stops!"))
        ),
    ]

    result = group_by_sentence(segments)

    assert [(s.start, s.end, s.text) for s in result] == [
        (0.0, 1.0, "It works."),
        (1.8, 4.0, "And then it stops!"),
    ]
    assert [w.text for w in result[1].words] == ["And", "then", "it", "stops!"]


def test_without_words_the_timings_are_shared_by_length() -> None:
    result = group_by_sentence([TranscriptSegment(0.0, 10.0, "Ab cd. Ef g.")])

    assert [(s.start, s.end, s.text) for s in result] == [
        (0.0, 5.0, "Ab cd."),
        (5.0, 10.0, "Ef g."),
    ]


def test_speakers_abbreviations_and_numbers_dont_end_sentences_wrongly() -> None:
    segments = [
        TranscriptSegment(0.0, 1.0, "The U.S. economy grew 3.5", "SPEAKER_00"),
        TranscriptSegment(1.0, 2.0, "percent and", "SPEAKER_00"),
        TranscriptSegment(2.0, 3.0, "Really?", "SPEAKER_01"),
    ]

    assert [(s.text, s.speaker) for s in group_by_sentence(segments)] == [
        ("The U.S. economy grew 3.5 percent and", "SPEAKER_00"),
        ("Really?", "SPEAKER_01"),
    ]


def test_full_width_punctuation_ends_sentences() -> None:
    result = group_by_sentence(
        [
            TranscriptSegment(0.0, 1.0, "你好。我很好"),
            TranscriptSegment(1.0, 2.0, "谢谢。"),
        ]
    )

    assert [s.text for s in result] == ["你好。", "我很好 谢谢。"]


def test_a_sentence_that_never_ends_is_cut_where_a_segment_ends() -> None:
    text = "word " * 50
    segments = [TranscriptSegment(i, i + 1, text.strip()) for i in range(6)]

    result = group_by_sentence(segments)

    assert len(result) > 1
    assert all(len(s.text) < MAX_SENTENCE_CHARS + len(text) for s in result)
    assert " ".join(s.text for s in result) == " ".join(s.text for s in segments)


def test_empty_segments_are_dropped() -> None:
    assert group_by_sentence(
        [TranscriptSegment(0.0, 1.0, "  "), TranscriptSegment(1.0, 2.0, "Hi.")]
    ) == [TranscriptSegment(1.0, 2.0, "Hi.")]


@pytest.mark.parametrize(
    "text",
    [
        "Dr. Smith said hi.",
        "Mr. Jones and Mrs. Jones said hi.",
        "It was Spain vs. France tonight.",
        "J. R. R. Tolkien said hi.",
        "The U.S. Army said hi.",
        "La Sra. García dijo hola.",
    ],
)
def test_abbreviations_dont_end_sentences(text: str) -> None:
    assert [s.text for s in group_by_sentence([TranscriptSegment(0, 1, text)])] == [
        text
    ]


def test_a_period_after_a_regular_word_still_ends_a_sentence() -> None:
    result = group_by_sentence(
        [TranscriptSegment(0, 1, "I saw the doctor. Smith too.")]
    )

    assert [s.text for s in result] == ["I saw the doctor.", "Smith too."]


def test_a_long_silence_ends_a_sentence() -> None:
    segments = [
        TranscriptSegment(0.0, 1.0, "And then"),
        TranscriptSegment(1.0 + MAX_PAUSE_SECONDS, 3.0, "we left."),
    ]

    assert [s.text for s in group_by_sentence(segments)] == ["And then", "we left."]


def test_a_short_pause_in_a_sentence_doesnt_cut_it() -> None:
    segment = TranscriptSegment(
        0.0,
        3.0,
        "It was a big advance.",
        words=words(
            (0.0, 0.5, "It"),
            (0.5, 0.8, "was"),
            (0.8, 1.0, "a"),
            (2.0, 2.4, "big"),
            (2.4, 3.0, "advance."),
        ),
    )

    assert [s.text for s in group_by_sentence([segment])] == ["It was a big advance."]


def test_a_long_unpunctuated_sentence_is_cut_at_a_pause() -> None:
    # Unpunctuated speech: a word every second, with a pause after the 20th
    items = [(float(i), i + 0.5, f"w{i}") for i in range(20)]
    items += [(20.5, 21.0, "w20"), (21.0, 21.5, "w21")]
    segment = TranscriptSegment(
        0.0, 21.5, " ".join(text for *_, text in items), words=words(*items)
    )

    result = group_by_sentence([segment])

    # The pauses of half a second between the first words are too short
    assert [(s.start, s.end) for s in result] == [(0.0, 19.5), (20.5, 21.5)]
    assert result[1].text == "w20 w21"


def test_a_long_sentence_without_words_is_cut_where_a_segment_ends() -> None:
    segments = [TranscriptSegment(i * 5.0, i * 5.0 + 5, f"part {i}") for i in range(5)]

    result = group_by_sentence(segments)

    assert [(s.start, s.end) for s in result] == [(0.0, 15.0), (15.0, 25.0)]
    assert MAX_SENTENCE_SECONDS == 15.0
