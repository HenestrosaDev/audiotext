from typing import Protocol

from models.summary import TranscriptSummary
from models.transcript_segment import TranscriptSegment


class Summarizer(Protocol):
    """Summarizes the transcriptions of the history (see `SummaryHandler`)."""

    def summarize(
        self, text: str, segments: list[TranscriptSegment]
    ) -> TranscriptSummary:
        """
        Summarizes a transcription. It takes a while, so it's called from a
        background thread.

        :param segments: The segments of the transcription, if it has timestamps.
        """
        ...
