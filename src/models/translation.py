from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TranscriptTranslation:
    """A translation of a transcription into another language."""

    # Code of the language it's translated into (e.g. "es")
    language: str
    # The translated text of the transcription
    text: str
    # The translated text of each segment, in the same order as the segments of
    # the transcription. Empty if it has no timestamps or its text was edited, in
    # which case the edited text is translated
    segments: tuple[str, ...] = ()
    # The provider and the model that translated it, e.g. "deepl" and ""
    provider: str = ""
    model: str = ""
    created_at: str = ""
    # Whether the user edited the text, which then no longer follows the segments
    is_text_edited: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "text": self.text,
            "segments": list(self.segments),
            "provider": self.provider,
            "model": self.model,
            "created_at": self.created_at,
            "is_text_edited": self.is_text_edited,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TranscriptTranslation | None":
        """:return: The translation, or None if there is none (an empty dict)."""
        if not data.get("language") or not data.get("text"):
            return None

        return cls(
            language=str(data["language"]),
            text=str(data["text"]),
            segments=tuple(str(text) for text in data.get("segments", [])),
            provider=str(data.get("provider", "")),
            model=str(data.get("model", "")),
            created_at=str(data.get("created_at", "")),
            is_text_edited=bool(data.get("is_text_edited", False)),
        )
