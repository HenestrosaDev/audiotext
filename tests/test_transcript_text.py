from models.transcript_segment import TranscriptWord
from views.transcript.transcript_text import LOW_CONFIDENCE_SCORE, is_low_confidence


def test_only_the_words_with_a_low_score_are_low_confidence() -> None:
    assert is_low_confidence(TranscriptWord(0, 1, "Hi", LOW_CONFIDENCE_SCORE - 0.1))
    assert not is_low_confidence(TranscriptWord(0, 1, "Hi", LOW_CONFIDENCE_SCORE))
    # Words that weren't aligned, or were corrected, have no score
    assert not is_low_confidence(TranscriptWord(0, 1, "Hi"))
