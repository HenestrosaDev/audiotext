from models.transcript_segment import TranscriptWord
from views.transcript.transcript_text import is_low_confidence


def test_only_the_words_below_the_score_are_low_confidence() -> None:
    assert is_low_confidence(TranscriptWord(0, 1, "Hi", 0.3), 0.4)
    assert not is_low_confidence(TranscriptWord(0, 1, "Hi", 0.4), 0.4)
    # Words that weren't aligned, or were corrected, have no score
    assert not is_low_confidence(TranscriptWord(0, 1, "Hi"), 0.4)


def test_no_word_is_low_confidence_if_they_are_not_highlighted() -> None:
    assert not is_low_confidence(TranscriptWord(0, 1, "Hi", 0.1), None)
