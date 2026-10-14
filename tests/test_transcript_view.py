from typing import Any

from models.history import EntryStatus, HistoryEntry
from models.transcript_segment import TranscriptSegment, TranscriptWord
from utils.enums import AudioSource
from views.transcript.transcript_view import low_confidence_hint

WORD = TranscriptWord(0, 1, "Hello")
SEGMENT = TranscriptSegment(0, 1, "Hello")


def make_entry(**kwargs: Any) -> HistoryEntry:
    values: dict[str, Any] = {
        "kind": AudioSource.FILE.value,
        "source": "/audio.mp3",
        "title": "Entry",
        "status": EntryStatus.DONE,
        "segments": [SEGMENT],
    }
    return HistoryEntry(**(values | kwargs))


def test_no_hint_if_the_transcription_has_scores() -> None:
    segment = TranscriptSegment(0, 1, "Hello", words=(TranscriptWord(0, 1, "Hi", 0.9),))

    assert low_confidence_hint(make_entry(segments=[segment])) is None


def test_whisperx_needs_the_word_level_timings() -> None:
    entry = make_entry(method="WhisperX", settings={"align_words": False})

    assert low_confidence_hint(entry) == (
        "Turn on “Word-level timings” and transcribe it again"
    )


def test_some_languages_have_no_alignment_model() -> None:
    entry = make_entry(method="WhisperX", settings={"align_words": True})

    assert low_confidence_hint(entry) == "There is no alignment model for its language"


def test_the_older_transcriptions_need_to_be_transcribed_again() -> None:
    aligned = TranscriptSegment(0, 1, "Hello", words=(WORD,))

    for entry in (
        make_entry(method="WhisperX", segments=[aligned]),
        make_entry(method="Whisper API", settings={"openai_model": "whisper-1"}),
    ):
        assert low_confidence_hint(entry) == "Transcribe it again to score its words"


def test_the_other_engines_dont_score_the_words() -> None:
    for entry in (
        make_entry(method="Google API", segments=[]),
        make_entry(
            method="Whisper API",
            settings={"openai_model": "gpt-4o-transcribe"},
            segments=[],
        ),
    ):
        assert low_confidence_hint(entry) == (
            "Only WhisperX and whisper-1 score the words"
        )
