from models.transcript_segment import TranscriptSegment, join_segments


def test_joins_the_text_of_the_segments() -> None:
    segments = [
        TranscriptSegment(0, 1, "Hello"),
        TranscriptSegment(1, 2, "world."),
    ]

    assert join_segments(segments) == "Hello world."


def test_starts_a_paragraph_when_the_speaker_changes() -> None:
    segments = [
        TranscriptSegment(0, 1, "Hi.", "SPEAKER_00"),
        TranscriptSegment(1, 2, "How are you?", "SPEAKER_00"),
        TranscriptSegment(2, 3, "Fine.", "SPEAKER_01"),
        TranscriptSegment(3, 4, "Good.", "SPEAKER_00"),
    ]

    assert join_segments(segments) == (
        "[SPEAKER_00]: Hi. How are you?\n\n[SPEAKER_01]: Fine.\n\n[SPEAKER_00]: Good."
    )


def test_segments_without_speaker_have_no_label() -> None:
    segments = [
        TranscriptSegment(0, 1, "Music.", None),
        TranscriptSegment(1, 2, "Hi.", "SPEAKER_00"),
    ]

    assert join_segments(segments) == "Music.\n\n[SPEAKER_00]: Hi."


def test_empty_transcription() -> None:
    assert join_segments([]) == ""
