from dataclasses import dataclass
from typing import Any

from models.transcript_segment import TranscriptSegment


@dataclass(frozen=True)
class TranscriptTranslation:
    """A translation of a transcription into another language."""

    # Code of the language it's translated into (e.g. "es")
    language: str
    # The translated text of the transcription
    text: str
    # The translated segments, sorted by their start. They start with the
    # timestamps of the segments of the transcription, but the user can change
    # them, add segments and delete them, since a translation often needs another
    # timing (e.g. subtitles that take longer to read). Empty if the transcription
    # has no timestamps or its text was edited, in which case the edited text is
    # translated
    segments: tuple[TranscriptSegment, ...] = ()
    # The provider and the model that translated it, e.g. "deepl" and "", or
    # "manual" if the user translates it from scratch, starting with empty texts
    provider: str = ""
    model: str = ""
    created_at: str = ""
    # Whether the user edited the text, which then no longer follows the segments
    is_text_edited: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "text": self.text,
            "segments": [segment.to_dict() for segment in self.segments],
            "provider": self.provider,
            "model": self.model,
            "created_at": self.created_at,
            "is_text_edited": self.is_text_edited,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TranscriptTranslation | None":
        """:return: The translation, or None if there is none (an empty dict)."""
        if not data.get("language"):
            return None

        return cls(
            language=str(data["language"]),
            text=str(data.get("text", "")),
            segments=tuple(
                TranscriptSegment.from_dict(segment)
                for segment in data.get("segments", [])
                # The first versions only kept the texts, without the timestamps
                if isinstance(segment, dict)
            ),
            provider=str(data.get("provider", "")),
            model=str(data.get("model", "")),
            created_at=str(data.get("created_at", "")),
            is_text_edited=bool(data.get("is_text_edited", False)),
        )
