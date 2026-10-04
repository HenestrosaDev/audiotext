from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TranscriptWord:
    """A word of a segment with its timestamps, in seconds."""

    start: float
    end: float
    text: str


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

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"start": self.start, "end": self.end, "text": self.text}

        if self.speaker:
            data["speaker"] = self.speaker
        if self.words:
            data["words"] = [[w.start, w.end, w.text] for w in self.words]

        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TranscriptSegment":
        return cls(
            start=float(data["start"]),
            end=float(data["end"]),
            text=str(data["text"]),
            speaker=data.get("speaker"),
            words=tuple(
                TranscriptWord(float(start), float(end), str(text))
                for start, end, text in data.get("words", [])
            ),
        )


def join_segments(segments: list[TranscriptSegment]) -> str:
    """
    Joins the text of the segments. If the speakers are identified, a paragraph is
    started every time the speaker changes, prefixed with the speaker label.

    :param segments: The segments of the transcription.
    :return: The text of the transcription.
    """
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
