from models.transcript_segment import TranscriptSegment, TranscriptWord, join_segments


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


def test_the_words_keep_their_score() -> None:
    segment = TranscriptSegment(
        0,
        1,
        "Hello world",
        words=(TranscriptWord(0, 0.5, "Hello", 0.9), TranscriptWord(0.5, 1, "world")),
    )

    data = segment.to_dict()

    assert data["words"] == [[0, 0.5, "Hello", 0.9], [0.5, 1, "world"]]
    assert TranscriptSegment.from_dict(data) == segment


def test_reads_the_words_saved_without_score() -> None:
    data = {"start": 0, "end": 1, "text": "Hello", "words": [[0, 1, "Hello"]]}

    segment = TranscriptSegment.from_dict(data)

    assert segment.words == (TranscriptWord(0, 1, "Hello"),)
