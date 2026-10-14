from models.history import HistoryEntry
from models.transcript_segment import TranscriptSegment, TranscriptWord
from models.translation import TranscriptTranslation

ORIGINAL = [
    TranscriptSegment(0.0, 2.0, "One two three"),
    TranscriptSegment(2.0, 3.0, "Four"),
]


def translation(*segments: TranscriptSegment, text: str = "") -> TranscriptTranslation:
    return TranscriptTranslation("es", text, segments, "manual")


def test_the_ratio_counts_the_words_of_the_translated_segments() -> None:
    assert (
        translation(
            TranscriptSegment(0.0, 2.0, ""), TranscriptSegment(2.0, 3.0, "")
        ).translated_ratio(ORIGINAL)
        == 0
    )
    assert (
        translation(
            TranscriptSegment(0.0, 2.0, "Uno dos tres"), TranscriptSegment(2.0, 3.0, "")
        ).translated_ratio(ORIGINAL)
        == 0.75
    )
    assert (
        translation(
            TranscriptSegment(0.0, 2.0, ""), TranscriptSegment(2.0, 3.0, "Cuatro")
        ).translated_ratio(ORIGINAL)
        == 0.25
    )


def test_the_ratio_follows_the_retimed_segments() -> None:
    # A single segment translates both of the transcription
    assert (
        translation(TranscriptSegment(0.5, 2.5, "Todo")).translated_ratio(ORIGINAL) == 1
    )


def test_the_ratio_counts_the_words_where_they_are_said() -> None:
    words = (
        TranscriptWord(0.0, 0.5, "One"),
        TranscriptWord(0.5, 1.0, "two"),
        TranscriptWord(1.0, 2.0, "three"),
    )
    original = [TranscriptSegment(0.0, 2.0, "One two three", words=words)]

    assert (
        translation(TranscriptSegment(0.0, 1.0, "Uno dos")).translated_ratio(original)
        == 2 / 3
    )


def test_a_translation_without_timestamps_is_translated_at_once() -> None:
    assert translation(text="Hola").translated_ratio(ORIGINAL) == 1
    assert translation(text="").translated_ratio(ORIGINAL) == 0
    assert translation(TranscriptSegment(0.0, 1.0, "Hola")).translated_ratio([]) == 0


def test_the_single_translation_of_older_entries_is_kept() -> None:
    old = translation(TranscriptSegment(0.0, 2.0, "Uno")).to_dict()

    entry = HistoryEntry.from_dict(
        {"kind": "File", "source": "/a.mp3", "title": "a", "translation": old}
    )

    assert entry.translations == {"es": old}
    assert entry.get_translation("es") == TranscriptTranslation.from_dict(old)
    assert entry.get_translation("fr") is None
    assert "translation" not in entry.to_dict()
