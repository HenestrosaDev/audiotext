from dataclasses import dataclass
from typing import Any

from models.transcript_segment import TranscriptSegment, TranscriptWord


@dataclass(frozen=True)
class TranscriptTranslation:
    """A translation of a transcription into another language."""

    # Code of the language it's translated into (e.g. "es")
    language: str
    # The translated text of the transcription
    text: str
    # The translated segments, sorted by their start. They start as the sentences
    # of the transcription, with the timestamps of its segments, but the user can
    # change them, add segments and delete them, since a translation often needs
    # another timing (e.g. subtitles that take longer to read). Empty if the
    # transcription has no timestamps or its text was edited, in which case the
    # edited text is translated
    segments: tuple[TranscriptSegment, ...] = ()
    # The provider and the model that translated it, e.g. "deepl" and "", or
    # "manual" if the user translates it from scratch, starting with empty texts
    provider: str = ""
    model: str = ""
    created_at: str = ""
    # Whether the user edited the text, which then no longer follows the segments
    is_text_edited: bool = False

    def translated_ratio(self, original: list[TranscriptSegment]) -> float:
        """
        How much of the transcription is translated, from 0 to 1: the share of
        its words said while a segment of the translation with a text lasts. The
        words with timestamps count where they're said, and the others where
        their segment is, since the segments of the translation can be retimed.

        :param original: The segments of the transcription.
        """
        if not original or not self.segments:
            # Without timestamps, the whole text is translated at once
            return 1.0 if self.text.strip() else 0.0

        translated = [(s.start, s.end) for s in self.segments if s.text.strip()]

        def is_translated(start: float, end: float) -> bool:
            return any(t_start < end and t_end > start for t_start, t_end in translated)

        def is_word_translated(word: TranscriptWord) -> bool:
            middle = (word.start + word.end) / 2
            return any(t_start <= middle < t_end for t_start, t_end in translated)

        total = done = 0
        for segment in original:
            if segment.words:
                total += len(segment.words)
                done += sum(1 for word in segment.words if is_word_translated(word))
            else:
                count = len(segment.text.split())
                total += count
                done += count if is_translated(segment.start, segment.end) else 0

        if not total:
            return 1.0 if translated else 0.0
        return done / total

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
