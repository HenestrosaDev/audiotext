from models.transcript_segment import TranscriptSegment, TranscriptWord
from utils.subtitle_cues import Cue, CueTrack, build_cues


def test_short_segments_are_one_cue_each() -> None:
    segments = [
        TranscriptSegment(0.0, 2.0, " Hello there."),
        TranscriptSegment(3.0, 4.0, "Bye."),
    ]

    assert build_cues(segments, 42) == [
        Cue(0.0, 2.0, "Hello there."),
        Cue(3.0, 4.0, "Bye."),
    ]


def test_long_segment_without_words_is_split_at_spaces() -> None:
    text = "one two three four five six"
    cues = build_cues([TranscriptSegment(0.0, 27.0, text)], 10)

    assert [cue.text for cue in cues] == ["one two", "three four", "five six"]
    assert cues[0].start == 0.0
    assert cues[-1].end == 27.0
    # The times follow the position of each part in the text
    assert (cues[1].start, cues[1].end) == (8.0, 19.0)


def test_text_without_spaces_is_split_by_length() -> None:
    cues = build_cues([TranscriptSegment(0.0, 1.0, "一二三四五六七")], 3)

    assert [cue.text for cue in cues] == ["一二三", "四五六", "七"]


def test_long_segment_with_words_starts_each_cue_with_its_word() -> None:
    words = (
        TranscriptWord(0.5, 1.0, "Hello"),
        TranscriptWord(1.2, 1.6, "big"),
        TranscriptWord(2.0, 2.5, "wide"),
        TranscriptWord(3.0, 3.5, "world"),
    )
    segment = TranscriptSegment(0.0, 4.0, "Hello big wide world!", words=words)

    assert build_cues([segment], 10) == [
        Cue(0.0, 2.0, "Hello big"),
        Cue(2.0, 4.0, "wide world!"),
    ]


def test_track_finds_the_cue_being_shown() -> None:
    track = CueTrack([Cue(1.0, 2.0, "a"), Cue(3.0, 4.0, "b")])

    assert track.at(0.5) is None
    assert track.at(1.5) == Cue(1.0, 2.0, "a")
    assert track.at(2.5) is None
    assert track.at(3.0) == Cue(3.0, 4.0, "b")
    assert track.at(4.0) is None
