from models.config.config_subtitles import ConfigSubtitles
from models.transcript_segment import TranscriptSegment, TranscriptWord
from utils.subtitle_cues import (
    Cue,
    CueTrack,
    SegmentPart,
    build_cues,
    line_limits,
    split_segments,
    uses_wide_characters,
)


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

    assert build_cues([segment], 11) == [
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


def test_words_added_at_the_end_are_shown_for_some_time() -> None:
    # An edit appends words with no time, at the end of the segment
    words = (
        TranscriptWord(0.0, 1.0, "Hello"),
        TranscriptWord(1.0, 2.0, "world."),
        TranscriptWord(2.0, 2.0, "Bye"),
        TranscriptWord(2.0, 2.0, "now"),
    )
    segment = TranscriptSegment(0.0, 2.0, "Hello world. Bye now", words=words)

    cues = build_cues([segment], 12)

    assert [cue.text for cue in cues] == ["Hello world.", "Bye now"]
    assert all(cue.start < cue.end for cue in cues)
    assert cues[-1].end == 2.0


def test_long_segment_with_words_is_split_into_lines() -> None:
    words = tuple(
        TranscriptWord(float(idx), idx + 0.5, word)
        for idx, word in enumerate(["one", "two", "three", "four", "five", "six"])
    )
    segment = TranscriptSegment(0.0, 6.0, "one two three four five six", words=words)

    assert build_cues([segment], 10, 2) == [
        Cue(0.0, 4.0, "one two\nthree four"),
        Cue(4.0, 6.0, "five six"),
    ]


def test_long_segment_without_words_is_split_into_lines() -> None:
    text = "one two three four five six"
    cues = build_cues([TranscriptSegment(0.0, 27.0, text)], 10, 2)

    assert [cue.text for cue in cues] == ["one two\nthree four", "five six"]
    assert (cues[1].start, cues[1].end) == (19.0, 27.0)


def test_no_line_is_longer_than_the_width() -> None:
    # Breaking at the spaces can take more lines than the length suggests
    text = "aaaaaa bbbbbb cccccc"
    cues = build_cues([TranscriptSegment(0.0, 3.0, text)], 10, 2)

    assert [cue.text for cue in cues] == ["aaaaaa\nbbbbbb", "cccccc"]


def test_segments_are_split_into_the_parts_of_their_subtitles() -> None:
    words = tuple(
        TranscriptWord(float(idx), idx + 0.5, word)
        for idx, word in enumerate(["one", "two", "three", "four", "five", "six"])
    )
    long_segment = TranscriptSegment(
        0.0, 6.0, " one two three four five six", "SPEAKER_00", words
    )
    short_segment = TranscriptSegment(7.0, 8.0, "Bye.")

    parts = split_segments([long_segment, short_segment], 10, 2)

    assert [(p.segment_idx, p.first, p.last) for p in parts] == [
        (0, 1, 19),
        (0, 20, 28),
        (1, 0, 4),
    ]
    first, second, third = (part.segment for part in parts)
    assert (first.start, first.end, first.text) == (0.0, 4.0, "one two three four")
    assert first.words == words[:4]
    assert first.speaker == "SPEAKER_00"
    assert (second.start, second.end, second.text) == (4.0, 6.0, "five six")
    assert second.words == words[4:]
    # A segment that fits in a subtitle is kept as it is
    assert third is short_segment


def test_wide_characters_are_detected_by_most_of_the_text() -> None:
    assert uses_wide_characters([TranscriptSegment(0, 1, "你好，世界。OK")])
    assert uses_wide_characters([TranscriptSegment(0, 1, "こんにちは")])
    assert uses_wide_characters([TranscriptSegment(0, 1, "안녕하세요")])
    assert not uses_wide_characters([TranscriptSegment(0, 1, "Hello, 世界")])
    assert not uses_wide_characters([])


def test_line_limits_follow_the_script_and_the_video() -> None:
    config = ConfigSubtitles(
        highlight_words=False,
        max_line_count=2,
        max_line_width=42,
        max_line_width_cjk=16,
        max_line_width_vertical=24,
        max_line_width_vertical_cjk=10,
    )
    latin = [TranscriptSegment(0, 1, "Hello there.")]
    chinese = [TranscriptSegment(0, 1, "你好，世界。")]

    assert line_limits(config, latin, is_vertical=False) == (42, 2)
    assert line_limits(config, chinese, is_vertical=False) == (16, 2)
    assert line_limits(config, latin, is_vertical=True) == (24, 2)
    assert line_limits(config, chinese, is_vertical=True) == (10, 2)
    config.max_line_count_vertical = 1
    assert line_limits(config, latin, is_vertical=True) == (24, 1)
    assert line_limits(config, latin, is_vertical=False) == (42, 2)


def test_segments_without_text_are_kept() -> None:
    # e.g. the segments of a translation that are not translated yet
    empty = TranscriptSegment(0.0, 1.0, "")

    assert split_segments([empty], 10, 1) == [SegmentPart(0, 0, 0, empty)]


def test_the_lines_of_a_subtitle_are_evened_out() -> None:
    text = "I cannot make my big entrance with one earring on."
    words = tuple(
        TranscriptWord(float(idx), idx + 0.5, word)
        for idx, word in enumerate(text.split())
    )

    cues = build_cues([TranscriptSegment(0.0, 10.0, text, words=words)], 42, 2)

    # Filling the first line would leave "earring on." alone below it
    assert [cue.text for cue in cues] == [
        "I cannot make my big\nentrance with one earring on."
    ]


def test_the_bottom_line_is_the_longer_one_if_they_cant_be_even() -> None:
    # "one two" and "six" are as uneven as "one" and "two six"
    cues = build_cues([TranscriptSegment(0.0, 2.0, "one two six")], 8, 2)

    assert [cue.text for cue in cues] == ["one\ntwo six"]


def test_text_without_spaces_is_not_broken_before_punctuation() -> None:
    cues = build_cues([TranscriptSegment(0.0, 1.0, "你好世界。再见")], 4, 1)

    # "。" stays with the character before it, so it doesn't start a line
    assert [cue.text for cue in cues] == ["你好世", "界。再见"]
