from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TranscriptWord:
    """A word of a segment with its timestamps, in seconds."""

    start: float
    end: float
    text: str
    # How well the word matches the audio, from 0 to 1. Only available if the word
    # was aligned, and lost when the word is edited
    score: float | None = None

    def to_list(self) -> list[Any]:
        if self.score is None:
            return [self.start, self.end, self.text]

        return [self.start, self.end, self.text, self.score]

    @classmethod
    def from_list(cls, data: list[Any]) -> "TranscriptWord":
        # The words saved before the scores were added have no score
        start, end, text, *rest = data
        score = float(rest[0]) if rest and rest[0] is not None else None

        return cls(float(start), float(end), str(text), score)


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
    # score whole segments (the OpenAI API). Lost when the text is edited
    score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"start": self.start, "end": self.end, "text": self.text}

        if self.speaker:
            data["speaker"] = self.speaker
        if self.words:
            data["words"] = [word.to_list() for word in self.words]
        if self.score is not None:
            data["score"] = self.score

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
