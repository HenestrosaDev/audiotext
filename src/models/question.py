from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AnswerSource:
    """A part of the transcription that supports an answer, from the given second."""

    start: float
    quote: str


@dataclass(frozen=True)
class TranscriptAnswer:
    """The answer of a language model to a question about a transcription."""

    question: str
    answer: str
    # Only available if the transcription has timestamps
    sources: tuple[AnswerSource, ...] = ()
    # The model that answered it, e.g. "gpt-5.4-mini"
    model: str = ""
    created_at: str = ""
    # Whether the transcription was too long and only its beginning was read
    is_partial: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "sources": [[source.start, source.quote] for source in self.sources],
            "model": self.model,
            "created_at": self.created_at,
            "is_partial": self.is_partial,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TranscriptAnswer":
        return cls(
            question=str(data.get("question", "")),
            answer=str(data.get("answer", "")),
            sources=tuple(
                AnswerSource(float(start), str(quote))
                for start, quote in data.get("sources", [])
            ),
            model=str(data.get("model", "")),
            created_at=str(data.get("created_at", "")),
            is_partial=bool(data.get("is_partial", False)),
        )
