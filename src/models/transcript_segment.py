from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ReviewMark(Enum):
    """How the user reviewed a text that may be wrong (see `models.review`)."""

    # Kept as it is
    ACCEPTED = "accepted"
    # Corrected, so it's no longer highlighted, whatever its score
    EDITED = "edited"


def _review_mark(value: Any) -> ReviewMark | None:
    """Reads a saved mark, which older (or newer) versions may not know."""
    try:
        return ReviewMark(value) if value is not None else None
    except ValueError:
        return None


@dataclass(frozen=True)
class TranscriptWord:
    """A word of a segment with its timestamps, in seconds."""

    start: float
    end: float
    text: str
    # How well the word matches the audio, from 0 to 1. Only available if the word
    # was aligned. Kept when the word is edited, so it's still counted
    score: float | None = None
    # Whether the user reviewed it, if it may be wrong
    reviewed: ReviewMark | None = None

    def to_list(self) -> list[Any]:
        data: list[Any] = [self.start, self.end, self.text]
        if self.score is not None or self.reviewed is not None:
            data.append(self.score)
        if self.reviewed is not None:
            data.append(self.reviewed.value)
        return data

    @classmethod
    def from_list(cls, data: list[Any]) -> "TranscriptWord":
        # The words saved before the scores (and the reviews) were added don't
        # have them
        start, end, text, *rest = data
        score = float(rest[0]) if rest and rest[0] is not None else None
        reviewed = _review_mark(rest[1]) if len(rest) > 1 else None

        return cls(float(start), float(end), str(text), score, reviewed)


@dataclass(frozen=True)
class TranscriptSegment:
    """A fragment of a transcription with its timestamps, in seconds."""

    start: float
    end: float
    text: str
    # Label assigned by the speaker diarization (e.g. "SPEAKER_00"), if any
    speaker: str | None = None
    # Only available if the transcription was aligned (word-level timings)
    words: tuple[TranscriptWord, ...] = field(default=())
    # How likely the text is to be right, from 0 to 1, for the engines that only
    # score whole segments (the OpenAI API). Kept when the text is edited
    score: float | None = None
    # Whether the user reviewed its text, if it's scored and may be wrong
    reviewed: ReviewMark | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"start": self.start, "end": self.end, "text": self.text}

        if self.speaker:
            data["speaker"] = self.speaker
        if self.words:
            data["words"] = [word.to_list() for word in self.words]
        if self.score is not None:
            data["score"] = self.score
        if self.reviewed is not None:
            data["reviewed"] = self.reviewed.value

        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TranscriptSegment":
        return cls(
            start=float(data["start"]),
            end=float(data["end"]),
            text=str(data["text"]),
            speaker=data.get("speaker"),
            words=tuple(
                TranscriptWord.from_list(word) for word in data.get("words", [])
            ),
            score=float(data["score"]) if data.get("score") is not None else None,
            reviewed=_review_mark(data.get("reviewed")),
        )


def has_scores(segments: list[TranscriptSegment]) -> bool:
    """:return: Whether any segment, or any of their words, has a score."""
    for segment in segments:
        if segment.score is not None:
            return True
        if any(word.score is not None for word in segment.words):
            return True

    return False


def join_segments(segments: list[TranscriptSegment]) -> str:
    """
    Joins the text of the segments. If the speakers are identified, a paragraph is
    started every time the speaker changes, prefixed with the speaker label.

    :param segments: The segments of the transcription.
    :return: The text of the transcription.
    """
    # Segments without text (e.g. not translated yet) are skipped
    segments = [segment for segment in segments if segment.text]
    if not any(segment.speaker for segment in segments):
        return " ".join(segment.text for segment in segments)

    paragraphs: list[tuple[str | None, list[str]]] = []

    for segment in segments:
        if paragraphs and paragraphs[-1][0] == segment.speaker:
            paragraphs[-1][1].append(segment.text)
        else:
            paragraphs.append((segment.speaker, [segment.text]))

    return "\n\n".join(
        f"[{speaker}]: {' '.join(texts)}" if speaker else " ".join(texts)
        for speaker, texts in paragraphs
    )
