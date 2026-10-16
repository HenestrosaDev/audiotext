from models.history import HistoryEntry
from models.transcript_segment import TranscriptSegment
from models.translation import TranscriptTranslation


def translation(*segments: TranscriptSegment, text: str = "") -> TranscriptTranslation:
    return TranscriptTranslation("es", text, segments, "manual")


def test_the_progress_counts_the_segments_with_a_text() -> None:
    assert translation(
        TranscriptSegment(0.0, 2.0, ""), TranscriptSegment(2.0, 3.0, "")
    ).segment_progress() == (0, 2)
    assert translation(
        TranscriptSegment(0.0, 2.0, "Uno dos tres"), TranscriptSegment(2.0, 3.0, "")
    ).segment_progress() == (1, 2)
    assert translation(
        TranscriptSegment(0.0, 2.0, "Uno"), TranscriptSegment(2.0, 3.0, "Cuatro")
    ).segment_progress() == (2, 2)


def test_whitespace_is_not_a_text() -> None:
    assert translation(TranscriptSegment(0.0, 1.0, " \n")).segment_progress() == (0, 1)


def test_an_empty_segment_is_left_even_if_another_is_retimed_over_it() -> None:
    # Two sentences merged into one subtitle: the empty one is still shown as not
    # translated, so it's counted as left
    assert translation(
        TranscriptSegment(0.0, 3.0, "Todo"), TranscriptSegment(2.0, 3.0, "")
    ).segment_progress() == (1, 2)


def test_a_translation_without_segments_has_no_progress() -> None:
    assert translation(text="Hola").segment_progress() == (0, 0)


def test_the_single_translation_of_older_entries_is_kept() -> None:
    old = translation(TranscriptSegment(0.0, 2.0, "Uno")).to_dict()

    entry = HistoryEntry.from_dict(
        {"kind": "File", "source": "/a.mp3", "title": "a", "translation": old}
    )

    assert entry.translations == {"es": old}
    assert entry.get_translation("es") == TranscriptTranslation.from_dict(old)
    assert entry.get_translation("fr") is None
    assert "translation" not in entry.to_dict()


def test_the_label_and_the_hint_agree() -> None:
    from views.transcript.translation_panel import TranslationPanel, translation_label

    partial = translation(
        TranscriptSegment(0.0, 2.0, "Uno"),
        TranscriptSegment(2.0, 3.0, ""),
        TranscriptSegment(3.0, 4.0, " "),
    )
    assert translation_label(partial) == "Spanish · 1/3"
    # Rounded down, so 100% only when all of it is translated
    assert TranslationPanel._progress_note(partial) == "Translated: 1/3 · 33%"

    done = translation(TranscriptSegment(0.0, 2.5, "Todo"))
    assert translation_label(done) == "Spanish"
    # Shown even when it's all translated
    assert TranslationPanel._progress_note(done) == "Translated: 1/1 · 100%"

    # Without segments, the text is translated at once
    assert TranslationPanel._progress_note(translation(text="Hola")) == ""


def test_an_edited_text_of_older_versions_is_built_from_the_segments() -> None:
    from models.transcript_segment import join_segments

    segments = (TranscriptSegment(0.0, 1.0, "Uno"), TranscriptSegment(1.0, 2.0, "Dos"))
    old = {
        **translation(*segments).to_dict(),
        "text": "Editado",
        "is_text_edited": True,
    }

    loaded = TranscriptTranslation.from_dict(old)
    assert loaded is not None
    assert loaded.text == join_segments(list(segments))
    assert not loaded.is_text_edited

    entry = HistoryEntry.from_dict(
        {
            "kind": "File",
            "source": "/a.mp3",
            "title": "a",
            "text": "Edited",
            "is_text_edited": True,
            "segments": [segment.to_dict() for segment in segments],
        }
    )
    assert entry.text == join_segments(list(segments))
    assert not entry.is_text_edited

    # Without segments, the edited text is all there is
    entry = HistoryEntry.from_dict(
        {
            "kind": "File",
            "source": "/a.mp3",
            "title": "a",
            "text": "Edited",
            "is_text_edited": True,
        }
    )
    assert entry.text == "Edited"
    assert entry.is_text_edited
