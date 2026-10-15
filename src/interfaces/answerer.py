from typing import Protocol

from models.question import TranscriptAnswer
from models.transcript_segment import TranscriptSegment


class Answerer(Protocol):
    """Answers questions about the transcriptions (see `QuestionHandler`)."""

    def answer(
        self,
        text: str,
        segments: list[TranscriptSegment],
        question: str,
        previous: list[TranscriptAnswer],
    ) -> TranscriptAnswer:
        """
        Answers a question about a transcription. It takes a while, so it's called
        from a background thread.

        :param segments: The segments of the transcription, if it has timestamps.
        :param previous: The questions asked before and their answers, so the
                         question can refer to them.
        """
        ...
