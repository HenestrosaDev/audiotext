import pytest

from models.transcript_segment import TranscriptSegment, TranscriptWord
from utils.transcript_editing import (
    count_matches,
    delete_segment,
    edit_segment,
    insert_segment,
    overlapping_segments,
    realign_words,
    rename_speakers,
    rename_speakers_in_text,
    replace_in_segments,
    replace_text,
    set_segment_timing,
    speakers,
)

WORDS = (
    TranscriptWord(0.0, 0.5, "Hello"),
    TranscriptWord(0.5, 1.0, "wisper"),
    TranscriptWord(1.0, 1.5, "users."),
)


def test_count_matches_ignores_the_case_by_default() -> None:
    assert count_matches("Wisper and wisper", "wisper") == 2
    assert count_matches("Wisper and wisper", "wisper", match_case=True) == 1
    assert count_matches("text", "") == 0


def test_replace_text_inserts_the_replacement_literally() -> None:
    assert replace_text("a.b a.b", "a.b", r"c\1") == r"c\1 c\1"
    assert replace_text("Cat cat", "cat", "dog", match_case=True) == "Cat dog"


def test_realign_words_keeps_the_timings_of_the_unchanged_words() -> None:
    words = realign_words(WORDS, "Hello Whisper users.")

    assert words == (
        TranscriptWord(0.0, 0.5, "Hello"),
        TranscriptWord(0.5, 1.0, "Whisper"),
        TranscriptWord(1.0, 1.5, "users."),
    )


def test_realign_words_splits_the_time_of_the_replaced_words() -> None:
    words = realign_words(WORDS, "Hello Whisper X users.")

    assert words[1:3] == (
        TranscriptWord(0.5, 0.75, "Whisper"),
        TranscriptWord(0.75, 1.0, "X"),
    )


def test_realign_words_with_inserted_and_deleted_words() -> None:
    assert realign_words(WORDS, "Oh Hello users.") == (
        TranscriptWord(0.0, 0.0, "Oh"),
        TranscriptWord(0.0, 0.5, "Hello"),
        TranscriptWord(1.0, 1.5, "users."),
    )
    assert realign_words((), "Anything") == ()


def test_replace_in_segments_updates_the_text_and_the_words() -> None:
    segments = [
        TranscriptSegment(0.0, 1.5, "Hello wisper users.", words=WORDS),
        TranscriptSegment(2.0, 3.0, "Nothing to change."),
    ]

    result = replace_in_segments(segments, "WISPER", "Whisper")

    assert result[0].text == "Hello Whisper users."
    assert [word.text for word in result[0].words] == ["Hello", "Whisper", "users."]
    assert result[1] is segments[1]


def test_edit_segment() -> None:
    segments = [
        TranscriptSegment(0.0, 1.5, "Hello wisper users.", words=WORDS),
        TranscriptSegment(2.0, 3.0, "Bye."),
    ]

    result = edit_segment(segments, 0, " Hello Whisper users. ")

    assert result[0].text == "Hello Whisper users."
    assert result[0].words[1] == TranscriptWord(0.5, 1.0, "Whisper")
    assert result[1] is segments[1]
    with pytest.raises(ValueError):
        edit_segment(segments, 0, "  ")


def test_rename_speakers() -> None:
    segments = [
        TranscriptSegment(0, 1, "Hi.", "SPEAKER_00"),
        TranscriptSegment(1, 2, "Hello.", "SPEAKER_01"),
        TranscriptSegment(2, 3, "Bye.", "SPEAKER_00"),
        TranscriptSegment(3, 4, "Hmm.", "SPEAKER_02"),
    ]

    result = rename_speakers(segments, {"SPEAKER_00": " Ana "})

    assert speakers(result) == ["Ana", "SPEAKER_01", "SPEAKER_02"]
    assert result[1] is segments[1]
    with pytest.raises(ValueError):
        rename_speakers(segments, {"SPEAKER_00": ""})


def test_rename_speakers_can_swap_and_merge_them() -> None:
    segments = [
        TranscriptSegment(0, 1, "Hi.", "A"),
        TranscriptSegment(1, 2, "Hello.", "B"),
        TranscriptSegment(2, 3, "Hmm.", "C"),
    ]

    result = rename_speakers(segments, {"A": "B", "B": "A", "C": "A"})

    assert [segment.speaker for segment in result] == ["B", "A", "A"]


def test_rename_speakers_in_text() -> None:
    text = "[SPEAKER_00]: Hi.\n\n[SPEAKER_01]: SPEAKER_00 said hi."

    assert rename_speakers_in_text(
        text, {"SPEAKER_00": "SPEAKER_01", "SPEAKER_01": "Ana"}
    ) == ("[SPEAKER_01]: Hi.\n\n[Ana]: SPEAKER_00 said hi.")
    assert rename_speakers_in_text(text, {}) == text


TIMED = [
    TranscriptSegment(0.0, 1.0, "One", "SPEAKER_00", WORDS[:1]),
    TranscriptSegment(1.5, 3.0, "Two"),
    TranscriptSegment(3.5, 5.0, "Three"),
]


def test_set_segment_timing_keeps_the_segments_sorted() -> None:
    segments = set_segment_timing(TIMED, 0, 4.0, 4.5)

    assert [s.text for s in segments] == ["Two", "Three", "One"]
    # The timings of its words no longer apply
    assert segments[2] == TranscriptSegment(4.0, 4.5, "One", "SPEAKER_00")


def test_set_segment_timing_needs_it_to_end_after_it_starts() -> None:
    with pytest.raises(ValueError):
        set_segment_timing(TIMED, 0, 1.0, 1.0)
    with pytest.raises(ValueError):
        set_segment_timing(TIMED, 0, -1.0, 1.0)


def test_insert_and_delete_segments() -> None:
    added = TranscriptSegment(3.0, 3.5, "")
    segments = insert_segment(TIMED, added)

    assert segments[2] is added
    assert delete_segment(segments, 2) == TIMED
    with pytest.raises(ValueError):
        insert_segment(TIMED, TranscriptSegment(3.0, 2.0, ""))


def test_overlapping_segments() -> None:
    assert [s.text for s in overlapping_segments(TIMED, 0.5, 2.0)] == ["One", "Two"]
    # Touching a segment isn't overlapping it
    assert overlapping_segments(TIMED, 1.0, 1.5) == []
